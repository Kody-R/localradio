# LocalRadio v0.1.0

LocalRadio turns a local music library into one continuous self-hosted radio station. It scans common audio formats into SQLite, applies configurable song and artist repeat protection, transcodes tracks in real time with FFmpeg, and exposes an MP3 broadcast plus an IPTV-style M3U playlist.

This first release deliberately focuses on the radio engine. Multi-station management, TTS DJs, Ollama scripting, broadcast clocks, video/album-art channels and XMLTV are later roadmap items.

## v0.1.0 features

- Docker and CasaOS friendly
- amd64 + arm64 GHCR workflow
- Read-only `/music` mount
- Persistent SQLite catalog in `/data`
- MP3, FLAC, M4A/MP4, OGG, Opus, WAV, AAC, WMA, AIFF and APE discovery
- Incremental rescans using file size + modification timestamp
- Automatic removal of catalog entries whose files were deleted
- One continuous central station shared by all listeners
- FFmpeg normalization/transcoding to constant-bitrate MP3
- Artist repeat protection
- Song repeat protection
- Optional year and genre filters
- Persistent play history
- Automatic startup scan
- Scheduled library rescans
- M3U endpoint for IPTV/Jellyfin/VLC clients
- Direct live MP3 endpoint
- Responsive status dashboard
- Health/status APIs

## Architecture

```text
/music (read only)
      |
      v
Library Scanner ----> SQLite catalog (/data/localradio.db)
                           |
                           v
                    Station Selector
                           |
                 repeat protection
                           |
                           v
                         FFmpeg
                           |
                           v
                     Central Stream Hub
                      /            \
                     /              \
            /playlist.m3u     /stream/localradio.mp3
```

All connected listeners receive the same live audio. Track selection and play-history recording happen once at the station level, not separately per client.

## Quick start with Docker Compose

1. Edit `docker-compose.yml`.
2. Replace `/path/to/your/music` with the host path containing your music.
3. Start LocalRadio:

```bash
docker compose up -d --build
```

4. Open:

```text
http://SERVER-IP:8095/
```

5. IPTV playlist:

```text
http://SERVER-IP:8095/playlist.m3u
```

6. Direct stream:

```text
http://SERVER-IP:8095/stream/localradio.mp3
```

The initial scan may take some time on a very large library. The web dashboard stays available while scanning.

## CasaOS / GHCR

The repository includes `docker-compose.casaos.yml` and a GitHub Actions workflow.

Before using the CasaOS compose file, change:

```text
ghcr.io/YOUR_GITHUB_USERNAME/localradio:v0.1.0
```

to your actual GHCR repository, and change:

```text
/CHANGE/ME/TO/YOUR/MUSIC
```

to the host music path.

A typical CasaOS data mapping is already provided:

```text
/DATA/AppData/localradio/data -> /data
```

The music mount is read-only by design.

## Environment variables

| Variable | Default | Purpose |
|---|---:|---|
| `PUID` | `1000` | UID used for the application process and `/data` ownership |
| `PGID` | `1000` | GID used for the application process and `/data` ownership |
| `MUSIC_DIR` | `/music` | Container music root |
| `DATA_DIR` | `/data` | Persistent app-data root |
| `STATION_NAME` | `LocalRadio` | Display name |
| `STATION_ID` | `localradio` | Stable ID used in stream/M3U URLs |
| `STATION_NUMBER` | `801` | IPTV channel number |
| `ARTIST_REPEAT_MINUTES` | `90` | Preferred same-artist separation |
| `SONG_REPEAT_HOURS` | `12` | Preferred same-track separation |
| `BITRATE_KBPS` | `192` | Output MP3 bitrate |
| `SAMPLE_RATE` | `44100` | Output sample rate |
| `AUTO_SCAN_ON_START` | `true` | Scan library when the container starts |
| `AUTO_START_BROADCAST` | `true` | Start playout automatically |
| `SCAN_INTERVAL_HOURS` | `24` | Rescan interval; `0` disables recurring scans |
| `MIN_YEAR` | `0` | Minimum year; `0` disables lower bound |
| `MAX_YEAR` | `0` | Maximum year; `0` disables upper bound |
| `ALLOWED_GENRES` | empty | Comma-separated case-insensitive genre matches |
| `TZ` | host choice | Container timezone |

Example genre filter:

```yaml
ALLOWED_GENRES: "Rock,Classic Rock,Alternative"
```

## Repeat-protection behavior

LocalRadio first tries to select a track satisfying both the artist and song separation windows. On small libraries, if that becomes impossible, it relaxes artist separation while preserving song separation. If the library is too small even for the song window, it falls back to any eligible playable track rather than stopping the station.

## API endpoints

- `GET /health` — lightweight health response
- `GET /api/status` — station, library, scan, playout and recent-play state
- `POST /api/scan` — start an asynchronous library rescan
- `GET /api/tracks?limit=100` — inspect cataloged tracks
- `GET /playlist.m3u` — IPTV playlist
- `GET /stream/<station-id>.mp3` — continuous live MP3 stream

## Logs

```bash
docker logs -f localradio
```

Useful messages include the library scan summary, current track, FFmpeg errors and tracks marked unplayable.

## Permissions

Find the UID/GID that should own LocalRadio's persistent data if needed:

```bash
id
```

Then set `PUID` and `PGID` in Compose. That UID/GID must have read access to the host music path. LocalRadio never writes to `/music`.

## GitHub Container Registry

Push this source to a GitHub repository. The included workflow builds `linux/amd64` and `linux/arm64` images and publishes them to GHCR on pushes to `main`, version tags, or manual workflow runs.

For a release tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Then use the generated GHCR image in CasaOS.

## v0.1.x / v0.2 roadmap

- v0.1.1 — multiple stations + station builder UI
- v0.1.2 — local TTS DJs + liners/station IDs
- v0.2.0 — Ollama DJ scripting + advance schedule generation
- v0.2.1 — weighted A/B/C rotation
- v0.2.2 — broadcast clocks
- v0.2.3 — Music Choice-style video presentation
- v0.2.4 — XMLTV/Jellyfin guide integration
- v0.2.5 — dayparts and programming blocks
- v0.3.0 — automatic station/network builder
