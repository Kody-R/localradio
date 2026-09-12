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
    station_name: str = os.getenv("STATION_NAME", "LocalRadio")
    station_id: str = os.getenv("STATION_ID", "localradio")
    station_number: str = os.getenv("STATION_NUMBER", "801")
    artist_repeat_minutes: int = _int("ARTIST_REPEAT_MINUTES", 90)
    song_repeat_hours: int = _int("SONG_REPEAT_HOURS", 12)
    bitrate_kbps: int = _int("BITRATE_KBPS", 192)
    sample_rate: int = _int("SAMPLE_RATE", 44100)
    scan_interval_hours: int = _int("SCAN_INTERVAL_HOURS", 24)
    auto_scan_on_start: bool = _bool("AUTO_SCAN_ON_START", True)
    auto_start_broadcast: bool = _bool("AUTO_START_BROADCAST", True)
    min_year: int = _int("MIN_YEAR", 0)
    max_year: int = _int("MAX_YEAR", 0)
    allowed_genres_raw: str = os.getenv("ALLOWED_GENRES", "")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "localradio.db"

    @property
    def allowed_genres(self) -> list[str]:
        return [x.strip().lower() for x in self.allowed_genres_raw.split(",") if x.strip()]


settings = Settings()
