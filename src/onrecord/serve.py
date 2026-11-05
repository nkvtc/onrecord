"""Local preview server: `onrecord serve`.

Serves the exported site from build/ and, if ANTHROPIC_API_KEY is set (in the environment or
a .env file at the repo root), forwards the site's AI requests to Anthropic with that key.
The key stays in this process; the browser only ever talks to localhost.

This is for local experimenting. It listens on 127.0.0.1 only, and accepts AI requests only
from pages it served itself, so another website open in your browser can't spend your key.
"""

from __future__ import annotations

import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import httpx

UPSTREAM = "https://api.anthropic.com"
PREFIX = "/api/anthropic"
# Only the Messages API; nothing else on the account is reachable through the proxy.
ALLOWED_PATHS = {"/v1/messages"}
FORWARD_HEADERS = {"content-type", "anthropic-version", "anthropic-beta", "accept"}
MAX_BODY = 5_000_000


def load_env(path: Path) -> None:
    """Read KEY=value lines into os.environ without overriding variables already set."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        value = value.strip().strip("'\"")
        if key.strip() and value:
            os.environ.setdefault(key.strip(), value)


class Handler(SimpleHTTPRequestHandler):
    key: str | None = None
    client: httpx.Client | None = None

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")  # always show the latest export
        super().end_headers()

    def _json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _same_origin(self) -> bool:
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        if origin is None:  # browsers always send Origin on POST from a page
            return False
        return urlsplit(origin).netloc == host and self.headers.get("Sec-Fetch-Site") in (
            None,
            "same-origin",
        )

    def do_GET(self):
        if urlsplit(self.path).path == "/api/ai":
            # The site asks this on load; on GitHub Pages it simply 404s.
            if not self.key:
                return self._json(404, {"error": "No ANTHROPIC_API_KEY set on this server."})
            return self._json(200, {"provider": "anthropic", "via": "local"})
        return super().do_GET()

    def do_POST(self):
        url = urlsplit(self.path)
        if not url.path.startswith(PREFIX + "/"):
            return self._json(404, {"error": "Not found."})
        if not self.key:
            return self._json(503, {"error": "No ANTHROPIC_API_KEY set on this server."})
        if not self._same_origin():
            return self._json(403, {"error": "AI requests are accepted only from this site."})
        path = url.path[len(PREFIX) :]
        if path not in ALLOWED_PATHS:
            return self._json(404, {"error": f"{path} is not forwarded."})
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._json(413, {"error": "Request too large."})
        body = self.rfile.read(length)

        headers = {k: v for k, v in self.headers.items() if k.lower() in FORWARD_HEADERS}
        headers["x-api-key"] = self.key  # whatever the browser sent is replaced here
        target = UPSTREAM + path + (f"?{url.query}" if url.query else "")
        try:
            with self.client.stream("POST", target, content=body, headers=headers) as r:
                self.send_response(r.status_code)
                for k in ("content-type", "request-id", "retry-after"):
                    if k in r.headers:
                        self.send_header(k, r.headers[k])
                self.end_headers()
                # iter_bytes undoes Anthropic's gzip; we don't pass Content-Encoding on.
                for chunk in r.iter_bytes():  # stream events through as they arrive
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except httpx.HTTPError as e:
            self._json(502, {"error": f"Could not reach Anthropic: {e!r}"})
        except (BrokenPipeError, ConnectionResetError):
            pass  # the reader closed the page mid-answer

    def log_message(self, fmt, *args):
        if self.path.startswith("/api/"):
            super().log_message(fmt, *args)  # skip the noise of static file requests


class Server(ThreadingHTTPServer):
    # On Windows, address reuse lets a second server bind a port that's already taken,
    # and requests then go to whichever one Windows picks. Fail loudly instead.
    allow_reuse_address = False
    daemon_threads = True


def serve(root: Path, site: Path, port: int) -> int:
    load_env(root / ".env")
    key = os.environ.get("ANTHROPIC_API_KEY") or None
    if not (site / "index.html").is_file():
        print(f"No site in {site}. Run `uv run onrecord export` first.")
        return 1
    Handler.key = key
    Handler.client = httpx.Client(timeout=httpx.Timeout(600, connect=15))
    try:
        server = Server(("127.0.0.1", port), partial(Handler, directory=str(site)))
    except OSError:
        print(f"Port {port} is already in use. Stop that server or pass --port.")
        return 1
    print(f"Serving {site} at http://localhost:{port}/", flush=True)
    print(
        "AI: using ANTHROPIC_API_KEY from "
        + (".env" if (root / ".env").is_file() else "the environment")
        if key
        else "AI: no ANTHROPIC_API_KEY found; readers paste their own key as on the public site.",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        Handler.client.close()
    return 0
