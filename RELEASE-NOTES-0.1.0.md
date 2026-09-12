# LocalRadio v0.1.0 — Core Radio Engine

v0.1.0 establishes the durable 24/7 radio foundation: catalog the library, choose music centrally, enforce repeat rules, transcode with FFmpeg and serve one shared live stream to IPTV clients.

## What to test

1. Initial scan completes against a real read-only library.
2. Tagged MP3/FLAC/M4A content appears correctly on the dashboard.
3. The stream plays continuously in VLC for several hours.
4. Multiple listeners hear the same current track.
5. Play history grows once per broadcast track rather than once per listener.
6. Repeat protection behaves reasonably for the size of the test library.
7. Deleted files disappear after a rescan.
8. Broken/unreadable tracks are skipped without stopping the station.
9. Container restart retains the catalog/history database.
10. `/music` remains untouched.

## Intentionally deferred

This release does not yet include multiple stations, TTS, Ollama, prerecorded station imaging, scheduled DJ breaks, smart rotation tiers, XMLTV or video presentation. Those layers will be built on top of this engine after 24/7 playout is proven reliable.
