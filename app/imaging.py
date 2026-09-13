import random
from pathlib import Path


class ImagingLibrary:
    SUPPORTED = {".wav", ".mp3", ".ogg", ".opus", ".flac", ".m4a", ".aac"}

    def __init__(self, settings):
        self.root = settings.imaging_dir
        self.root.mkdir(parents=True, exist_ok=True)

    def station_dir(self, station_id: str) -> Path:
        path = self.root / station_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def files(self, station_id: str):
        path = self.station_dir(station_id)
        return sorted(
            p for p in path.iterdir()
            if p.is_file() and p.suffix.lower() in self.SUPPORTED
        )

    def random_file(self, station_id: str):
        items = self.files(station_id)
        return random.choice(items) if items else None

    def count(self, station_id: str):
        return len(self.files(station_id))
