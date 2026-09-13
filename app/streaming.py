import logging
import os
import queue
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .imaging import ImagingLibrary
from .scheduler import AdvanceScheduler
from .station import StationSelector
from .tts import TTSManager

log = logging.getLogger(__name__)


class StreamHub:
    def __init__(self, db, station: dict, settings, scheduler: AdvanceScheduler):
        self.db = db
        self.station = station
        self.settings = settings
        self.scheduler = scheduler
        self.selector = StationSelector(db, station)
        self._subscribers = set()
        self._sub_lock = threading.RLock()
        self._state_lock = threading.RLock()
        self._thread = None
        self._stop = threading.Event()
        self._ffmpeg = None
        self.current_track = None
        self.previous_track = None
        self.track_started_at = None
        self.current_segment_type = "idle"
        self.announcement_text = None
        self.last_error = None
        self.running = False
        self.tracks_played_this_run = 0
        self.dj_breaks_this_run = 0
        self.station_ids_this_run = 0
        self.emergency_music_plays = 0

    @property
    def station_id(self):
        return self.station["id"]

    @property
    def listener_count(self):
        with self._sub_lock:
            return len(self._subscribers)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.scheduler.ensure_station_async(self.station_id)
        self._thread = threading.Thread(target=self._run, name=f"radio-{self.station_id}", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        proc = self._ffmpeg
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def subscribe(self):
        q = queue.Queue(maxsize=128)
        with self._sub_lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q):
        with self._sub_lock:
            self._subscribers.discard(q)

    def _publish(self, chunk: bytes):
        with self._sub_lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(chunk)
            except queue.Full:
                try:
                    while True:
                        q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    q.put_nowait(chunk)
                except queue.Full:
                    pass

    def status(self):
        with self._state_lock:
            track = dict(self.current_track) if self.current_track else None
            previous = dict(self.previous_track) if self.previous_track else None
            started = self.track_started_at
            segment_type = self.current_segment_type
            announcement = self.announcement_text
        if track:
            track = {k: track.get(k) for k in ("id", "title", "artist", "album", "genre", "year", "duration")}
        if previous:
            previous = {k: previous.get(k) for k in ("id", "title", "artist", "album", "year")}
        upcoming_rows = self.db.upcoming_schedule(self.station_id, 5)
        next_music = next((x for x in upcoming_rows if x.get("kind") == "music"), None)
        upcoming = None
        if next_music:
            upcoming = {k: next_music.get(k) for k in ("title", "artist", "album", "year")}
        return {
            "running": self.running,
            "listeners": self.listener_count,
            "current": track,
            "previous": previous,
            "next": upcoming,
            "track_started_at": started,
            "segment_type": segment_type,
            "announcement_text": announcement,
            "last_error": self.last_error,
            "tracks_played_this_run": self.tracks_played_this_run,
            "dj_breaks_this_run": self.dj_breaks_this_run,
            "station_ids_this_run": self.station_ids_this_run,
            "emergency_music_plays": self.emergency_music_plays,
            "eligible_tracks": self.selector.eligible_track_count(),
            "imaging_files": self.scheduler.imaging.count(self.station_id),
            "schedule": self.scheduler.station_status(self.station_id),
        }

    def _run(self):
        self.running = True
        log.info("Broadcaster started for %s", self.station_id)
        try:
            while not self._stop.is_set():
                entry = self.db.next_schedule_entry(self.station_id)
                if not entry:
                    # Scheduler generation may take a few seconds when Ollama/TTS
                    # is cold. Never let that become dead air: play a normal track
                    # while another thread rebuilds the future queue.
                    self.scheduler.ensure_station_async(self.station_id)
                    track = self.selector.choose_next()
                    if not track:
                        self.last_error = "No tracks match this station's filters. Adjust the station or scan the library."
                        time.sleep(2)
                        continue
                    self.emergency_music_plays += 1
                    self._play_track(track)
                    continue

                self.db.set_schedule_state(entry["id"], "playing")
                ok = False
                try:
                    kind = entry.get("kind")
                    if kind == "music":
                        track = {
                            "id": entry.get("track_id"), "path": entry.get("path"), "title": entry.get("title"),
                            "artist": entry.get("artist"), "album": entry.get("album"), "genre": entry.get("genre"),
                            "year": entry.get("year"), "duration": entry.get("duration"),
                        }
                        ok = self._play_track(track)
                    elif kind in {"dj", "station-id"}:
                        ok = self._play_imaging(
                            entry.get("audio_path"),
                            segment_type=kind,
                            announcement_text=entry.get("script_text"),
                        )
                        if ok and kind == "dj":
                            self.dj_breaks_this_run += 1
                        if ok and kind == "station-id":
                            self.station_ids_this_run += 1
                    else:
                        log.warning("Unknown schedule entry kind %s", kind)
                finally:
                    self.db.set_schedule_state(entry["id"], "completed" if ok else "skipped")
                    schedule = self.scheduler.station_status(self.station_id)
                    if float(schedule.get("hours") or 0) < float(schedule.get("minimum_hours") or 1):
                        self.scheduler.ensure_station_async(self.station_id)
        except Exception:
            log.exception("Broadcaster worker crashed for %s", self.station_id)
            self.last_error = "Broadcaster worker crashed; check logs."
        finally:
            self.running = False
            log.info("Broadcaster stopped for %s", self.station_id)

    def _play_track(self, track: dict):
        path = track.get("path")
        if not path or not os.path.exists(path):
            if track.get("id"):
                self.db.mark_unplayable(track["id"], "File no longer exists")
            return False
        with self._state_lock:
            self.previous_track = self.current_track
            self.current_track = track
            self.track_started_at = datetime.now(timezone.utc).isoformat()
            self.current_segment_type = "music"
            self.announcement_text = None
        log.info("[%s] Now playing: %s - %s", self.station_id, track.get("artist"), track.get("title"))
        emitted, history_id, returncode, stderr_text = self._broadcast_file(path, realtime=True, is_track=True, track=track)
        if history_id and returncode == 0:
            self.db.complete_play(history_id)
        elif not emitted and not self._stop.is_set():
            error = stderr_text or f"FFmpeg returned code {returncode} before producing audio"
            if track.get("id"):
                self.db.mark_unplayable(track["id"], error)
            self.last_error = error[:500]
            return False
        elif returncode not in (0, -15) and not self._stop.is_set():
            self.last_error = (stderr_text or f"FFmpeg exited with code {returncode}")[:500]
        return bool(emitted)

    def _broadcast_file(self, path, *, realtime=True, is_track=True, track=None):
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin"]
        if realtime:
            cmd.append("-re")
        cmd += [
            "-i", str(path), "-vn", "-map_metadata", "-1",
            "-ac", "2", "-ar", str(self.settings.sample_rate),
            "-codec:a", "libmp3lame", "-b:a", f"{self.settings.bitrate_kbps}k",
            "-f", "mp3", "pipe:1",
        ]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        except Exception as exc:
            self.last_error = f"Could not start FFmpeg: {exc}"
            return False, None, -1, str(exc)
        self._ffmpeg = proc
        history_id = None
        emitted = False
        stderr_lines = []

        def drain_stderr():
            try:
                for raw in iter(proc.stderr.readline, b""):
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line:
                        stderr_lines.append(line)
                        if len(stderr_lines) > 40:
                            del stderr_lines[:-40]
            except Exception:
                pass

        stderr_thread = threading.Thread(target=drain_stderr, name=f"ffmpeg-{self.station_id}", daemon=True)
        stderr_thread.start()
        try:
            while not self._stop.is_set():
                chunk = proc.stdout.read(16384)
                if not chunk:
                    break
                if not emitted:
                    emitted = True
                    self.last_error = None
                    if is_track and track and track.get("id"):
                        history_id = self.db.add_play(track["id"], self.listener_count, self.station_id)
                        self.tracks_played_this_run += 1
                self._publish(chunk)
            if self._stop.is_set() and proc.poll() is None:
                proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            stderr_thread.join(timeout=1)
            return emitted, history_id, proc.returncode, "\n".join(stderr_lines).strip()
        except Exception as exc:
            self.last_error = str(exc)
            if proc.poll() is None:
                proc.kill()
            return emitted, history_id, proc.returncode or -1, str(exc)
        finally:
            self._ffmpeg = None

    def _play_imaging(self, path, *, segment_type: str, announcement_text: str | None = None):
        if not path or not Path(path).exists() or self._stop.is_set():
            return False
        with self._state_lock:
            self.current_segment_type = segment_type
            self.announcement_text = announcement_text
            self.track_started_at = datetime.now(timezone.utc).isoformat()
        log.info("[%s] Playing %s: %s", self.station_id, segment_type, path)
        emitted, _, returncode, stderr_text = self._broadcast_file(path, realtime=True, is_track=False)
        if not emitted and not self._stop.is_set():
            log.warning("[%s] Imaging failed: %s", self.station_id, stderr_text or returncode)
        with self._state_lock:
            self.current_segment_type = "transition"
            self.announcement_text = None
        return bool(emitted)

    def stream_generator(self):
        q = self.subscribe()
        try:
            while True:
                try:
                    yield q.get(timeout=15)
                except queue.Empty:
                    if self._stop.is_set():
                        return
        finally:
            self.unsubscribe(q)


class StationManager:
    def __init__(self, db, settings):
        self.db = db
        self.settings = settings
        self.tts = TTSManager(settings)
        self.imaging = ImagingLibrary(settings)
        self.scheduler = AdvanceScheduler(db, settings, self.tts, self.imaging)
        self._lock = threading.RLock()
        self.hubs = {}

    def sync(self, rebuild_changed=True):
        stations = {s["id"]: s for s in self.db.list_stations()}
        changed = []
        with self._lock:
            for sid, hub in list(self.hubs.items()):
                desired = stations.get(sid)
                if not desired or not desired["enabled"] or desired != hub.station:
                    hub.stop()
                    self.hubs.pop(sid, None)
                    if desired and desired.get("enabled"):
                        changed.append(sid)
            if self.settings.auto_start_broadcast:
                for sid, station in stations.items():
                    if station["enabled"] and sid not in self.hubs:
                        hub = StreamHub(self.db, station, self.settings, self.scheduler)
                        self.hubs[sid] = hub
                        hub.start()
        if rebuild_changed:
            for sid in changed:
                self.scheduler.invalidate_station(sid)

    def start_all(self):
        self.scheduler.start()
        self.sync(rebuild_changed=False)

    def stop_all(self):
        self.scheduler.stop()
        with self._lock:
            hubs = list(self.hubs.values())
        for hub in hubs:
            hub.stop()

    def get_hub(self, station_id: str):
        with self._lock:
            return self.hubs.get(station_id)

    def station_status(self, station: dict) -> dict:
        hub = self.get_hub(station["id"])
        if hub:
            return hub.status()
        return {
            "running": False, "listeners": 0, "current": None, "previous": None, "next": None,
            "track_started_at": None, "segment_type": "disabled" if not station.get("enabled") else "stopped",
            "announcement_text": None, "last_error": None, "tracks_played_this_run": 0,
            "dj_breaks_this_run": 0, "station_ids_this_run": 0, "emergency_music_plays": 0,
            "eligible_tracks": StationSelector(self.db, station).eligible_track_count(),
            "imaging_files": self.imaging.count(station["id"]),
            "schedule": self.scheduler.station_status(station["id"]),
        }

    def statuses(self):
        return [{"station": s, "playout": self.station_status(s)} for s in self.db.list_stations()]
