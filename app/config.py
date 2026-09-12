import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    music_dir: Path = Path(os.getenv("MUSIC_DIR", "/music"))
    data_dir: Path = Path(os.getenv("DATA_DIR", "/data"))
    bitrate_kbps: int = _int("BITRATE_KBPS", 192)
    sample_rate: int = _int("SAMPLE_RATE", 44100)
    scan_interval_hours: int = _int("SCAN_INTERVAL_HOURS", 24)
    auto_scan_on_start: bool = _bool("AUTO_SCAN_ON_START", True)
    auto_start_broadcast: bool = _bool("AUTO_START_BROADCAST", True)

    # v0.1.0 compatibility: these values seed the first station only when the
    # database contains no stations yet. From v0.1.1 onward station settings
    # are managed in the web UI and persisted in SQLite.
    seed_station_name: str = os.getenv("STATION_NAME", "LocalRadio")
    seed_station_id: str = os.getenv("STATION_ID", "localradio")
    seed_station_number: str = os.getenv("STATION_NUMBER", "801")
    seed_artist_repeat_minutes: int = _int("ARTIST_REPEAT_MINUTES", 90)
    seed_song_repeat_hours: int = _int("SONG_REPEAT_HOURS", 12)
    seed_min_year: int = _int("MIN_YEAR", 0)
    seed_max_year: int = _int("MAX_YEAR", 0)
    seed_allowed_genres: str = os.getenv("ALLOWED_GENRES", "")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "localradio.db"


settings = Settings()
