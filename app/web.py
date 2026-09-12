import threading
from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context


def create_blueprint(db, scanner, manager, settings):
    bp = Blueprint("web", __name__)

    @bp.get("/")
    def index():
        return render_template("index.html")

    @bp.get("/health")
    def health():
        enabled = db.list_stations(enabled_only=True)
        running = sum(1 for s in enabled if manager.station_status(s)["running"])
        return jsonify({
            "ok": True,
            "tracks": db.track_count(),
            "stations_enabled": len(enabled),
            "stations_running": running,
        })

    @bp.get("/api/status")
    def api_status():
        statuses = manager.statuses()
        return jsonify({
            "version": "0.1.1",
            "library": db.stats(),
            "scan": {
                "running": scanner.running,
                "last_scan": db.get_state("last_scan"),
                "last_result": scanner.last_result,
            },
            "audio": {"bitrate_kbps": settings.bitrate_kbps, "sample_rate": settings.sample_rate},
            "stations": statuses,
            "recent": db.recent_history(12),
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

    @bp.get("/api/library/options")
    def api_library_options():
        return jsonify({"genres": db.list_genres(), "artists": db.list_artists(500)})

    @bp.get("/api/stations")
    def api_stations():
        return jsonify(manager.statuses())

    @bp.post("/api/stations")
    def create_station():
        data = request.get_json(silent=True) or {}
        station = db.create_station(data)
        manager.sync()
        return jsonify({"ok": True, "station": station, "playout": manager.station_status(station)}), 201

    @bp.get("/api/stations/<station_id>")
    def get_station(station_id):
        station = db.get_station(station_id)
        if not station:
            return jsonify({"error": "Unknown station"}), 404
        return jsonify({
            "station": station,
            "playout": manager.station_status(station),
            "recent": db.recent_history(20, station_id),
        })

    @bp.put("/api/stations/<station_id>")
    def update_station(station_id):
        data = request.get_json(silent=True) or {}
        station = db.update_station(station_id, data)
        if not station:
            return jsonify({"error": "Unknown station"}), 404
        manager.sync()
        return jsonify({"ok": True, "station": station, "playout": manager.station_status(station)})

    @bp.delete("/api/stations/<station_id>")
    def delete_station(station_id):
        station = db.get_station(station_id)
        if not station:
            return jsonify({"error": "Unknown station"}), 404
        if not db.delete_station(station_id):
            return jsonify({"error": "Could not delete station"}), 500
        manager.sync()
        return jsonify({"ok": True})

    @bp.get("/api/stations/<station_id>/history")
    def station_history(station_id):
        if not db.get_station(station_id):
            return jsonify({"error": "Unknown station"}), 404
        return jsonify(db.recent_history(50, station_id))

    @bp.get("/playlist.m3u")
    def playlist():
        base = request.host_url.rstrip("/")
        lines = ["#EXTM3U"]
        for station in db.list_stations(enabled_only=True):
            name = str(station["name"]).replace("\r", " ").replace("\n", " ")
            number = str(station["channel_number"]).replace('"', "'").replace("\r", "").replace("\n", "")
            logo = str(station.get("logo_url") or "").replace('"', "%22").replace("\r", "").replace("\n", "")
            logo_attr = f' tvg-logo="{logo}"' if logo else ""
            lines.append(
                f'#EXTINF:-1 tvg-id="{station["id"]}" tvg-chno="{number}"{logo_attr} group-title="Local Radio",{name}'
            )
            lines.append(f'{base}/stream/{station["id"]}.mp3')
        lines.append("")
        return Response("\n".join(lines), mimetype="audio/x-mpegurl", headers={"Content-Disposition": "inline; filename=localradio.m3u"})

    @bp.get("/stream/<station_id>.mp3")
    def stream(station_id):
        station = db.get_station(station_id)
        if not station or not station["enabled"]:
            return jsonify({"error": "Unknown or disabled station"}), 404
        hub = manager.get_hub(station_id)
        if not hub:
            manager.sync()
            hub = manager.get_hub(station_id)
        if not hub:
            return jsonify({"error": "Station broadcaster is not running"}), 503
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
