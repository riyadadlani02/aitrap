"""Localhost JSON control plane. Runs on a daemon thread, never on the event loop."""
import json
import pathlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import render, trapsets


def _make_handler(engine):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_):
            pass  # never write to the target's stderr

        def _send(self, payload, status=200):
            body = json.dumps(payload, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def _send_html(self):
            body = (pathlib.Path(__file__).parent / "ui.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path in ("/", "/index.html"):
                return self._send_html()
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path == "/poll":
                    self._send(engine.buffer.poll(int(q.get("cursor", 0)), int(q.get("limit", 100))))
                elif url.path == "/inspect":
                    self._send(render.expand(int(q["objectId"])))
                elif url.path == "/traps":
                    self._send({"traps": [t.info() for t in engine.traps.values()]})
                elif url.path == "/trapsets":
                    self._send({"trapsets": trapsets.available()})
                elif url.path == "/probe":
                    self._send(trapsets.probe(q.get("name")))
                elif url.path == "/health":
                    self._send({"ok": True, "traps": len(engine.traps)})
                else:
                    self._send({"error": "not found"}, 404)
            except Exception as exc:
                self._send({"error": f"{type(exc).__name__}: {exc}"}, 400)

        def do_POST(self):
            try:
                if urlparse(self.path).path != "/trap":
                    return self._send({"error": "not found"}, 404)
                body = self._body()
                symbols = (
                    trapsets.symbols_for(body["trapset"], body.get("hook"))
                    if body.get("trapset")
                    else [(body["symbol"], None)]
                )
                armed, failed = [], []
                for symbol, capture in symbols:
                    try:
                        trap = engine.arm(
                            symbol,
                            tuple(body.get("events", ("call", "return"))),
                            body.get("when"),
                            body.get("capture") or capture,
                        )
                        armed.append(trap.info())
                    except LookupError as exc:
                        failed.append({"symbol": symbol, "error": str(exc)})
                self._send({"armed": armed, "failed": failed})
            except Exception as exc:
                self._send({"error": f"{type(exc).__name__}: {exc}"}, 400)

        def do_DELETE(self):
            path = urlparse(self.path).path
            if path == "/events":
                engine.buffer.clear()
                return self._send({"cleared": True})
            if path.startswith("/trap/"):
                return self._send({"disarmed": engine.disarm(int(path.rsplit("/", 1)[1]))})
            self._send({"error": "not found"}, 404)

    return Handler


def serve(engine, port=0):
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _make_handler(engine))
    threading.Thread(target=httpd.serve_forever, daemon=True, name="aitrap-server").start()
    return httpd.server_address[1]
