# LocalRadio v0.2.0 — Ollama AI DJs & Advance Scheduling

v0.2.0 moves DJ generation out of the live playback path. Each enabled station now maintains a persistent future schedule containing music, DJ breaks and station IDs. Ollama scripts and TTS audio are prepared ahead of airtime, while v0.1.2 deterministic speech remains available as an automatic fail-safe.

## Recommended model

```bash
ollama pull qwen3:4b
```

Default container configuration:

```text
OLLAMA_MODEL=qwen3:4b
OLLAMA_URL=http://host.docker.internal:11434
```

The LocalRadio Ollama client requests short chat responses with thinking disabled and a small output budget. This workload does not require a large model.

## Major additions

- Per-station Ollama AI DJ
- Per-station model override and personality
- Maximum DJ break word count
- Grounded previous/next-track prompts
- Planned local airtime supplied to the DJ
- Recent-script avoidance
- Persistent future schedule in SQLite
- 6-hour minimum / 24-hour target schedule defaults
- Pre-generated local TTS audio
- AI timeout/retry/circuit breaker
- Dashboard Ollama/TTS/schedule health
- Test Ollama and per-station Test Model controls
- Rebuild Schedule control
- Automatic schedule invalidation after station changes/library rescans
- Emergency music playout if future scheduling is temporarily unavailable

## Reliability chain

```text
Ollama
  -> deterministic v0.1.2 script
  -> Piper/eSpeak
  -> prerecorded imaging where applicable
  -> skip the voice break
  -> music continues
```

Ollama can be stopped completely and the station can continue operating.

## Database migration

Opening an existing v0.1.2 database automatically adds:

```text
stations.ai_dj_enabled
stations.ai_model
stations.ai_personality
stations.ai_max_words
schedule_entries
```

Existing tracks, stations and play history remain intact.

## New environment variables

```text
OLLAMA_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen3:4b
OLLAMA_TIMEOUT_SECONDS=45
OLLAMA_FAILURE_THRESHOLD=3
OLLAMA_CIRCUIT_SECONDS=300
OLLAMA_KEEP_ALIVE=30m
SCHEDULE_MIN_HOURS=6
SCHEDULE_TARGET_HOURS=24
SCHEDULE_CHECK_SECONDS=60
```

## New APIs

```text
GET  /api/ollama
POST /api/ollama/test
GET  /api/stations/<id>/schedule
POST /api/stations/<id>/schedule/rebuild
```

## CasaOS

`docker-compose.casaos.yml` is updated to `v0.2.0`, retains `/music` read-only, and exposes Ollama/schedule variables. If Ollama is on another device, set `OLLAMA_URL` to that machine's LAN IP.

## Validation performed for this release

- Python source compilation
- Dashboard JavaScript syntax check
- Docker Compose YAML parsing
- CasaOS YAML parsing
- GitHub Actions YAML parsing
- Fresh v0.2.0 database creation
- v0.1.2 -> v0.2.0 database migration
- Tagged-audio library scan
- AI schedule generation using a mocked Ollama response
- Ollama-down deterministic fallback and circuit breaker
- Real FFmpeg music -> DJ -> music playout
- Shared live-byte fan-out to two listeners
- Imaging/DJ entries excluded from music history

Docker itself is not installed in the build environment used to create this source release, so the final `docker build` could not be executed there.
