# Changelog

## v0.1.1 — Radio Network

- Added persistent multi-station support.
- Added the web Station Builder for creating, editing, deleting, enabling and disabling stations.
- Added independent centralized FFmpeg broadcaster and listener fan-out for each enabled station.
- Added per-station channel number and immutable stream slug/ID.
- Added per-station minimum/maximum year filters.
- Added comma-separated genre include and exclude filters.
- Added comma-separated artist include and exclude filters.
- Added per-station artist and song repeat-protection windows.
- Added optional station logo URL and `tvg-logo` output in M3U.
- Added eligible-track counts and per-station live/listener/status cards.
- `playlist.m3u` now includes every enabled station.
- Added station-specific history API.
- Added library genre/artist options API for Station Builder suggestions.
- Added v0.1.0 database migration: the existing station is imported as the first v0.1.1 station and legacy history is assigned to it.
- Preserved read-only `/music`, PUID/PGID, CasaOS, GHCR amd64/arm64, health check, incremental scans and persistent catalog behavior.

## v0.1.0 — Core Radio Engine

- Initial Docker/CasaOS release.
- SQLite music catalog, incremental scanner, single central station, FFmpeg MP3 playout, repeat protection, play history, M3U endpoint and status dashboard.
