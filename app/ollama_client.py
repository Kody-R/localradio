import json
import logging
import threading
import time
import urllib.error
import urllib.request

log = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, settings):
        self.settings = settings
        self.base_url = settings.ollama_url
        self.default_model = settings.ollama_model
        self.timeout = max(5, int(settings.ollama_timeout_seconds))
        self.failure_threshold = max(1, int(settings.ollama_failure_threshold))
        self.circuit_seconds = max(30, int(settings.ollama_circuit_seconds))
        self.keep_alive = settings.ollama_keep_alive
        self._lock = threading.RLock()
        self._consecutive_failures = 0
        self._circuit_until = 0.0
        self._last_error = None
        self._last_success_at = None
        self._last_probe_at = 0.0
        self._last_probe_online = None
        self._last_probe_models = []

    def _request_json(self, path: str, payload=None, method=None, timeout=None):
        url = self.base_url + path
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers, method=method or ("POST" if body else "GET"))
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8")) if raw else {}

    def _record_success(self):
        with self._lock:
            self._consecutive_failures = 0
            self._circuit_until = 0.0
            self._last_error = None
            self._last_success_at = time.time()

    def _record_failure(self, exc):
        with self._lock:
            self._consecutive_failures += 1
            self._last_error = str(exc)[:1000]
            if self._consecutive_failures >= self.failure_threshold:
                self._circuit_until = max(self._circuit_until, time.time() + self.circuit_seconds)
        log.warning("Ollama request failed: %s", exc)

    def circuit_open(self):
        with self._lock:
            return self._circuit_until > time.time()

    def status(self, force=False):
        now = time.time()
        with self._lock:
            base = {
                "url": self.base_url,
                "default_model": self.default_model,
                "consecutive_failures": self._consecutive_failures,
                "circuit_open": self._circuit_until > now,
                "circuit_remaining_seconds": max(0, int(self._circuit_until - now)),
                "last_error": self._last_error,
                "last_success_at": self._last_success_at,
            }
        if base["circuit_open"]:
            base.update({"online": False, "models": []})
            return base
        with self._lock:
            if not force and self._last_probe_online is not None and now - self._last_probe_at < 30:
                base.update({"online": self._last_probe_online, "models": list(self._last_probe_models)})
                return base
        try:
            data = self._request_json("/api/tags", timeout=min(self.timeout, 8))
            models = []
            for item in data.get("models") or []:
                name = item.get("name") or item.get("model")
                if name:
                    models.append(name)
            self._record_success()
            models = sorted(set(models))
            with self._lock:
                self._last_probe_at = time.time()
                self._last_probe_online = True
                self._last_probe_models = models
            base.update({"online": True, "models": models})
        except Exception as exc:
            self._record_failure(exc)
            with self._lock:
                self._last_probe_at = time.time()
                self._last_probe_online = False
                self._last_probe_models = []
            base.update({"online": False, "models": []})
            base["last_error"] = str(exc)[:1000]
        return base

    def generate(self, *, system: str, user: str, model: str | None = None, max_tokens: int = 120):
        if self.circuit_open():
            return None
        payload = {
            "model": model or self.default_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "think": False,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": 0.75,
                "top_p": 0.9,
                "num_ctx": 4096,
                "num_predict": max(32, min(int(max_tokens), 256)),
                "repeat_penalty": 1.08,
            },
        }
        last_exc = None
        for attempt in range(2):
            try:
                data = self._request_json("/api/chat", payload=payload)
                content = ((data.get("message") or {}).get("content") or "").strip()
                if not content:
                    raise RuntimeError("Ollama returned an empty response")
                self._record_success()
                return content
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
                last_exc = exc
                if attempt == 0:
                    time.sleep(0.35)
        self._record_failure(last_exc or RuntimeError("Ollama request failed"))
        return None

    def test(self, model: str | None = None):
        text = self.generate(
            system="You are a radio DJ test endpoint. Reply with one short sentence only.",
            user="Say that the LocalRadio AI DJ connection is working.",
            model=model,
            max_tokens=48,
        )
        return {"ok": bool(text), "text": text, "model": model or self.default_model, "status": self.status(force=True)}
