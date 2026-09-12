import random
from datetime import datetime, timedelta, timezone


class StationSelector:
    def __init__(self, db, settings):
        self.db = db
        self.settings = settings

    def _base_where(self):
        clauses = ["t.playable=1"]
        params = []
        if self.settings.min_year > 0:
            clauses.append("COALESCE(t.year,0) >= ?")
            params.append(self.settings.min_year)
        if self.settings.max_year > 0:
            clauses.append("COALESCE(t.year,9999) <= ?")
            params.append(self.settings.max_year)
        if self.settings.allowed_genres:
            genre_parts = []
            for genre in self.settings.allowed_genres:
                genre_parts.append("LOWER(COALESCE(t.genre,'')) LIKE ?")
                params.append(f"%{genre}%")
            clauses.append("(" + " OR ".join(genre_parts) + ")")
        return clauses, params

    def choose_next(self):
        now = datetime.now(timezone.utc)
        song_cutoff = (now - timedelta(hours=self.settings.song_repeat_hours)).isoformat()
        artist_cutoff = (now - timedelta(minutes=self.settings.artist_repeat_minutes)).isoformat()
        clauses, params = self._base_where()

        strict_sql = f"""
            SELECT t.* FROM tracks t
            WHERE {' AND '.join(clauses)}
              AND NOT EXISTS (
                SELECT 1 FROM play_history h
                WHERE h.track_id=t.id AND h.started_at >= ?
              )
              AND NOT EXISTS (
                SELECT 1 FROM play_history h2
                JOIN tracks t2 ON t2.id=h2.track_id
                WHERE LOWER(COALESCE(t2.artist,''))=LOWER(COALESCE(t.artist,''))
                  AND h2.started_at >= ?
              )
            ORDER BY RANDOM() LIMIT 50
        """
        with self.db.connection() as conn:
            rows = conn.execute(strict_sql, [*params, song_cutoff, artist_cutoff]).fetchall()
            if rows:
                return dict(random.choice(rows))

            # Small libraries may not satisfy both repeat windows. Preserve song separation first.
            relaxed_artist_sql = f"""
                SELECT t.* FROM tracks t
                WHERE {' AND '.join(clauses)}
                  AND NOT EXISTS (
                    SELECT 1 FROM play_history h
                    WHERE h.track_id=t.id AND h.started_at >= ?
                  )
                ORDER BY RANDOM() LIMIT 50
            """
            rows = conn.execute(relaxed_artist_sql, [*params, song_cutoff]).fetchall()
            if rows:
                return dict(random.choice(rows))

            # Final fallback for very small libraries: any eligible playable track.
            rows = conn.execute(
                f"SELECT t.* FROM tracks t WHERE {' AND '.join(clauses)} ORDER BY RANDOM() LIMIT 50",
                params,
            ).fetchall()
            return dict(random.choice(rows)) if rows else None
