import random
from datetime import datetime, timedelta, timezone


def _csv(value: str) -> list[str]:
    return [part.strip().lower() for part in (value or "").split(",") if part.strip()]


class StationSelector:
    def __init__(self, db, station: dict):
        self.db = db
        self.station = station

    def _base_where(self):
        s = self.station
        clauses = ["t.playable=1"]
        params = []
        if int(s.get("min_year") or 0) > 0:
            clauses.append("COALESCE(t.year,0) >= ?")
            params.append(int(s["min_year"]))
        if int(s.get("max_year") or 0) > 0:
            clauses.append("COALESCE(t.year,9999) <= ?")
            params.append(int(s["max_year"]))

        include_genres = _csv(s.get("genres_include", ""))
        if include_genres:
            parts = []
            for genre in include_genres:
                parts.append("LOWER(COALESCE(t.genre,'')) LIKE ?")
                params.append(f"%{genre}%")
            clauses.append("(" + " OR ".join(parts) + ")")

        for genre in _csv(s.get("genres_exclude", "")):
            clauses.append("LOWER(COALESCE(t.genre,'')) NOT LIKE ?")
            params.append(f"%{genre}%")

        include_artists = _csv(s.get("artists_include", ""))
        if include_artists:
            parts = []
            for artist in include_artists:
                parts.append("LOWER(COALESCE(t.artist,'')) LIKE ?")
                params.append(f"%{artist}%")
            clauses.append("(" + " OR ".join(parts) + ")")

        for artist in _csv(s.get("artists_exclude", "")):
            clauses.append("LOWER(COALESCE(t.artist,'')) NOT LIKE ?")
            params.append(f"%{artist}%")
        return clauses, params

    def eligible_track_count(self) -> int:
        clauses, params = self._base_where()
        with self.db.connection() as conn:
            return conn.execute(
                f"SELECT COUNT(*) FROM tracks t WHERE {' AND '.join(clauses)}", params
            ).fetchone()[0]

    def choose_next(self):
        s = self.station
        now = datetime.now(timezone.utc)
        song_cutoff = (now - timedelta(hours=int(s.get("song_repeat_hours") or 0))).isoformat()
        artist_cutoff = (now - timedelta(minutes=int(s.get("artist_repeat_minutes") or 0))).isoformat()
        clauses, params = self._base_where()
        sid = s["id"]

        strict_sql = f"""
            SELECT t.* FROM tracks t
            WHERE {' AND '.join(clauses)}
              AND NOT EXISTS (
                SELECT 1 FROM play_history h
                WHERE h.track_id=t.id AND h.station_id=? AND h.started_at >= ?
              )
              AND NOT EXISTS (
                SELECT 1 FROM play_history h2
                JOIN tracks t2 ON t2.id=h2.track_id
                WHERE h2.station_id=?
                  AND LOWER(COALESCE(t2.artist,''))=LOWER(COALESCE(t.artist,''))
                  AND h2.started_at >= ?
              )
            ORDER BY RANDOM() LIMIT 50
        """
        with self.db.connection() as conn:
            rows = conn.execute(strict_sql, [*params, sid, song_cutoff, sid, artist_cutoff]).fetchall()
            if rows:
                return dict(random.choice(rows))

            relaxed_artist_sql = f"""
                SELECT t.* FROM tracks t
                WHERE {' AND '.join(clauses)}
                  AND NOT EXISTS (
                    SELECT 1 FROM play_history h
                    WHERE h.track_id=t.id AND h.station_id=? AND h.started_at >= ?
                  )
                ORDER BY RANDOM() LIMIT 50
            """
            rows = conn.execute(relaxed_artist_sql, [*params, sid, song_cutoff]).fetchall()
            if rows:
                return dict(random.choice(rows))

            rows = conn.execute(
                f"SELECT t.* FROM tracks t WHERE {' AND '.join(clauses)} ORDER BY RANDOM() LIMIT 50",
                params,
            ).fetchall()
            return dict(random.choice(rows)) if rows else None
