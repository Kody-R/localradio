import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    title TEXT,
    artist TEXT,
    album TEXT,
    album_artist TEXT,
    genre TEXT,
    year INTEGER,
    duration REAL NOT NULL DEFAULT 0,
    bitrate INTEGER,
    sample_rate INTEGER,
    file_size INTEGER NOT NULL DEFAULT 0,
    modified_ns INTEGER NOT NULL DEFAULT 0,
    scan_seen INTEGER NOT NULL DEFAULT 1,
    playable INTEGER NOT NULL DEFAULT 1,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist);
CREATE INDEX IF NOT EXISTS idx_tracks_genre ON tracks(genre);
CREATE INDEX IF NOT EXISTS idx_tracks_year ON tracks(year);
CREATE INDEX IF NOT EXISTS idx_tracks_playable ON tracks(playable);

CREATE TABLE IF NOT EXISTS play_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER NOT NULL,
    station_id TEXT,
    started_at TEXT NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0,
    client_count INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_history_started ON play_history(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_track ON play_history(track_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_station ON play_history(station_id, started_at DESC);

CREATE TABLE IF NOT EXISTS stations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    channel_number TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    genres_include TEXT NOT NULL DEFAULT '',
    genres_exclude TEXT NOT NULL DEFAULT '',
    min_year INTEGER NOT NULL DEFAULT 0,
    max_year INTEGER NOT NULL DEFAULT 0,
    artists_include TEXT NOT NULL DEFAULT '',
    artists_exclude TEXT NOT NULL DEFAULT '',
    artist_repeat_minutes INTEGER NOT NULL DEFAULT 90,
    song_repeat_hours INTEGER NOT NULL DEFAULT 12,
    logo_url TEXT NOT NULL DEFAULT '',
    dj_enabled INTEGER NOT NULL DEFAULT 1,
    dj_min_songs INTEGER NOT NULL DEFAULT 3,
    dj_max_songs INTEGER NOT NULL DEFAULT 5,
    dj_voice TEXT NOT NULL DEFAULT '',
    dj_speed_wpm INTEGER NOT NULL DEFAULT 165,
    station_slogan TEXT NOT NULL DEFAULT '',
    station_liners TEXT NOT NULL DEFAULT '',
    station_id_enabled INTEGER NOT NULL DEFAULT 1,
    station_id_every_songs INTEGER NOT NULL DEFAULT 8,
    ai_dj_enabled INTEGER NOT NULL DEFAULT 1,
    ai_model TEXT NOT NULL DEFAULT '',
    ai_personality TEXT NOT NULL DEFAULT '',
    ai_max_words INTEGER NOT NULL DEFAULT 40,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stations_enabled ON stations(enabled, channel_number);

CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT NOT NULL
);
"""


STATION_FIELDS = {
    "name", "channel_number", "enabled", "genres_include", "genres_exclude",
    "min_year", "max_year", "artists_include", "artists_exclude",
    "artist_repeat_minutes", "song_repeat_hours", "logo_url",
    "dj_enabled", "dj_min_songs", "dj_max_songs", "dj_voice", "dj_speed_wpm",
    "station_slogan", "station_liners", "station_id_enabled", "station_id_every_songs",
    "ai_dj_enabled", "ai_model", "ai_personality", "ai_max_words",
}


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return value[:64] or "station"


class Database:
    def __init__(self, path: Path, settings=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.RLock()
        self.init()
        if settings is not None:
            self.ensure_seed_station(settings)

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def connection(self):
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    def init(self):
        with self._write_lock, self.connection() as conn:
            # A v0.1.0 DB already has play_history but without station_id. Add
            # that column before creating its v0.1.1 index.
            conn.executescript(SCHEMA.split("CREATE INDEX IF NOT EXISTS idx_history_station")[0])
            columns = {row[1] for row in conn.execute("PRAGMA table_info(play_history)").fetchall()}
            if "station_id" not in columns:
                conn.execute("ALTER TABLE play_history ADD COLUMN station_id TEXT")
            conn.executescript("""
                CREATE INDEX IF NOT EXISTS idx_history_station ON play_history(station_id, started_at DESC);
                CREATE TABLE IF NOT EXISTS stations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    channel_number TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    genres_include TEXT NOT NULL DEFAULT '',
                    genres_exclude TEXT NOT NULL DEFAULT '',
                    min_year INTEGER NOT NULL DEFAULT 0,
                    max_year INTEGER NOT NULL DEFAULT 0,
                    artists_include TEXT NOT NULL DEFAULT '',
                    artists_exclude TEXT NOT NULL DEFAULT '',
                    artist_repeat_minutes INTEGER NOT NULL DEFAULT 90,
                    song_repeat_hours INTEGER NOT NULL DEFAULT 12,
                    logo_url TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_stations_enabled ON stations(enabled, channel_number);
                CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT NOT NULL
                );
            """)
            # v0.1.2 station imaging / DJ migration. SQLite cannot add several
            # columns conditionally in one statement, so add only those absent.
            station_columns = {row[1] for row in conn.execute("PRAGMA table_info(stations)").fetchall()}
            additions = {
                "dj_enabled": "INTEGER NOT NULL DEFAULT 1",
                "dj_min_songs": "INTEGER NOT NULL DEFAULT 3",
                "dj_max_songs": "INTEGER NOT NULL DEFAULT 5",
                "dj_voice": "TEXT NOT NULL DEFAULT ''",
                "dj_speed_wpm": "INTEGER NOT NULL DEFAULT 165",
                "station_slogan": "TEXT NOT NULL DEFAULT ''",
                "station_liners": "TEXT NOT NULL DEFAULT ''",
                "station_id_enabled": "INTEGER NOT NULL DEFAULT 1",
                "station_id_every_songs": "INTEGER NOT NULL DEFAULT 8",
                "ai_dj_enabled": "INTEGER NOT NULL DEFAULT 1",
                "ai_model": "TEXT NOT NULL DEFAULT ''",
                "ai_personality": "TEXT NOT NULL DEFAULT ''",
                "ai_max_words": "INTEGER NOT NULL DEFAULT 40",
            }
            for column, definition in additions.items():
                if column not in station_columns:
                    conn.execute(f"ALTER TABLE stations ADD COLUMN {column} {definition}")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS schedule_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    track_id INTEGER,
                    planned_at TEXT NOT NULL,
                    duration_estimate REAL NOT NULL DEFAULT 0,
                    script_text TEXT,
                    audio_path TEXT,
                    ai_generated INTEGER NOT NULL DEFAULT 0,
                    state TEXT NOT NULL DEFAULT 'planned',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_schedule_station_state ON schedule_entries(station_id, state, id);
                CREATE INDEX IF NOT EXISTS idx_schedule_station_time ON schedule_entries(station_id, planned_at);
            """)
            conn.commit()

    def ensure_seed_station(self, settings):
        with self.connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM stations").fetchone()[0]
        if count:
            return
        seed_id = slugify(settings.seed_station_id or settings.seed_station_name)
        self.create_station({
            "id": seed_id,
            "name": settings.seed_station_name,
            "channel_number": settings.seed_station_number,
            "enabled": True,
            "genres_include": settings.seed_allowed_genres,
            "genres_exclude": "",
            "min_year": settings.seed_min_year,
            "max_year": settings.seed_max_year,
            "artists_include": "",
            "artists_exclude": "",
            "artist_repeat_minutes": settings.seed_artist_repeat_minutes,
            "song_repeat_hours": settings.seed_song_repeat_hours,
            "logo_url": "",
            "dj_enabled": True,
            "dj_min_songs": 3,
            "dj_max_songs": 5,
            "dj_voice": "",
            "dj_speed_wpm": 165,
            "station_slogan": "",
            "station_liners": "",
            "station_id_enabled": True,
            "station_id_every_songs": 8,
            "ai_dj_enabled": True,
            "ai_model": "",
            "ai_personality": "Friendly, concise local radio DJ. Natural and upbeat without sounding exaggerated.",
            "ai_max_words": 40,
        })
        # Associate legacy v0.1.0 history with the migrated default station.
        with self._write_lock, self.connection() as conn:
            conn.execute("UPDATE play_history SET station_id=? WHERE station_id IS NULL OR station_id=''", (seed_id,))
            conn.commit()

    def set_state(self, key: str, value: str):
        now = datetime.now(timezone.utc).isoformat()
        with self._write_lock, self.connection() as conn:
            conn.execute(
                """INSERT INTO system_state(key, value, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (key, str(value), now),
            )
            conn.commit()

    def get_state(self, key: str, default=None):
        with self.connection() as conn:
            row = conn.execute("SELECT value FROM system_state WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def begin_scan(self):
        with self._write_lock, self.connection() as conn:
            conn.execute("UPDATE tracks SET scan_seen=0")
            conn.commit()

    def upsert_track(self, track: dict):
        now = datetime.now(timezone.utc).isoformat()
        values = (
            track["path"], track.get("title"), track.get("artist"), track.get("album"),
            track.get("album_artist"), track.get("genre"), track.get("year"),
            float(track.get("duration") or 0), track.get("bitrate"), track.get("sample_rate"),
            int(track.get("file_size") or 0), int(track.get("modified_ns") or 0), now, now,
        )
        with self._write_lock, self.connection() as conn:
            conn.execute(
                """
                INSERT INTO tracks(
                    path,title,artist,album,album_artist,genre,year,duration,bitrate,sample_rate,
                    file_size,modified_ns,scan_seen,playable,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1,1,?,?)
                ON CONFLICT(path) DO UPDATE SET
                    title=excluded.title, artist=excluded.artist, album=excluded.album,
                    album_artist=excluded.album_artist, genre=excluded.genre, year=excluded.year,
                    duration=excluded.duration, bitrate=excluded.bitrate, sample_rate=excluded.sample_rate,
                    file_size=excluded.file_size, modified_ns=excluded.modified_ns,
                    scan_seen=1, playable=1, last_error=NULL, updated_at=excluded.updated_at
                """,
                values,
            )
            conn.commit()

    def mark_seen_unchanged(self, path: str):
        with self._write_lock, self.connection() as conn:
            conn.execute("UPDATE tracks SET scan_seen=1 WHERE path=?", (path,))
            conn.commit()

    def get_file_signature(self, path: str):
        with self.connection() as conn:
            row = conn.execute("SELECT file_size, modified_ns FROM tracks WHERE path=?", (path,)).fetchone()
            return tuple(row) if row else None

    def finish_scan(self) -> int:
        with self._write_lock, self.connection() as conn:
            cur = conn.execute("DELETE FROM tracks WHERE scan_seen=0")
            removed = cur.rowcount
            conn.commit()
            return removed

    def mark_unplayable(self, track_id: int, error: str):
        with self._write_lock, self.connection() as conn:
            conn.execute(
                "UPDATE tracks SET playable=0, last_error=?, updated_at=? WHERE id=?",
                (error[:1000], datetime.now(timezone.utc).isoformat(), track_id),
            )
            conn.commit()

    def add_play(self, track_id: int, client_count: int, station_id: str) -> int:
        with self._write_lock, self.connection() as conn:
            cur = conn.execute(
                "INSERT INTO play_history(track_id, station_id, started_at, client_count) VALUES(?,?,?,?)",
                (track_id, station_id, datetime.now(timezone.utc).isoformat(), client_count),
            )
            conn.commit()
            return cur.lastrowid

    def complete_play(self, history_id: int):
        with self._write_lock, self.connection() as conn:
            conn.execute("UPDATE play_history SET completed=1 WHERE id=?", (history_id,))
            conn.commit()

    def track_count(self) -> int:
        with self.connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM tracks WHERE playable=1").fetchone()[0]

    def stats(self) -> dict:
        with self.connection() as conn:
            tracks = conn.execute("SELECT COUNT(*) FROM tracks WHERE playable=1").fetchone()[0]
            artists = conn.execute("SELECT COUNT(DISTINCT artist) FROM tracks WHERE playable=1 AND artist IS NOT NULL AND artist<>''").fetchone()[0]
            albums = conn.execute("SELECT COUNT(DISTINCT album) FROM tracks WHERE playable=1 AND album IS NOT NULL AND album<>''").fetchone()[0]
            plays = conn.execute("SELECT COUNT(*) FROM play_history").fetchone()[0]
            return {"tracks": tracks, "artists": artists, "albums": albums, "plays": plays}

    def recent_history(self, limit: int = 20, station_id: str | None = None) -> list[dict]:
        where = "WHERE h.station_id=?" if station_id else ""
        params = [station_id] if station_id else []
        params.append(limit)
        with self.connection() as conn:
            rows = conn.execute(
                f"""SELECT h.station_id,h.started_at,h.completed,t.title,t.artist,t.album
                    FROM play_history h JOIN tracks t ON t.id=h.track_id
                    {where}
                    ORDER BY h.id DESC LIMIT ?""",
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def list_tracks(self, limit: int = 100) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT id,title,artist,album,genre,year,duration,path,playable,last_error FROM tracks ORDER BY artist,title LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_genres(self) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute("""
                SELECT genre, COUNT(*) AS count FROM tracks
                WHERE playable=1 AND genre IS NOT NULL AND TRIM(genre)<>''
                GROUP BY genre ORDER BY count DESC, genre COLLATE NOCASE
            """).fetchall()
            return [dict(row) for row in rows]

    def list_artists(self, limit: int = 500) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute("""
                SELECT artist, COUNT(*) AS count FROM tracks
                WHERE playable=1 AND artist IS NOT NULL AND TRIM(artist)<>''
                GROUP BY artist ORDER BY count DESC, artist COLLATE NOCASE LIMIT ?
            """, (limit,)).fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    def _station_dict(row):
        if not row:
            return None
        d = dict(row)
        d["enabled"] = bool(d["enabled"])
        d["dj_enabled"] = bool(d.get("dj_enabled", 1))
        d["station_id_enabled"] = bool(d.get("station_id_enabled", 1))
        d["ai_dj_enabled"] = bool(d.get("ai_dj_enabled", 1))
        return d

    def list_stations(self, enabled_only: bool = False) -> list[dict]:
        where = "WHERE enabled=1" if enabled_only else ""
        with self.connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM stations {where} ORDER BY CAST(channel_number AS INTEGER), channel_number, name COLLATE NOCASE"
            ).fetchall()
            return [self._station_dict(row) for row in rows]

    def get_station(self, station_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM stations WHERE id=?", (station_id,)).fetchone()
            return self._station_dict(row)

    def _unique_station_id(self, requested: str) -> str:
        base = slugify(requested)
        candidate = base
        n = 2
        with self.connection() as conn:
            while conn.execute("SELECT 1 FROM stations WHERE id=?", (candidate,)).fetchone():
                candidate = f"{base[:58]}-{n}"
                n += 1
        return candidate

    @staticmethod
    def _normalize_station_payload(data: dict, *, existing: dict | None = None) -> dict:
        src = dict(existing or {})
        src.update({k: v for k, v in data.items() if k in STATION_FIELDS})
        name = str(src.get("name") or "New Station").strip()[:120]
        def intv(key, default, minimum=0, maximum=9999):
            try:
                return max(minimum, min(int(src.get(key, default)), maximum))
            except (TypeError, ValueError):
                return default
        return {
            "name": name,
            "channel_number": str(src.get("channel_number") or "").strip()[:20],
            "enabled": 1 if bool(src.get("enabled", True)) else 0,
            "genres_include": str(src.get("genres_include") or "").strip()[:2000],
            "genres_exclude": str(src.get("genres_exclude") or "").strip()[:2000],
            "min_year": intv("min_year", 0),
            "max_year": intv("max_year", 0),
            "artists_include": str(src.get("artists_include") or "").strip()[:4000],
            "artists_exclude": str(src.get("artists_exclude") or "").strip()[:4000],
            "artist_repeat_minutes": intv("artist_repeat_minutes", 90, 0, 10080),
            "song_repeat_hours": intv("song_repeat_hours", 12, 0, 8760),
            "logo_url": str(src.get("logo_url") or "").strip()[:1000],
            "dj_enabled": 1 if bool(src.get("dj_enabled", True)) else 0,
            "dj_min_songs": intv("dj_min_songs", 3, 1, 50),
            "dj_max_songs": intv("dj_max_songs", 5, 1, 50),
            "dj_voice": str(src.get("dj_voice") or "").strip()[:200],
            "dj_speed_wpm": intv("dj_speed_wpm", 165, 80, 300),
            "station_slogan": str(src.get("station_slogan") or "").strip()[:300],
            "station_liners": str(src.get("station_liners") or "").strip()[:5000],
            "station_id_enabled": 1 if bool(src.get("station_id_enabled", True)) else 0,
            "station_id_every_songs": intv("station_id_every_songs", 8, 1, 100),
            "ai_dj_enabled": 1 if bool(src.get("ai_dj_enabled", True)) else 0,
            "ai_model": str(src.get("ai_model") or "").strip()[:200],
            "ai_personality": str(src.get("ai_personality") or "").strip()[:4000],
            "ai_max_words": intv("ai_max_words", 40, 10, 100),
        }

    def create_station(self, data: dict) -> dict:
        normalized = self._normalize_station_payload(data)
        requested = str(data.get("id") or normalized["name"])
        station_id = self._unique_station_id(requested)
        now = datetime.now(timezone.utc).isoformat()
        with self._write_lock, self.connection() as conn:
            conn.execute("""
                INSERT INTO stations(
                    id,name,channel_number,enabled,genres_include,genres_exclude,min_year,max_year,
                    artists_include,artists_exclude,artist_repeat_minutes,song_repeat_hours,logo_url,
                    dj_enabled,dj_min_songs,dj_max_songs,dj_voice,dj_speed_wpm,station_slogan,station_liners,
                    station_id_enabled,station_id_every_songs,ai_dj_enabled,ai_model,ai_personality,ai_max_words,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                station_id, normalized["name"], normalized["channel_number"], normalized["enabled"],
                normalized["genres_include"], normalized["genres_exclude"], normalized["min_year"], normalized["max_year"],
                normalized["artists_include"], normalized["artists_exclude"], normalized["artist_repeat_minutes"],
                normalized["song_repeat_hours"], normalized["logo_url"], normalized["dj_enabled"],
                normalized["dj_min_songs"], normalized["dj_max_songs"], normalized["dj_voice"],
                normalized["dj_speed_wpm"], normalized["station_slogan"], normalized["station_liners"],
                normalized["station_id_enabled"], normalized["station_id_every_songs"], normalized["ai_dj_enabled"],
                normalized["ai_model"], normalized["ai_personality"], normalized["ai_max_words"], now, now,
            ))
            conn.commit()
        return self.get_station(station_id)

    def update_station(self, station_id: str, data: dict) -> dict | None:
        existing = self.get_station(station_id)
        if not existing:
            return None
        normalized = self._normalize_station_payload(data, existing=existing)
        now = datetime.now(timezone.utc).isoformat()
        with self._write_lock, self.connection() as conn:
            conn.execute("""
                UPDATE stations SET name=?,channel_number=?,enabled=?,genres_include=?,genres_exclude=?,
                    min_year=?,max_year=?,artists_include=?,artists_exclude=?,artist_repeat_minutes=?,
                    song_repeat_hours=?,logo_url=?,dj_enabled=?,dj_min_songs=?,dj_max_songs=?,dj_voice=?,
                    dj_speed_wpm=?,station_slogan=?,station_liners=?,station_id_enabled=?,station_id_every_songs=?,
                    ai_dj_enabled=?,ai_model=?,ai_personality=?,ai_max_words=?,updated_at=? WHERE id=?
            """, (
                normalized["name"], normalized["channel_number"], normalized["enabled"], normalized["genres_include"],
                normalized["genres_exclude"], normalized["min_year"], normalized["max_year"], normalized["artists_include"],
                normalized["artists_exclude"], normalized["artist_repeat_minutes"], normalized["song_repeat_hours"],
                normalized["logo_url"], normalized["dj_enabled"], normalized["dj_min_songs"],
                normalized["dj_max_songs"], normalized["dj_voice"], normalized["dj_speed_wpm"],
                normalized["station_slogan"], normalized["station_liners"], normalized["station_id_enabled"],
                normalized["station_id_every_songs"], normalized["ai_dj_enabled"], normalized["ai_model"],
                normalized["ai_personality"], normalized["ai_max_words"], now, station_id,
            ))
            conn.commit()
        return self.get_station(station_id)

    def delete_station(self, station_id: str) -> bool:
        with self._write_lock, self.connection() as conn:
            cur = conn.execute("DELETE FROM stations WHERE id=?", (station_id,))
            conn.commit()
            return cur.rowcount > 0


    def clear_future_schedule(self, station_id: str):
        with self._write_lock, self.connection() as conn:
            conn.execute("DELETE FROM schedule_entries WHERE station_id=? AND state IN ('planned','playing')", (station_id,))
            conn.commit()

    def cleanup_schedule(self, keep_completed: int = 200):
        with self._write_lock, self.connection() as conn:
            stations = [r[0] for r in conn.execute("SELECT id FROM stations").fetchall()]
            for sid in stations:
                rows = conn.execute(
                    "SELECT id FROM schedule_entries WHERE station_id=? AND state IN ('completed','skipped') ORDER BY id DESC LIMIT -1 OFFSET ?",
                    (sid, max(0, int(keep_completed))),
                ).fetchall()
                if rows:
                    conn.executemany("DELETE FROM schedule_entries WHERE id=?", [(r[0],) for r in rows])
            conn.commit()

    def add_schedule_entry(self, station_id: str, kind: str, planned_at: str, duration_estimate: float, *, track_id=None, script_text=None, audio_path=None, ai_generated=False):
        now = datetime.now(timezone.utc).isoformat()
        with self._write_lock, self.connection() as conn:
            cur = conn.execute(
                """INSERT INTO schedule_entries(station_id,kind,track_id,planned_at,duration_estimate,script_text,audio_path,ai_generated,state,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?, 'planned', ?, ?)""",
                (station_id, kind, track_id, planned_at, float(duration_estimate or 0), script_text, str(audio_path) if audio_path else None, 1 if ai_generated else 0, now, now),
            )
            conn.commit()
            return cur.lastrowid

    def next_schedule_entry(self, station_id: str):
        with self.connection() as conn:
            row = conn.execute(
                """SELECT s.*,t.path,t.title,t.artist,t.album,t.genre,t.year,t.duration
                   FROM schedule_entries s LEFT JOIN tracks t ON t.id=s.track_id
                   WHERE s.station_id=? AND s.state='planned' ORDER BY s.id LIMIT 1""",
                (station_id,),
            ).fetchone()
            return dict(row) if row else None

    def set_schedule_state(self, entry_id: int, state: str):
        now = datetime.now(timezone.utc).isoformat()
        with self._write_lock, self.connection() as conn:
            conn.execute("UPDATE schedule_entries SET state=?,updated_at=? WHERE id=?", (state, now, int(entry_id)))
            conn.commit()

    def schedule_buffer(self, station_id: str):
        with self.connection() as conn:
            row = conn.execute(
                """SELECT COUNT(*) AS entries,
                          COALESCE(SUM(duration_estimate),0) AS seconds,
                          MAX(planned_at) AS prepared_through,
                          SUM(CASE WHEN kind='music' THEN 1 ELSE 0 END) AS music_entries,
                          SUM(CASE WHEN kind='dj' THEN 1 ELSE 0 END) AS dj_entries
                   FROM schedule_entries WHERE station_id=? AND state='planned'""",
                (station_id,),
            ).fetchone()
            d = dict(row)
            d["hours"] = round(float(d.get("seconds") or 0) / 3600.0, 2)
            return d

    def recent_schedule_scripts(self, station_id: str, limit: int = 6):
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT script_text FROM schedule_entries
                   WHERE station_id=? AND script_text IS NOT NULL AND TRIM(script_text)<>''
                   ORDER BY id DESC LIMIT ?""",
                (station_id, max(1, min(int(limit), 20))),
            ).fetchall()
            return [r[0] for r in rows]

    def scheduled_track_ids(self, station_id: str, limit: int = 250):
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT track_id FROM schedule_entries
                   WHERE station_id=? AND state='planned' AND kind='music' AND track_id IS NOT NULL
                   ORDER BY id DESC LIMIT ?""",
                (station_id, max(1, min(int(limit), 1000))),
            ).fetchall()
            return [r[0] for r in rows]

    def upcoming_schedule(self, station_id: str, limit: int = 20):
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT s.id,s.kind,s.planned_at,s.duration_estimate,s.script_text,s.ai_generated,s.state,
                          t.title,t.artist,t.album,t.year
                   FROM schedule_entries s LEFT JOIN tracks t ON t.id=s.track_id
                   WHERE s.station_id=? AND s.state='planned' ORDER BY s.id LIMIT ?""",
                (station_id, max(1, min(int(limit), 100))),
            ).fetchall()
            return [dict(r) for r in rows]
