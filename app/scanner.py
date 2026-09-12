import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from mutagen import File as MutagenFile

log = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".mp4", ".ogg", ".opus", ".wav", ".aac", ".wma", ".aiff", ".ape"}


def _first(tags, keys, default=""):
    if not tags:
        return default
    for key in keys:
        value = tags.get(key)
        if value:
            if isinstance(value, (list, tuple)):
                value = value[0] if value else default
            return str(value).strip()
    return default


def _year(value: str):
    if not value:
        return None
    match = re.search(r"(?:19|20)\d{2}", str(value))
    return int(match.group(0)) if match else None


class LibraryScanner:
    def __init__(self, db, music_dir: Path):
        self.db = db
        self.music_dir = Path(music_dir)
        self.lock = threading.Lock()
        self.running = False
        self.last_result = None

    def scan(self) -> dict:
        if not self.lock.acquire(blocking=False):
            return {"ok": False, "message": "Scan already running"}
        self.running = True
        started = datetime.now(timezone.utc)
        found = updated = unchanged = errors = 0
        try:
            if not self.music_dir.exists():
                msg = f"Music directory does not exist: {self.music_dir}"
                log.warning(msg)
                self.last_result = {"ok": False, "message": msg}
                return self.last_result

            self.db.begin_scan()
            for path in self.music_dir.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
                    continue
                found += 1
                try:
                    st = path.stat()
                    sig = self.db.get_file_signature(str(path))
                    if sig == (st.st_size, st.st_mtime_ns):
                        self.db.mark_seen_unchanged(str(path))
                        unchanged += 1
                        continue

                    audio = MutagenFile(path, easy=True)
                    if audio is None or not getattr(audio, "info", None):
                        raise ValueError("Unsupported or unreadable audio metadata")
                    tags = audio.tags or {}
                    title = _first(tags, ["title"]) or path.stem
                    artist = _first(tags, ["artist", "albumartist"]) or "Unknown Artist"
                    album = _first(tags, ["album"]) or "Unknown Album"
                    album_artist = _first(tags, ["albumartist", "artist"]) or artist
                    genre = _first(tags, ["genre"]) or "Unknown"
                    date_value = _first(tags, ["date", "year", "originaldate"])
                    info = audio.info
                    self.db.upsert_track({
                        "path": str(path),
                        "title": title,
                        "artist": artist,
                        "album": album,
                        "album_artist": album_artist,
                        "genre": genre,
                        "year": _year(date_value),
                        "duration": float(getattr(info, "length", 0) or 0),
                        "bitrate": int(getattr(info, "bitrate", 0) or 0),
                        "sample_rate": int(getattr(info, "sample_rate", 0) or 0),
                        "file_size": st.st_size,
                        "modified_ns": st.st_mtime_ns,
                    })
                    updated += 1
                except Exception as exc:
                    errors += 1
                    log.warning("Could not scan %s: %s", path, exc)

            removed = self.db.finish_scan()
            finished = datetime.now(timezone.utc)
            result = {
                "ok": True,
                "found": found,
                "updated": updated,
                "unchanged": unchanged,
                "errors": errors,
                "removed": removed,
                "duration_seconds": round((finished - started).total_seconds(), 2),
                "finished_at": finished.isoformat(),
            }
            self.db.set_state("last_scan", finished.isoformat())
            self.db.set_state("last_scan_result", str(result))
            self.last_result = result
            log.info("Library scan complete: %s", result)
            return result
        finally:
            self.running = False
            self.lock.release()
