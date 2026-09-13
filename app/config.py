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
    config_dir: Path = Path(os.getenv("CONFIG_DIR", "/config"))
    bitrate_kbps: int = _int("BITRATE_KBPS", 192)
    sample_rate: int = _int("SAMPLE_RATE", 44100)
    scan_interval_hours: int = _int("SCAN_INTERVAL_HOURS", 24)
    auto_scan_on_start: bool = _bool("AUTO_SCAN_ON_START", True)
    auto_start_broadcast: bool = _bool("AUTO_START_BROADCAST", True)

    # Local TTS. `auto` prefers Piper when a matching .onnx model is mounted
    # under /config/voices, then falls back to bundled eSpeak NG.
    tts_engine: str = os.getenv("TTS_ENGINE", "auto")
    piper_binary: str = os.getenv("PIPER_BINARY", "piper")
    default_espeak_voice: str = os.getenv("DEFAULT_ESPEAK_VOICE", "en-us")

    # v0.2.0 Ollama / advance scheduling defaults.
    ollama_url: str = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434").rstrip("/")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3:4b")
    ollama_timeout_seconds: int = _int("OLLAMA_TIMEOUT_SECONDS", 45)
    ollama_failure_threshold: int = _int("OLLAMA_FAILURE_THRESHOLD", 3)
    ollama_circuit_seconds: int = _int("OLLAMA_CIRCUIT_SECONDS", 300)
    ollama_keep_alive: str = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
    schedule_target_hours: int = _int("SCHEDULE_TARGET_HOURS", 24)
    schedule_min_hours: int = _int("SCHEDULE_MIN_HOURS", 6)
    schedule_check_seconds: int = _int("SCHEDULE_CHECK_SECONDS", 60)

    # v0.1.0/v0.1.1 compatibility: these values seed the first station only
    # when the database contains no stations yet. Station settings then live in
    # SQLite and are managed through the web UI.
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

    @property
    def tts_cache_dir(self) -> Path:
        return self.data_dir / "tts-cache"

    @property
    def voices_dir(self) -> Path:
        return self.config_dir / "voices"

    @property
    def imaging_dir(self) -> Path:
        return self.config_dir / "imaging"


settings = Settings()
