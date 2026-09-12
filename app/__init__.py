import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def create_app():
    import atexit
    import threading
    import time

    from flask import Flask

    from .config import settings
    from .db import Database
    from .scanner import LibraryScanner
    from .streaming import StationManager
    from .web import create_blueprint

    log = logging.getLogger(__name__)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    app = Flask(__name__)
    db = Database(settings.db_path, settings=settings)
    scanner = LibraryScanner(db, settings.music_dir)
    manager = StationManager(db, settings)

    app.extensions["localradio"] = {
        "db": db,
        "scanner": scanner,
        "manager": manager,
        "settings": settings,
    }
    app.register_blueprint(create_blueprint(db, scanner, manager, settings))

    def startup_worker():
        time.sleep(1)
        if settings.auto_scan_on_start:
            try:
                scanner.scan()
            except Exception:
                log.exception("Startup music scan failed")
        manager.start_all()

        if settings.scan_interval_hours > 0:
            while True:
                time.sleep(settings.scan_interval_hours * 3600)
                try:
                    scanner.scan()
                except Exception:
                    log.exception("Scheduled music scan failed")

    thread = threading.Thread(target=startup_worker, name="localradio-startup", daemon=True)
    thread.start()
    atexit.register(manager.stop_all)
    return app
