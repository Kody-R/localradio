# LocalRadio v0.1.1

LocalRadio turns one local music library into multiple continuous self-hosted radio stations. It scans common audio files into SQLite, lets you build station rules in a web UI, applies station-specific repeat protection, transcodes tracks in real time with FFmpeg, and exposes the enabled stations through one IPTV-style M3U playlist.

## v0.1.1 features

- Multiple independent stations from one library
- Web Station Builder: create, edit, delete, enable and disable
- Per-station channel number and stable stream slug
- Per-station year range
- Genre include/exclude filters
- Artist include/exclude filters
- Per-station artist/song repeat protection
- Optional station logo URL / M3U `tvg-logo`
- Per-station now playing, listeners, errors, eligible-track count and run play count
- One centralized stream per station shared by all listeners
- All enabled stations generated in `/playlist.m3u`
- Persistent station definitions and play history in SQLite
- Automatic migration from v0.1.0
- Read-only `/music`; persistent `/data`
- Incremental music-library rescans
- Docker, CasaOS and GHCR amd64/arm64 support

## Architecture

```text
                         /music (read only)
                               |
                               v
                        Library Scanner
                               |
                               v
                    SQLite /data/localradio.db
                               |
               +---------------+---------------+
               |               |               |
               v               v               v
          Retro 80s       Classic Rock       Chill FM
          Selector         Selector           Selector
               |               |               |
             FFmpeg          FFmpeg          FFmpeg
               |               |               |
          Stream Hub       Stream Hub       Stream Hub
               |               |               |
     /stream/retro-80s   /stream/classic-rock   ...
               \               |               /
                +--------------+--------------+
                               |
                         /playlist.m3u
```

Each station selects and records a song once, regardless of how many clients are listening to it.

## Quick start

1. Edit `docker-compose.yml` and replace `/path/to/your/music`.
2. Start the container:

```bash
docker compose up -d --build
```

3. Open the Station Builder/dashboard:

```text
http://SERVER-IP:8095/
```

4. Add the generated IPTV playlist to Jellyfin/VLC/another IPTV client:

```text
http://SERVER-IP:8095/playlist.m3u
```

A direct station URL is:

```text
http://SERVER-IP:8095/stream/<station-id>.mp3
```

## Building stations

Choose **New Station** in the dashboard. A station can match the whole library or a filtered subset.

Example Retro 80s station:

```text
Name: Retro 80s
ID: retro-80s
Channel: 801
Minimum year: 1980
Maximum year: 1989
Include genres: Rock, Pop, New Wave
Exclude genres: Christmas
Artist separation: 90 minutes
Song separation: 12 hours
```

Filters are case-insensitive substring matches. Comma-separated include values are OR rules; excludes remove matches.

## Upgrade from v0.1.0

Use the same `/data` mapping and replace the image with v0.1.1. LocalRadio performs an in-place schema migration.

- Your track catalog remains intact.
- Existing history remains intact.
- The old v0.1.0 station becomes the first v0.1.1 station.
- Legacy history is tagged to that station.
- Old station environment variables are only used to seed a station when the station table is empty.

After upgrading, use the web Station Builder for station settings.

## CasaOS / GHCR

Edit `docker-compose.casaos.yml`:

```text
ghcr.io/YOUR_GITHUB_USERNAME/localradio:v0.1.1
```

and change:

```text
/CHANGE/ME/TO/YOUR/MUSIC
```

The default persistent mapping is:

```text
/DATA/AppData/localradio/data -> /data
```

The music mapping remains read-only.

## Environment variables

Global container settings:

| Variable | Default | Purpose |
|---|---:|---|
| `PUID` | `1000` | Runtime UID and `/data` owner |
| `PGID` | `1000` | Runtime GID |
| `MUSIC_DIR` | `/music` | Music root inside container |
| `DATA_DIR` | `/data` | Persistent data root |
| `BITRATE_KBPS` | `192` | MP3 bitrate used by all stations |
| `SAMPLE_RATE` | `44100` | MP3 output sample rate |
| `AUTO_SCAN_ON_START` | `true` | Scan on container startup |
| `AUTO_START_BROADCAST` | `true` | Start enabled broadcasters |
| `SCAN_INTERVAL_HOURS` | `24` | Recurring scan period; `0` disables |
| `TZ` | deployment choice | Container timezone |

Compatibility/first-station seed variables from v0.1.0 are still accepted: `STATION_NAME`, `STATION_ID`, `STATION_NUMBER`, `ARTIST_REPEAT_MINUTES`, `SONG_REPEAT_HOURS`, `MIN_YEAR`, `MAX_YEAR`, and `ALLOWED_GENRES`.

## API

- `GET /health` — health, catalog count and station counts
- `GET /api/status` — network/dashboard state
- `POST /api/scan` — start a music scan
- `GET /api/tracks?limit=100` — inspect tracks
- `GET /api/library/options` — genre/artist suggestions
- `GET /api/stations` — list station definitions + live status
- `POST /api/stations` — create station
- `GET /api/stations/<id>` — station + status + recent history
- `PUT /api/stations/<id>` — edit station
- `DELETE /api/stations/<id>` — delete station definition
- `GET /api/stations/<id>/history` — station-specific history
- `GET /playlist.m3u` — all enabled stations
- `GET /stream/<id>.mp3` — live station stream

## Resource behavior

Each enabled station runs one FFmpeg process while broadcasting. CPU use therefore scales primarily with the number of enabled stations, not the number of listeners. Disable stations you are not using on low-power hardware.

## GitHub Container Registry

The supplied workflow publishes `linux/amd64` and `linux/arm64` images. For this release:

```bash
git tag v0.1.1
git push origin v0.1.1
```

## Roadmap

- v0.1.2 — local TTS DJs, station IDs and liners
- v0.2.0 — Ollama DJ scripting + advance scheduling
- v0.2.1 — weighted A/B/C rotation
- v0.2.2 — broadcast clocks
- v0.2.3 — Music Choice-style video presentation
- v0.2.4 — XMLTV/Jellyfin guide integration
- v0.2.5 — dayparts/programming
- v0.3.0 — automatic station/network builder
