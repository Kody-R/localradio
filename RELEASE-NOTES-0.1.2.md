# LocalRadio v0.1.2 — Local TTS DJs & Station Imaging

v0.1.2 gives every LocalRadio station a local voice and an imaging layer while keeping the playlist engine deterministic and resilient.

## Local DJ breaks

Each station can enable a DJ and define a random interval such as 3-5 songs. LocalRadio decides the next track itself, then prepares a short back-announce/next-song line using built-in templates.

Example:

```text
That was Fleetwood Mac with Dreams. Coming up, Tom Petty with Free Fallin', right here on Classic Hits 98.
```

No LLM is involved yet. v0.2.0 remains the planned Ollama scripting milestone.

## Announcement prefetching

Speech is prepared during the current song instead of waiting until the track ends. The current play is first written to station history, the next track is selected with normal repeat protection, and the announcement is generated into the persistent cache.

If speech is not ready, LocalRadio does not hold the broadcast waiting for it.

## Piper + eSpeak NG

The container includes Piper TTS and eSpeak NG. `TTS_ENGINE=auto` behaves as follows:

```text
matching Piper voice model -> Piper
otherwise                  -> eSpeak NG
```

Piper voices are stored in `/config/voices`. The Station Builder reports detected Piper models and includes a voice-preview button.

## Station IDs and liners

Station IDs can run on a different interval from DJ breaks. Each station can define a slogan and multiple liner templates using:

```text
{station}
{slogan}
```

Generated IDs are prewarmed into the TTS cache when the station starts.

## Prerecorded imaging

Production IDs, sweepers and jingles can be placed in:

```text
/config/imaging/<station-id>/
```

LocalRadio recognizes WAV, MP3, OGG, Opus, FLAC, M4A and AAC. When custom imaging exists, a scheduled station-ID event randomly chooses a local file instead of synthesizing one.

## Reliability

TTS is deliberately non-critical to music playout.

- Piper failure falls back to eSpeak NG when available.
- A bad voice/model does not stop the broadcaster.
- A late or failed announcement is skipped.
- Slow listeners still cannot stall the central station stream.
- TTS does not choose music or modify play history.

## Persistence

New volume:

```text
/config
```

Contains:

```text
/config/voices
/config/imaging/<station-id>
```

Generated speech remains under:

```text
/data/tts-cache
```

The music volume remains read-only.

## Upgrade from v0.1.1

Reuse the same `/data` volume and add `/config`. The database migration is automatic and preserves all existing tracks, station definitions and play history.

Existing stations receive usable defaults:

```text
DJ enabled:              yes
DJ break interval:       3-5 songs
station IDs enabled:     yes
station ID interval:     8 songs
speech speed:            165 WPM for eSpeak
```

## Validation performed

The release was checked with:

- Python compilation
- dashboard JavaScript syntax validation
- Docker Compose YAML parsing
- CasaOS YAML parsing
- GitHub Actions YAML parsing
- fresh v0.1.2 database creation
- simulated v0.1.1 database migration
- local speech generation
- TTS cache reuse
- real FFmpeg music playout
- forced music -> DJ -> music transition
- custom prerecorded station-ID playout
- imaging excluded from music play history
- invalid voice fallback to the default local voice
- v0.1.0 and v0.1.1 schema migration compatibility
- independent play-history recording

The local execution environment did not provide Docker itself, so the image could not be built end-to-end here. The Docker dependency set includes a current Piper Linux wheel for both target architectures and eSpeak NG from Debian as fallback.
