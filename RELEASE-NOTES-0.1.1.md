# LocalRadio v0.1.1 — Radio Network

v0.1.1 turns the original one-station engine into a small virtual radio headend. One LocalRadio container can now run multiple independent stations from the same read-only music library.

## Station Builder

Create and manage stations from the browser. Each station stores its configuration in SQLite and can define:

- name and stream ID/slug
- IPTV channel number
- enabled/disabled state
- minimum and maximum release year
- included and excluded genre matches
- included and excluded artist matches
- artist repeat separation in minutes
- song repeat separation in hours
- optional external station-logo URL

The station ID is intentionally immutable after creation because it forms part of the stable stream URL.

## Independent live broadcasters

Every enabled station receives its own centralized `StreamHub`, selector, FFmpeg playout process and subscriber fan-out. Ten listeners on one station still share one broadcast; they do not create ten independent playlists.

Repeat protection is also station-specific. A song playing on `classic-rock` does not incorrectly count as a recent play on `retro-80s`.

## IPTV output

`GET /playlist.m3u` now returns all enabled stations. Example:

```text
#EXTM3U
#EXTINF:-1 tvg-id="retro-80s" tvg-chno="801" group-title="Local Radio",Retro 80s
http://SERVER:8095/stream/retro-80s.mp3
#EXTINF:-1 tvg-id="classic-rock" tvg-chno="802" group-title="Local Radio",Classic Rock
http://SERVER:8095/stream/classic-rock.mp3
```

When a station logo URL is configured, it is emitted as `tvg-logo`.

## Upgrade from v0.1.0

Keep the existing `/data` volume. At startup v0.1.1 automatically adds the new schema needed for multiple stations. If no station records exist, the old `STATION_*`, `ARTIST_REPEAT_MINUTES`, `SONG_REPEAT_HOURS`, `MIN_YEAR`, `MAX_YEAR` and `ALLOWED_GENRES` environment variables seed the first station. Existing v0.1.0 play history is associated with that migrated station.

After migration, edit station settings through the Station Builder. Global audio/scanner settings remain environment variables.

## Deployment compatibility

- Docker / Docker Compose
- CasaOS
- GHCR workflow
- linux/amd64
- linux/arm64
- read-only `/music`
- persistent `/data`
- PUID/PGID entrypoint

## Next planned release

v0.1.2 is reserved for local TTS DJs, station IDs/liners, cached generated announcement audio and fallback voice behavior.
