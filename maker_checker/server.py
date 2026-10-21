"""A small HTTP gate, so agents in any language (TypeScript, Go, n8n, ...)
can ask for a decision before running a tool.

    POST /check   {"tool": "send_email", "args": {...}, "context": {...}}
              ->  {"decision": "allow" | "deny" | "ask", "reason": "..."}
    GET  /health  {"ok": true}

"ask" means your app should get a human's OK before running the tool.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import adapters
from .policy import Policy
from .recorder import Recorder


def make_server(
    policy: Policy,
    host: str = "127.0.0.1",
    port: int = 8787,
    recorder: Recorder | None = None,
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/health":
                self._send(200, {"ok": True})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/check":
                self._send(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                intent, context = adapters.parse("generic", json.loads(self.rfile.read(length)))
            except (ValueError, KeyError, TypeError) as error:
                self._send(400, {"error": f"expected {{'tool': ..., 'args': {{...}}}}: {error}"})
                return

            verdict = adapters.evaluate(policy, intent, context)
            if recorder:
                recorder.record("proposed", tool=intent.tool, args=intent.args, via="http")
                recorder.record("decision", tool=intent.tool, effect=verdict.effect, reason=verdict.reason)
            self._send(200, adapters.render("generic", verdict))

        def log_message(self, *args):  # keep stdout quiet
            pass

    return ThreadingHTTPServer((host, port), Handler)
