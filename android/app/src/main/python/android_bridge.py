"""Android entry point: runs the desktop API in this process, with no socket and no port.

The WebView's API calls arrive through the native Backend plugin as (method, path, headers, body).
Each one is handed to the desktop request handler unchanged, so routing, validation and error
mapping stay exactly as on the desktop; only the transport differs.
"""

import io
import json
import os
import threading
from email.message import Message
from types import SimpleNamespace

from apps.api import server

ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

_context = None
_start_lock = threading.Lock()


def start(data_dir):
    """Open the database under the app's private storage and resume queued story jobs."""
    global _context
    with _start_lock:
        if _context is None:
            os.makedirs(data_dir, exist_ok=True)
            # The WebView serves the frontend itself, so the static folder is never read.
            context = server.AppContext(data_dir, os.path.join(data_dir, "unused-static"))
            _use_keystore_secrets(context, data_dir)
            context.resume_queued()
            _context = context
    return True


def request(method, path, headers_json, body):
    """One API call from the WebView. Returns (status, headers as JSON, body bytes)."""
    if _context is None:
        return _error(503, "SERVICE_STARTING", "游戏服务正在启动，请稍后重试")
    url_path = path.split("?", 1)[0]
    if method not in ALLOWED_METHODS or not (url_path == "/api" or url_path.startswith("/api/")):
        return _error(404, "NOT_FOUND", "接口不存在")
    headers = json.loads(headers_json or "{}")
    payload = bytes(body) if body is not None else b""
    handler = _BridgeHandler(method, path, headers, payload)
    getattr(handler, "do_" + method)()
    return handler.result()


def busy():
    """True while a character, story or image job is running; the app then keeps itself awake."""
    if _context is None:
        return False
    with _context._worker_lock:
        return any(worker.is_alive() for worker in _context._workers)


def _error(status, code, message):
    body = json.dumps({"error": {"code": code, "message": message, "fields": {}, "retryable": status == 503}},
                      ensure_ascii=False).encode("utf-8")
    return status, json.dumps({"Content-Type": "application/json; charset=utf-8"}), body


class _BridgeHandler(server.FantasySimulatorHandler):
    """The desktop handler with in-memory streams in place of a socket."""

    def __init__(self, method, path, headers, body):  # pylint: disable=super-init-not-called
        self.command = method
        self.path = path
        self.request_version = "HTTP/1.1"
        self.requestline = f"{method} {path} HTTP/1.1"
        self.client_address = ("android", 0)
        self.close_connection = True
        self.server = SimpleNamespace(app_context=_context)
        self.headers = Message()
        for key, value in headers.items():
            if key.lower() != "content-length":
                self.headers[key] = str(value)
        if body:
            self.headers["Content-Length"] = str(len(body))
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()

    def result(self):
        raw = self.wfile.getvalue()
        head, _, body = raw.partition(b"\r\n\r\n")
        lines = head.decode("iso-8859-1").split("\r\n")
        status = int(lines[0].split(" ", 2)[1])
        headers = {}
        for line in lines[1:]:
            key, _, value = line.partition(":")
            if key.lower() not in {"server", "date", "content-length", "connection"}:
                headers[key.strip()] = value.strip()
        return status, json.dumps(headers, ensure_ascii=False), body


class _KeystoreSecretStore(server.SecretStore):
    """API keys sealed with an Android Keystore key (SecretCipher), so they survive restarts."""

    def __init__(self, path):
        super().__init__(path, backend="android_keystore")

    def _durable_label(self):
        return "android_keystore" if self.backend else "memory_only"

    @staticmethod
    def _cipher():
        from java import jclass  # pylint: disable=import-outside-toplevel
        return jclass("com.fantasysimulator.app.SecretCipher")

    def _protect(self, value):
        try:
            return str(self._cipher().seal(value))
        except Exception as exc:  # Java exceptions surface as Python exceptions.
            raise ValueError("Keystore encryption failed") from exc

    def _unprotect(self, cipher):
        try:
            return str(self._cipher().open(cipher))
        except Exception as exc:
            raise ValueError("Keystore decryption failed") from exc


def _use_keystore_secrets(context, data_dir):
    context.secrets = _KeystoreSecretStore(os.path.join(data_dir, "secrets.dat"))
    context.image_secrets._store = _KeystoreSecretStore(os.path.join(data_dir, "image-secrets.dat"))
    context.embedding_secrets._store = _KeystoreSecretStore(os.path.join(data_dir, "embedding-secrets.dat"))
