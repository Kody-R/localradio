import threading
from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context


def create_blueprint(db, scanner, hub, settings):
    bp = Blueprint("web", __name__)

    @bp.get("/")
    def index():
        return render_template("index.html", station_name=settings.station_name, station_number=settings.station_number, station_id=settings.station_id)

    @bp.get("/health")
    def health():
        return jsonify({"ok": True, "broadcaster_running": hub.running, "tracks": db.track_count()})

    @bp.get("/api/status")
    def api_status():
        return jsonify({
            "station": {
                "name": settings.station_name,
                "id": settings.station_id,
                "number": settings.station_number,
                "bitrate_kbps": settings.bitrate_kbps,
                "artist_repeat_minutes": settings.artist_repeat_minutes,
                "song_repeat_hours": settings.song_repeat_hours,
            },
            "library": db.stats(),
            "scan": {
                "running": scanner.running,
                "last_scan": db.get_state("last_scan"),
                "last_result": scanner.last_result,
            },
            "playout": hub.status(),
            "recent": db.recent_history(10),
        })

    @bp.post("/api/scan")
    def api_scan():
        if scanner.running:
            return jsonify({"ok": False, "message": "Scan already running"}), 409
        threading.Thread(target=scanner.scan, name="manual-library-scan", daemon=True).start()
        return jsonify({"ok": True, "message": "Library scan started"}), 202

    @bp.get("/api/tracks")
    def api_tracks():
        try:
            limit = max(1, min(int(request.args.get("limit", "100")), 500))
        except ValueError:
            limit = 100
        return jsonify(db.list_tracks(limit))

    @bp.get("/playlist.m3u")
    def playlist():
        base = request.host_url.rstrip("/")
        body = "\n".join([
            "#EXTM3U",
            f'#EXTINF:-1 tvg-id="{settings.station_id}" tvg-chno="{settings.station_number}" group-title="Local Radio",{settings.station_name}',
            f"{base}/stream/{settings.station_id}.mp3",
            "",
        ])
        return Response(body, mimetype="audio/x-mpegurl", headers={"Content-Disposition": "inline; filename=localradio.m3u"})

    @bp.get("/stream/<station_id>.mp3")
    def stream(station_id):
        if station_id != settings.station_id:
            return jsonify({"error": "Unknown station"}), 404
        return Response(
            stream_with_context(hub.stream_generator()),
            mimetype="audio/mpeg",
            headers={
                "Cache-Control": "no-cache, no-store",
                "Pragma": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
            direct_passthrough=True,
        )

    return bp
