import hashlib
import importlib.util
import logging
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

log = logging.getLogger(__name__)


class TTSManager:
    """Generate and cache local speech audio.

    `auto` prefers Piper when a matching model exists under /config/voices and
    falls back to eSpeak NG, which is included in the Docker image. Cache files
    are WAV so FFmpeg can normalize them into the station's live MP3 stream.
    """

    def __init__(self, settings):
        self.settings = settings
        self.cache_dir = settings.tts_cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.voices_dir = settings.voices_dir
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        self._locks = {}
        self._locks_lock = threading.Lock()

    def _lock_for(self, key: str):
        with self._locks_lock:
            return self._locks.setdefault(key, threading.Lock())

    @property
    def piper_binary(self):
        configured = str(self.settings.piper_binary or "").strip()
        if configured:
            found = shutil.which(configured)
            if found:
                return found
        return shutil.which("piper")

    @property
    def piper_module_available(self):
        try:
            return importlib.util.find_spec("piper") is not None
        except (ImportError, ValueError):
            return False

    @property
    def espeak_binary(self):
        return shutil.which("espeak-ng") or shutil.which("espeak")

    def piper_model_for(self, voice: str):
        voice = (voice or "").strip()
        if not voice:
            choices = sorted(self.voices_dir.glob("*.onnx")) if self.voices_dir.exists() else []
            return choices[0] if choices else None
        raw = Path(voice)
        candidates = []
        if raw.is_absolute():
            candidates.append(raw)
        else:
            candidates.extend([
                self.voices_dir / voice,
                self.voices_dir / f"{voice}.onnx",
            ])
        for candidate in candidates:
            if candidate.is_file() and candidate.suffix.lower() == ".onnx":
                return candidate
        return None

    def available_piper_voices(self):
        if not self.voices_dir.exists():
            return []
        return sorted(p.stem for p in self.voices_dir.glob("*.onnx") if p.is_file())

    def choose_engine(self, voice: str):
        requested = (self.settings.tts_engine or "auto").strip().lower()
        has_piper = bool((self.piper_binary or self.piper_module_available) and self.piper_model_for(voice))
        has_espeak = bool(self.espeak_binary)
        if requested == "piper":
            if has_piper:
                return "piper"
            if has_espeak:
                return "espeak-ng"
            return None
        if requested in {"espeak", "espeak-ng"}:
            return "espeak-ng" if has_espeak else None
        if has_piper:
            return "piper"
        return "espeak-ng" if has_espeak else None

    def status(self):
        voices = self.available_piper_voices()
        return {
            "requested_engine": self.settings.tts_engine,
            "piper_available": bool(self.piper_binary or self.piper_module_available),
            "piper_voices": voices,
            "espeak_available": bool(self.espeak_binary),
            "cache_dir": str(self.cache_dir),
            "voices_dir": str(self.voices_dir),
        }

    @staticmethod
    def _clean_text(text: str):
        text = " ".join(str(text or "").replace("\x00", " ").split())
        return text[:900]

    def generate(self, text: str, *, voice: str = "", speed_wpm: int = 165):
        text = self._clean_text(text)
        if not text:
            return None
        engine = self.choose_engine(voice)
        if not engine:
            log.warning("No local TTS engine is available")
            return None
        speed_wpm = max(80, min(int(speed_wpm or 165), 300))
        key_data = f"v2|{engine}|{voice}|{speed_wpm}|{text}".encode("utf-8", errors="replace")
        key = hashlib.sha256(key_data).hexdigest()
        target = self.cache_dir / f"{key}.wav"
        if target.exists() and target.stat().st_size > 128:
            return target

        with self._lock_for(key):
            if target.exists() and target.stat().st_size > 128:
                return target
            tmp = None
            try:
                with tempfile.NamedTemporaryFile(
                    prefix=f"tts-{key[:10]}-", suffix=".wav", dir=self.cache_dir, delete=False
                ) as fh:
                    tmp = Path(fh.name)

                if engine == "piper":
                    model = self.piper_model_for(voice)
                    if not model:
                        raise RuntimeError(f"Piper voice model not found: {voice}")
                    if self.piper_module_available:
                        # Current OHF Piper CLI: python -m piper -m VOICE -f out.wav -- TEXT
                        cmd = [sys.executable, "-m", "piper", "-m", str(model), "-f", str(tmp), "--", text]
                        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
                    else:
                        # Compatibility with standalone Piper binaries using the
                        # classic stdin/output_file interface.
                        cmd = [self.piper_binary, "--model", str(model), "--output_file", str(tmp)]
                        proc = subprocess.run(
                            cmd, input=(text + "\n").encode("utf-8"),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90,
                        )
                else:
                    voice_name = (voice or self.settings.default_espeak_voice or "en-us").strip()
                    cmd = [self.espeak_binary, "-v", voice_name, "-s", str(speed_wpm), "-w", str(tmp), text]
                    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)

                if proc.returncode != 0 or not tmp.exists() or tmp.stat().st_size <= 128:
                    stderr = proc.stderr.decode("utf-8", errors="replace").strip()[-1000:]
                    raise RuntimeError(stderr or f"{engine} returned {proc.returncode}")
                tmp.replace(target)
                return target
            except Exception as exc:
                log.warning("TTS generation failed with %s: %s", engine, exc)
                # Piper is optional. If it fails, guarantee the station still has
                # a local fallback when eSpeak is present.
                if engine == "piper" and self.espeak_binary:
                    return self._generate_espeak_fallback(text, voice="", speed_wpm=speed_wpm)
                if engine == "espeak-ng" and self.espeak_binary:
                    # A Piper model name or typo may have been entered while no
                    # matching model is installed. Retry with the configured
                    # safe eSpeak voice before giving up on the break.
                    default_voice = self.settings.default_espeak_voice or "en-us"
                    if (voice or "").strip() != default_voice:
                        return self._generate_espeak_fallback(text, voice=default_voice, speed_wpm=speed_wpm)
                return None
            finally:
                if tmp and tmp.exists():
                    try:
                        tmp.unlink()
                    except OSError:
                        pass

    def _generate_espeak_fallback(self, text: str, *, voice: str = "", speed_wpm: int = 165):
        fallback_voice = voice or self.settings.default_espeak_voice or "en-us"
        key_data = f"fallback|espeak-ng|{fallback_voice}|{speed_wpm}|{text}".encode("utf-8")
        key = hashlib.sha256(key_data).hexdigest()
        target = self.cache_dir / f"{key}.wav"
        if target.exists() and target.stat().st_size > 128:
            return target
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(prefix="tts-fallback-", suffix=".wav", dir=self.cache_dir, delete=False) as fh:
                tmp = Path(fh.name)
            proc = subprocess.run(
                [self.espeak_binary, "-v", fallback_voice, "-s", str(speed_wpm), "-w", str(tmp), text],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
            )
            if proc.returncode == 0 and tmp.exists() and tmp.stat().st_size > 128:
                tmp.replace(target)
                return target
        except Exception as exc:
            log.warning("Fallback TTS generation failed: %s", exc)
        finally:
            if tmp and tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
        return None
