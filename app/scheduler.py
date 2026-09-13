import logging
import random
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .ollama_client import OllamaClient
from .station import StationSelector

log = logging.getLogger(__name__)


class AdvanceScheduler:
    def __init__(self, db, settings, tts, imaging):
        self.db = db
        self.settings = settings
        self.tts = tts
        self.imaging = imaging
        self.ollama = OllamaClient(settings)
        self._lock = threading.RLock()
        self._station_locks = {}
        self._state = {}
        self._stop = threading.Event()
        self._thread = None
        self._building = set()
        self._last_error = {}
        self._last_build = {}

    def _station_lock(self, station_id):
        with self._lock:
            return self._station_locks.setdefault(station_id, threading.RLock())

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker, name="advance-scheduler", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _worker(self):
        # Fill the minimum buffer in small batches first, then continue toward
        # the target. AI/TTS generation stays entirely off the live audio path.
        while not self._stop.is_set():
            did_work = False
            for station in self.db.list_stations(enabled_only=True):
                if self._stop.is_set():
                    break
                try:
                    buf = self.db.schedule_buffer(station["id"])
                    target = max(1, int(self.settings.schedule_target_hours))
                    minimum = max(1, min(int(self.settings.schedule_min_hours), target))
                    if float(buf.get("hours") or 0) < target:
                        batch = 16 if float(buf.get("hours") or 0) < minimum else 8
                        self.ensure_station(station["id"], max_music=batch)
                        did_work = True
                except Exception as exc:
                    self._last_error[station["id"]] = str(exc)[:1000]
                    log.exception("Schedule build failed for %s", station["id"])
            self.db.cleanup_schedule()
            if self._stop.wait(2 if did_work else max(10, int(self.settings.schedule_check_seconds))):
                return

    def invalidate_station(self, station_id: str):
        # Do not make a Station Builder save wait for an in-progress Ollama
        # request. Serialize invalidation behind any current builder in a small
        # background worker, then immediately begin refilling the fresh queue.
        def worker():
            with self._station_lock(station_id):
                self.db.clear_future_schedule(station_id)
                with self._lock:
                    self._state.pop(station_id, None)
            self.ensure_station(station_id, max_music=16)
        threading.Thread(target=worker, name=f"schedule-reset-{station_id}", daemon=True).start()

    def ensure_station_async(self, station_id: str):
        def run():
            try:
                self.ensure_station(station_id, max_music=16)
            except Exception:
                log.exception("Async schedule build failed for %s", station_id)
        threading.Thread(target=run, name=f"schedule-{station_id}", daemon=True).start()

    def _build_state(self, station: dict):
        sid = station["id"]
        with self._lock:
            state = self._state.get(sid)
            if not state:
                minimum = max(1, int(station.get("dj_min_songs") or 3))
                maximum = max(minimum, int(station.get("dj_max_songs") or minimum))
                state = {
                    "songs_since_dj": 0,
                    "songs_since_id": 0,
                    "dj_target": random.randint(minimum, maximum),
                    "pending_track": None,
                }
                self._state[sid] = state
            return state

    @staticmethod
    def _safe_words(text: str, max_words: int) -> str:
        text = " ".join((text or "").replace("\n", " ").split()).strip(" \"'")
        # Strip common model prefixes and lightweight markdown.
        text = re.sub(r"^(dj|announcement|script)\s*:\s*", "", text, flags=re.I)
        text = text.replace("**", "").replace("`", "")
        words = text.split()
        if len(words) > max_words:
            text = " ".join(words[:max_words]).rstrip(" ,;:-")
            if text and text[-1] not in ".!?":
                text += "."
        return text[:900]

    def _deterministic_dj(self, station, previous, upcoming, include_id=False):
        station_name = station["name"]
        slogan = str(station.get("station_slogan") or "").strip()
        pa = previous.get("artist") or "that artist"
        pt = previous.get("title") or "that song"
        na = upcoming.get("artist") or "another favorite"
        nt = upcoming.get("title") or "another song"
        templates = [
            "That was {pa} with {pt}. Coming up, {na} with {nt}, right here on {station}.",
            "You just heard {pt} from {pa}. Next up is {nt} by {na} on {station}.",
            "{pa}, {pt}. We've got {na} and {nt} coming up next on {station}.",
            "Keeping the music moving on {station}. That was {pt} by {pa}; next is {nt} from {na}.",
        ]
        body = random.choice(templates).format(pa=pa, pt=pt, na=na, nt=nt, station=station_name)
        if include_id:
            return f"{station_name}. " + (f"{slogan}. " if slogan else "") + body
        return body

    def _station_id_text(self, station):
        lines = [x.strip() for x in str(station.get("station_liners") or "").splitlines() if x.strip()]
        if lines:
            text = random.choice(lines)
            return " ".join(text.replace("{station}", station["name"]).replace(
                "{slogan}", str(station.get("station_slogan") or "")
            ).split())
        slogan = str(station.get("station_slogan") or "").strip()
        return f"You're listening to {station['name']}." + (f" {slogan}." if slogan else "")

    def _ai_dj_text(self, station, previous, upcoming, include_id=False, planned_time=None):
        if not station.get("ai_dj_enabled"):
            return None
        max_words = max(10, min(int(station.get("ai_max_words") or 40), 100))
        personality = str(station.get("ai_personality") or "").strip() or (
            "Friendly, concise local radio DJ. Natural and upbeat without sounding exaggerated."
        )
        recent = self.db.recent_schedule_scripts(station["id"], 5)
        airtime = planned_time or datetime.now(timezone.utc)
        now_local = airtime.astimezone().strftime("%A %I:%M %p").lstrip("0")
        supplied = {
            "station": station["name"],
            "slogan": station.get("station_slogan") or "",
            "previous_artist": previous.get("artist") or "Unknown Artist",
            "previous_title": previous.get("title") or "Unknown Title",
            "previous_album": previous.get("album") or "",
            "previous_year": previous.get("year") or "",
            "next_artist": upcoming.get("artist") or "Unknown Artist",
            "next_title": upcoming.get("title") or "Unknown Title",
            "next_album": upcoming.get("album") or "",
            "next_year": upcoming.get("year") or "",
            "local_time": now_local,
            "include_station_id": bool(include_id),
        }
        system = f"""You write short spoken radio DJ breaks for LocalRadio.\nPersonality: {personality}\nRules:\n- Return only the words the DJ should speak. No labels, markdown, stage directions, or quotation marks.\n- Use at most {max_words} words and normally 1-2 sentences.\n- Back-announce the previous song and naturally tease the next song.\n- You may mention the supplied station name, slogan, local time, album, or year.\n- NEVER invent chart positions, awards, biographies, release facts, locations, weather, news, or trivia not explicitly supplied.\n- Avoid internet slang and exaggerated hype unless the personality explicitly requests it.\n- Vary phrasing and avoid repeating recent scripts.\n"""
        user = "SUPPLIED FACTS:\n" + "\n".join(f"{k}: {v}" for k, v in supplied.items())
        if recent:
            user += "\n\nRECENT SCRIPTS TO AVOID ECHOING:\n" + "\n".join(f"- {x}" for x in recent)
        raw = self.ollama.generate(
            system=system,
            user=user,
            model=(station.get("ai_model") or "").strip() or None,
            max_tokens=max(64, max_words * 3),
        )
        if not raw:
            return None
        cleaned = self._safe_words(raw, max_words)
        return cleaned if len(cleaned.split()) >= 5 else None

    def _make_dj_asset(self, station, previous, upcoming, include_id=False, planned_time=None):
        text = self._ai_dj_text(station, previous, upcoming, include_id=include_id, planned_time=planned_time)
        ai_generated = bool(text)
        if not text:
            text = self._deterministic_dj(station, previous, upcoming, include_id=include_id)
        audio = self.tts.generate(
            text,
            voice=station.get("dj_voice") or "",
            speed_wpm=int(station.get("dj_speed_wpm") or 165),
        )
        if not audio:
            custom = self.imaging.random_file(station["id"])
            if custom:
                return {"text": text, "audio": custom, "ai": ai_generated, "duration": 7.0}
            return None
        duration = max(4.0, len(text.split()) / 2.5)
        return {"text": text, "audio": audio, "ai": ai_generated, "duration": duration}

    def _make_station_id_asset(self, station):
        custom = self.imaging.random_file(station["id"])
        if custom:
            return {"text": None, "audio": custom, "ai": False, "duration": 7.0}
        text = self._station_id_text(station)
        audio = self.tts.generate(
            text,
            voice=station.get("dj_voice") or "",
            speed_wpm=int(station.get("dj_speed_wpm") or 165),
        )
        if not audio:
            return None
        return {"text": text, "audio": audio, "ai": False, "duration": max(3.0, len(text.split()) / 2.5)}

    def ensure_station(self, station_id: str, *, max_music: int = 16, force_target_hours: float | None = None):
        station = self.db.get_station(station_id)
        if not station or not station.get("enabled"):
            return self.db.schedule_buffer(station_id)
        lock = self._station_lock(station_id)
        if not lock.acquire(blocking=False):
            return self.db.schedule_buffer(station_id)
        with self._lock:
            self._building.add(station_id)
        try:
            target_hours = float(force_target_hours if force_target_hours is not None else max(1, self.settings.schedule_target_hours))
            buf = self.db.schedule_buffer(station_id)
            if float(buf.get("hours") or 0) >= target_hours:
                return buf
            state = self._build_state(station)
            selector = StationSelector(self.db, station)
            base_time = datetime.now(timezone.utc) + timedelta(seconds=float(buf.get("seconds") or 0))
            recent_ids = self.db.scheduled_track_ids(station_id, 80)
            music_added = 0

            while music_added < max(1, int(max_music)):
                current_buffer = self.db.schedule_buffer(station_id)
                if float(current_buffer.get("hours") or 0) >= target_hours:
                    break
                track = state.get("pending_track")
                state["pending_track"] = None
                if not track:
                    track = selector.choose_next(exclude_ids=recent_ids[-40:])
                    if not track:
                        track = selector.choose_next()
                if not track:
                    break
                duration = max(1.0, float(track.get("duration") or 180.0))
                self.db.add_schedule_entry(station_id, "music", base_time.isoformat(), duration, track_id=track["id"])
                base_time += timedelta(seconds=duration)
                recent_ids.append(track["id"])
                music_added += 1
                state["songs_since_dj"] += 1
                state["songs_since_id"] += 1

                due_dj = bool(station.get("dj_enabled")) and state["songs_since_dj"] >= state["dj_target"]
                every_id = max(1, int(station.get("station_id_every_songs") or 8))
                due_id = bool(station.get("station_id_enabled")) and state["songs_since_id"] >= every_id

                if due_dj:
                    upcoming = selector.choose_next(exclude_ids=recent_ids[-40:])
                    if not upcoming:
                        upcoming = selector.choose_next(exclude_ids=[track.get("id")])
                    if upcoming:
                        asset = self._make_dj_asset(station, track, upcoming, include_id=due_id, planned_time=base_time)
                        if asset:
                            self.db.add_schedule_entry(
                                station_id, "dj", base_time.isoformat(), asset["duration"],
                                script_text=asset["text"], audio_path=asset["audio"], ai_generated=asset["ai"],
                            )
                            base_time += timedelta(seconds=asset["duration"])
                        state["pending_track"] = upcoming
                    state["songs_since_dj"] = 0
                    minimum = max(1, int(station.get("dj_min_songs") or 3))
                    maximum = max(minimum, int(station.get("dj_max_songs") or minimum))
                    state["dj_target"] = random.randint(minimum, maximum)
                    if due_id:
                        state["songs_since_id"] = 0
                elif due_id:
                    asset = self._make_station_id_asset(station)
                    if asset:
                        self.db.add_schedule_entry(
                            station_id, "station-id", base_time.isoformat(), asset["duration"],
                            script_text=asset["text"], audio_path=asset["audio"], ai_generated=False,
                        )
                        base_time += timedelta(seconds=asset["duration"])
                    state["songs_since_id"] = 0

            self._last_build[station_id] = datetime.now(timezone.utc).isoformat()
            self._last_error.pop(station_id, None)
            return self.db.schedule_buffer(station_id)
        except Exception as exc:
            self._last_error[station_id] = str(exc)[:1000]
            raise
        finally:
            with self._lock:
                self._building.discard(station_id)
            lock.release()

    def rebuild_station(self, station_id: str):
        station = self.db.get_station(station_id)
        if not station:
            return None
        with self._station_lock(station_id):
            self.db.clear_future_schedule(station_id)
            with self._lock:
                self._state.pop(station_id, None)
        return self.ensure_station(station_id, max_music=20)

    def station_status(self, station_id: str):
        buf = self.db.schedule_buffer(station_id)
        with self._lock:
            building = station_id in self._building
        return {
            **buf,
            "building": building,
            "minimum_hours": max(1, int(self.settings.schedule_min_hours)),
            "target_hours": max(1, int(self.settings.schedule_target_hours)),
            "last_build": self._last_build.get(station_id),
            "last_error": self._last_error.get(station_id),
        }

    def status(self):
        return {
            "ollama": self.ollama.status(),
            "stations": {s["id"]: self.station_status(s["id"]) for s in self.db.list_stations(enabled_only=True)},
        }
