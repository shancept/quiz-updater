"""Локальный фейк Google (token endpoint + Drive API v3) для тестов клиента.

Настоящий urllib ходит на 127.0.0.1 — подменять внутренности urllib не нужно.
Ответы задаются сценарием: fake.on("GET", "/files", resp1, resp2, ...) — по одному на запрос,
последний повторяется, если запросов больше, чем ответов.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


def google_error(status: int, reason: str, message: str = "boom") -> tuple:
    body = {"error": {"code": status, "message": message, "errors": [{"reason": reason, "message": message}]}}
    return status, body


class RecordedRequest:
    def __init__(self, method: str, path: str, query: dict, headers: dict, body: bytes) -> None:
        self.method = method
        self.path = path
        self.query = query  # {имя: [значения]}
        self.headers = headers
        self.body = body

    def form(self) -> dict:
        return {k: v[0] for k, v in parse_qs(self.body.decode()).items()}


class FakeGoogle:
    def __init__(self) -> None:
        self.requests: list = []
        self._script: dict = {}
        self._lock = threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _handle(self) -> None:
                parsed = urlparse(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                request = RecordedRequest(
                    self.command, parsed.path, parse_qs(parsed.query), dict(self.headers), body
                )
                status, payload = fake._respond(request)
                if isinstance(payload, (dict, list)):
                    raw, ctype = json.dumps(payload).encode(), "application/json"
                else:
                    raw, ctype = payload, "application/octet-stream"
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            do_GET = do_POST = _handle

            def log_message(self, *args) -> None:  # тишина в выводе тестов
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        # poll_interval по умолчанию 0.5 с → shutdown() в каждом тесте ждал бы до полсекунды.
        self._thread = threading.Thread(
            target=lambda: self._server.serve_forever(poll_interval=0.01), daemon=True
        )

    def _respond(self, request: RecordedRequest) -> tuple:
        with self._lock:
            self.requests.append(request)
            queue = self._script.get((request.method, request.path))
            if not queue:
                return 599, {"error": f"не задан ответ для {request.method} {request.path}"}
            return queue.pop(0) if len(queue) > 1 else queue[0]

    def on(self, method: str, path: str, *responses: tuple) -> None:
        self._script[(method, path)] = list(responses)

    def requests_to(self, path: str) -> list:
        return [r for r in self.requests if r.path == path]

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def start(self) -> "FakeGoogle":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
