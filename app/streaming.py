import logging
import os
import queue
import subprocess
import threading
import time
from datetime import datetime, timezone

from .station import StationSelector

log = logging.getLogger(__name__)


class StreamHub:
    def __init__(self, db, station: dict, settings):
        self.db = db
        self.station = station
        self.settings = settings
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
        self.last_error = None
        self.running = False
        self.tracks_played_this_run = 0

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
        self._thread = threading.Thread(
            target=self._run, name=f"radio-{self.station_id}", daemon=True
        )
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
        if track:
            track = {k: track.get(k) for k in ("id", "title", "artist", "album", "genre", "year", "duration")}
        if previous:
            previous = {k: previous.get(k) for k in ("id", "title", "artist", "album", "year")}
        return {
            "running": self.running,
            "listeners": self.listener_count,
            "current": track,
            "previous": previous,
            "track_started_at": started,
            "last_error": self.last_error,
            "tracks_played_this_run": self.tracks_played_this_run,
            "eligible_tracks": self.selector.eligible_track_count(),
        }

    def _run(self):
        self.running = True
        log.info("Broadcaster started for %s", self.station_id)
        try:
            while not self._stop.is_set():
                track = self.selector.choose_next()
                if not track:
                    self.last_error = "No tracks match this station's filters. Adjust the station or scan the library."
                    time.sleep(5)
                    continue
                self._play_track(track)
        except Exception:
            log.exception("Broadcaster worker crashed for %s", self.station_id)
            self.last_error = "Broadcaster worker crashed; check logs."
        finally:
            self.running = False
            log.info("Broadcaster stopped for %s", self.station_id)

    def _play_track(self, track: dict):
        path = track["path"]
        if not os.path.exists(path):
            self.db.mark_unplayable(track["id"], "File no longer exists")
            return

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
            "-re", "-i", path,
            "-vn", "-map_metadata", "-1",
            "-ac", "2", "-ar", str(self.settings.sample_rate),
            "-codec:a", "libmp3lame", "-b:a", f"{self.settings.bitrate_kbps}k",
            "-f", "mp3", "pipe:1",
        ]
        log.info("[%s] Now playing: %s - %s", self.station_id, track.get("artist"), track.get("title"))
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        except Exception as exc:
            self.last_error = f"Could not start FFmpeg: {exc}"
            log.exception(self.last_error)
            time.sleep(2)
            return

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

        with self._state_lock:
            self.previous_track = self.current_track
            self.current_track = track
            self.track_started_at = datetime.now(timezone.utc).isoformat()

        try:
            while not self._stop.is_set():
                chunk = proc.stdout.read(16384)
                if not chunk:
                    break
                if not emitted:
                    emitted = True
                    history_id = self.db.add_play(track["id"], self.listener_count, self.station_id)
                    self.tracks_played_this_run += 1
                    self.last_error = None
                self._publish(chunk)

            if self._stop.is_set() and proc.poll() is None:
                proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            stderr_thread.join(timeout=1)
            stderr_text = "\n".join(stderr_lines).strip()

            if history_id and proc.returncode == 0:
                self.db.complete_play(history_id)
            elif not emitted and not self._stop.is_set():
                error = stderr_text or f"FFmpeg returned code {proc.returncode} before producing audio"
                self.db.mark_unplayable(track["id"], error)
                self.last_error = error[:500]
                log.warning("Track marked unplayable: %s (%s)", path, error)
            elif proc.returncode not in (0, -15) and not self._stop.is_set():
                self.last_error = (stderr_text or f"FFmpeg exited with code {proc.returncode}")[:500]
                log.warning("FFmpeg issue on %s: %s", path, self.last_error)
        except Exception as exc:
            self.last_error = str(exc)
            log.exception("Playout error for %s", path)
            if proc.poll() is None:
                proc.kill()
        finally:
            self._ffmpeg = None

    def stream_generator(self):
        q = self.subscribe()
        try:
            while True:
                try:
                    chunk = q.get(timeout=15)
                    yield chunk
                except queue.Empty:
                    if self._stop.is_set():
                        return
        finally:
            self.unsubscribe(q)


class StationManager:
    def __init__(self, db, settings):
        self.db = db
        self.settings = settings
        self._lock = threading.RLock()
        self.hubs = {}

    def sync(self):
        stations = {s["id"]: s for s in self.db.list_stations()}
        with self._lock:
            # Stop removed, disabled, or edited station hubs. Rebuilding a hub
            # is intentional: selectors snapshot the station rules.
            for sid, hub in list(self.hubs.items()):
                desired = stations.get(sid)
                if not desired or not desired["enabled"] or desired != hub.station:
                    hub.stop()
                    self.hubs.pop(sid, None)
            if self.settings.auto_start_broadcast:
                for sid, station in stations.items():
                    if station["enabled"] and sid not in self.hubs:
                        hub = StreamHub(self.db, station, self.settings)
                        self.hubs[sid] = hub
                        hub.start()

    def start_all(self):
        self.sync()

    def stop_all(self):
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
        selector = StationSelector(self.db, station)
        return {
            "running": False, "listeners": 0, "current": None, "previous": None,
            "track_started_at": None, "last_error": None, "tracks_played_this_run": 0,
            "eligible_tracks": selector.eligible_track_count(),
        }

    def statuses(self):
        return [
            {"station": station, "playout": self.station_status(station)}
            for station in self.db.list_stations()
        ]
