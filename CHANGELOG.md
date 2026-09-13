# Changelog

## v0.2.0 — Ollama AI DJs & Advance Scheduling

- Added Ollama AI DJ scripting with `qwen3:4b` as the recommended/default model.
- Added per-station AI enable/disable, model override, personality prompt and maximum-word controls.
- Added persistent SQLite `schedule_entries` queue for music, DJ breaks and station IDs.
- Added configurable minimum/target future programming buffers; defaults are 6 and 24 hours.
- Added pre-generation of DJ scripts and local TTS assets before airtime.
- Added previous/next-track context, planned local airtime and recent-script avoidance to AI prompts.
- Added grounding rules that prohibit unsupported chart, award, biography, weather, news and trivia claims.
- Added short retry, timeout, consecutive-failure tracking and circuit-breaker behavior for Ollama.
- Retained v0.1.2 deterministic DJ templates as the automatic Ollama fallback.
- Retained Piper/eSpeak and prerecorded station-imaging fallbacks.
- Added emergency music playout when the prepared queue is temporarily empty.
- Added per-station schedule buffer status and AI-queue counts to the dashboard.
- Added dashboard Ollama status plus Test Ollama/Test Model controls.
- Added per-station Rebuild Schedule control and REST endpoints.
- Saving station settings or rescanning the music library invalidates future schedule entries and regenerates them.
- Added automatic v0.1.2 database migration for AI fields and the new schedule table.
- Added Docker/CasaOS `host.docker.internal:host-gateway` mapping and Ollama environment controls.
- Preserved read-only `/music`, PUID/PGID, multi-station M3U, GHCR amd64/arm64 and health checks.

## v0.1.2 — Local TTS DJs & Station Imaging

- Added local TTS DJ breaks with deterministic previous/next-track announcement templates.
- Added Piper TTS 1.8.0 to the container and retained bundled eSpeak NG as an automatic fallback.
- Added per-station DJ enable/disable, minimum/maximum songs between breaks, voice, and eSpeak WPM controls.
- Added per-station slogans.
- Added scheduled station IDs with configurable song intervals.
- Added multiple generated liner templates with `{station}` and `{slogan}` substitutions.
- Added custom prerecorded station imaging under `/config/imaging/<station-id>/`.
- Added persistent `/config` volume for imaging and Piper voice models.
- Added persistent TTS cache under `/data/tts-cache`.
- Added announcement prefetching during the currently playing song to avoid normal TTS generation gaps.
- Added automatic station-ID/liner cache prewarming at station startup.
- Added browser voice preview endpoint and Station Builder control.
- Added TTS/imaging status to the dashboard, including DJ break and station-ID counters.
- Added automatic v0.1.1 database migration for all new DJ/imaging fields.
- TTS failure is non-fatal: Piper falls back to eSpeak NG, and failed/late announcements are skipped while music continues.

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
