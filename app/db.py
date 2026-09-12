import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


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
    started_at TEXT NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0,
    client_count INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_history_started ON play_history(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_track ON play_history(track_id, started_at DESC);

CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.RLock()
        self.init()

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
            conn.executescript(SCHEMA)
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
            row = conn.execute(
                "SELECT file_size, modified_ns FROM tracks WHERE path=?", (path,)
            ).fetchone()
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

    def add_play(self, track_id: int, client_count: int) -> int:
        with self._write_lock, self.connection() as conn:
            cur = conn.execute(
                "INSERT INTO play_history(track_id, started_at, client_count) VALUES(?,?,?)",
                (track_id, datetime.now(timezone.utc).isoformat(), client_count),
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
            artists = conn.execute(
                "SELECT COUNT(DISTINCT artist) FROM tracks WHERE playable=1 AND artist IS NOT NULL AND artist<>''"
            ).fetchone()[0]
            albums = conn.execute(
                "SELECT COUNT(DISTINCT album) FROM tracks WHERE playable=1 AND album IS NOT NULL AND album<>''"
            ).fetchone()[0]
            plays = conn.execute("SELECT COUNT(*) FROM play_history").fetchone()[0]
            return {"tracks": tracks, "artists": artists, "albums": albums, "plays": plays}

    def recent_history(self, limit: int = 20) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT h.started_at,h.completed,t.title,t.artist,t.album
                   FROM play_history h JOIN tracks t ON t.id=h.track_id
                   ORDER BY h.id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_tracks(self, limit: int = 100) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT id,title,artist,album,genre,year,duration,path,playable,last_error FROM tracks ORDER BY artist,title LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]
