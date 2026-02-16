"""Minimal HTTP server for the Chess Rocket web dashboard.

Serves dashboard.html and JSON API endpoints for live game data.
Launch: uv run python scripts/dashboard_server.py [--port 8088]
"""

from __future__ import annotations

import argparse
import http.server
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"
_DASHBOARD_HTML = Path(__file__).resolve().parent / "dashboard.html"


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    """Serves dashboard HTML and JSON API endpoints."""

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/index.html":
            self._serve_file(_DASHBOARD_HTML, "text/html; charset=utf-8")
        elif self.path == "/api/game":
            self._serve_json(_DATA_DIR / "current_game.json")
        elif self.path == "/api/progress":
            self._serve_json(_DATA_DIR / "progress.json")
        else:
            self.send_error(404)

    def _serve_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(404, f"File not found: {path.name}")
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _serve_json(self, path: Path) -> None:
        if not path.exists():
            payload = json.dumps(None).encode("utf-8")
        else:
            payload = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(payload)

    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")

    def log_message(self, format: str, *args: object) -> None:
        # Silence per-request logs; only show startup message
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Chess Rocket Dashboard Server")
    parser.add_argument("--port", type=int, default=8088, help="Port (default: 8088)")
    args = parser.parse_args()

    server = http.server.HTTPServer(("127.0.0.1", args.port), DashboardHandler)
    print(f"Chess Rocket Dashboard: http://localhost:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
