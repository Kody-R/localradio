# LocalRadio v0.2.0

LocalRadio turns a local music library into continuous self-hosted radio stations for IPTV, Jellyfin and VLC. v0.2.0 adds **Ollama AI DJs and persistent advance scheduling** while retaining the deterministic TTS/imaging system from v0.1.2 as the reliability fallback.

## v0.2.0 highlights

- Ollama-written DJ breaks with a different personality for each station
- Recommended default model: `qwen3:4b`
- Per-station Ollama model override
- `think: false` requests for short, fast DJ copy
- Persistent future schedule stored in SQLite
- Default 6-hour minimum / 24-hour target schedule buffer
- DJ scripts and TTS assets generated before airtime
- Previous-song back-announces and next-song teases
- Planned-airtime context for time-aware copy
- Recent-script avoidance to reduce repetitive DJ phrasing
- Strict per-station maximum word count
- Two-attempt Ollama request path with timeout and circuit breaker
- Deterministic v0.1.2 DJ templates when Ollama is unavailable
- Piper/eSpeak TTS fallback retained
- Prerecorded imaging fallback retained
- Emergency music playout if the prepared queue ever runs dry
- Dashboard status for Ollama, TTS and per-station schedule buffers
- **Test Ollama** and **Rebuild Schedule** controls
- Automatic in-place migration from v0.1.2
- All v0.1.x multi-station, M3U, CasaOS and GHCR functionality retained

## Recommended Ollama model

For a 16 GB Ollama host, start with:

```bash
ollama pull qwen3:4b
```

LocalRadio defaults to:

```text
OLLAMA_MODEL=qwen3:4b
```

The AI workload is intentionally small: each request normally produces only 1-2 sentences. A larger model is optional, not required.

If you later want to try more elaborate personalities and your Ollama host has enough spare memory, you can set a station to another installed model from the Station Builder without rebuilding the Docker image.

## Architecture

```text
                     /music (read only)
                            |
                            v
                    SQLite music catalog
                            |
                            v
                   Advance Scheduler
                    /             \
                   /               \
             Music selector       Break planner
                   |                |
                   |           Ollama AI DJ
                   |                |
                   |          deterministic fallback
                   |                |
                   |             Piper / eSpeak
                   |                |
                   +--------+-------+
                            |
                            v
                  SQLite prepared schedule
                  music / DJ / IDs / music
                            |
                            v
                    live FFmpeg playout
                            |
                            v
                       IPTV clients
```

The critical reliability rule is that **Ollama is not in the live playback path**. The advance scheduler writes scripts and generates speech before the break is needed. The broadcaster consumes prepared entries from SQLite.

If Ollama is unavailable:

```text
Ollama AI script
      |
      X
      v
v0.1.2 deterministic DJ template
      |
      v
local TTS
      |
      X
      v
prerecorded imaging if available
      |
      X
      v
skip voice break and keep playing music
```

If the entire prepared schedule is temporarily empty, LocalRadio plays an emergency music track immediately while the future queue rebuilds in another thread.

## Quick start

1. Install Ollama on the device that will generate DJ copy.
2. Pull the recommended model:

```bash
ollama pull qwen3:4b
```

3. Make sure the LocalRadio container can reach Ollama. See **Ollama networking** below.
4. Edit `docker-compose.yml` and change the music path.
5. Start LocalRadio:

```bash
docker compose up -d --build
```

6. Open:

```text
http://SERVER-IP:8095/
```

7. Use **Test Ollama** on the dashboard.
8. Add the generated playlist to Jellyfin/VLC/your IPTV client:

```text
http://SERVER-IP:8095/playlist.m3u
```

Direct station stream:

```text
http://SERVER-IP:8095/stream/<station-id>.mp3
```

## Ollama networking

### Ollama on the same Linux/CasaOS host

The Compose files include:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

and default to:

```text
OLLAMA_URL=http://host.docker.internal:11434
```

Ollama must listen on an address reachable from Docker. If your Ollama service is bound only to `127.0.0.1`, configure the Ollama service to listen on the host network, for example:

```text
OLLAMA_HOST=0.0.0.0:11434
```

Keep port 11434 restricted to your trusted LAN/firewall; do not expose it directly to the public internet.

### Ollama on another PC

Use that computer's LAN IP:

```text
OLLAMA_URL=http://192.168.1.50:11434
```

The Ollama host must allow the LocalRadio/CasaOS machine to reach TCP port 11434.

## AI DJ configuration

Each station has these v0.2.0 settings:

```text
Enable AI-written DJ breaks: Yes
Ollama model:                blank = global default
Maximum words per break:     40
DJ personality:              custom text
```

Example personality:

```text
Warm, energetic American FM DJ. Mention artists naturally. Keep transitions
short and conversational. Avoid internet slang, exaggerated hype and repetitive
phrasing.
```

A different station might use:

```text
Quiet late-night host. Understated and relaxed. Short sentences. Mention the
artist and song naturally, with very little hype.
```

LocalRadio adds its own safety/grounding prompt around this text. The model is instructed to use only supplied metadata and **not invent** chart positions, awards, biographies, weather, news or music trivia.

## What Ollama receives

A normal break is generated from structured facts such as:

```text
station: Retro 80s
slogan: The soundtrack of the 1980s
previous_artist: Tears for Fears
previous_title: Everybody Wants to Rule the World
previous_album: Songs from the Big Chair
previous_year: 1985
next_artist: The Cars
next_title: Drive
next_year: 1984
local_time: Saturday 7:42 PM
```

LocalRadio also includes several recent DJ scripts and tells the model to avoid echoing them.

## Ollama reliability controls

Global environment variables:

```text
OLLAMA_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen3:4b
OLLAMA_TIMEOUT_SECONDS=45
OLLAMA_FAILURE_THRESHOLD=3
OLLAMA_CIRCUIT_SECONDS=300
OLLAMA_KEEP_ALIVE=30m
```

Behavior:

1. LocalRadio tries the request.
2. One short retry is allowed.
3. Repeated failures open the circuit breaker.
4. During the breaker period, LocalRadio immediately uses deterministic DJ copy instead of repeatedly waiting for a dead Ollama server.
5. Successful requests automatically reset the failure counter.

## Advance scheduling

Defaults:

```text
SCHEDULE_MIN_HOURS=6
SCHEDULE_TARGET_HOURS=24
SCHEDULE_CHECK_SECONDS=60
```

The scheduler first tries to establish the minimum healthy buffer, then continues filling toward the target in smaller background batches.

Schedule entries are stored in SQLite and can include:

```text
music
DJ break
station ID
music
```

The Station cards show their current prepared hours. **Rebuild Schedule** deletes only future planned entries and generates a new queue from the latest station settings.

Saving a station automatically invalidates and rebuilds its future schedule.

A music-library rescan also rebuilds future schedules so deleted or newly discovered files are reflected in upcoming programming.

## Station Builder

Existing music/rotation settings remain available:

```text
Name / channel number
Year filters
Genre include/exclude
Artist include/exclude
Artist separation
Song separation
Logo URL
```

DJ/TTS settings:

```text
Enable DJ breaks
Minimum songs between breaks
Maximum songs between breaks
Piper/eSpeak voice
Voice speed
Station slogan
Station IDs
Generated liners
Custom prerecorded imaging
```

New v0.2.0 AI settings:

```text
Enable AI-written DJ breaks
Per-station Ollama model override
DJ personality
Maximum words per break
Test Model
```

## Local TTS

v0.2.0 retains the complete v0.1.2 TTS path.

### Piper

The image includes `piper-tts`. Download a model into the persistent voice directory:

```bash
docker exec -it localradio python -m piper.download_voices \
  --data-dir /config/voices en_US-lessac-medium
```

Then choose:

```text
en_US-lessac-medium
```

in Station Builder.

### eSpeak NG

eSpeak NG ships in the container and is the zero-setup local fallback.

Example:

```text
en-us
```

### TTS cache

Generated speech is cached under:

```text
/data/tts-cache
```

Identical text/voice requests reuse the cached file after restarts.

## Custom prerecorded imaging

Per-station imaging lives under:

```text
/config/imaging/<station-id>/
```

Example:

```text
/config/imaging/retro-80s/retro80s-id-01.wav
/config/imaging/retro-80s/retro80s-sweeper-02.mp3
```

Supported imaging formats include:

```text
.wav .mp3 .ogg .opus .flac .m4a .aac
```

## Volumes

```text
/music   read-only music collection
/data    SQLite DB, schedules, play history and TTS cache
/config  Piper voices and station imaging
```

Typical Compose mappings:

```yaml
volumes:
  - ./data:/data
  - ./config:/config
  - /path/to/your/music:/music:ro
```

LocalRadio never modifies `/music`.

## Database migration

The v0.2.0 database upgrade is automatic.

A v0.1.2 database receives:

- `ai_dj_enabled`
- `ai_model`
- `ai_personality`
- `ai_max_words`
- the new `schedule_entries` table

Existing tracks, stations, TTS settings and play history are preserved.

## IPTV output

All enabled stations remain in one playlist:

```text
http://SERVER-IP:8095/playlist.m3u
```

Example:

```text
#EXTM3U
#EXTINF:-1 tvg-id="retro-80s" tvg-chno="801" group-title="Local Radio",Retro 80s
http://SERVER-IP:8095/stream/retro-80s.mp3
```

## CasaOS

Use `docker-compose.casaos.yml` and replace:

```text
ghcr.io/YOUR_GITHUB_USERNAME/localradio:v0.2.0
```

with your GHCR path.

Also change:

```text
/CHANGE/ME/TO/YOUR/MUSIC
```

to the host path containing your music library.

The CasaOS definition exposes the important Ollama and scheduling variables in addition to the existing audio/TTS options.

## GHCR

The included GitHub Actions workflow builds:

```text
linux/amd64
linux/arm64
```

Push to `main` for `latest`, or create a version tag such as:

```bash
git tag v0.2.0
git push origin v0.2.0
```

## HTTP API additions

```text
GET  /api/ollama
POST /api/ollama/test
GET  /api/stations/<id>/schedule
POST /api/stations/<id>/schedule/rebuild
```

Existing status, station, library, TTS, M3U and stream endpoints remain available.

## Operational notes

- One central broadcaster exists per enabled station. Multiple listeners receive the same live bytes; listeners do not create independent station timelines.
- FFmpeg performs live MP3 transcoding.
- Speech/imaging entries never create music play-history records.
- Repeat protection is still based on actual music play history. The more advanced A/B/C weighted rotation engine remains planned for v0.2.1.
- The scheduler is intentionally conservative about AI facts. Rich external music trivia/metadata is not part of v0.2.0.
