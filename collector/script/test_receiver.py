"""Phase 0 test receiver. Standard library only.

It serves paddock_test.lua to CSP, and it writes each request of the script to received.jsonl.
Run it on the PC of the test server:

    python test_receiver.py

Then join the test server in AC and drive two laps.
"""

import json
import sys
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "paddock_test.lua"
LOG = HERE / "received.jsonl"
PORT = 8765


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] != "/paddock_test.lua":
            self.send_error(404)
            return
        body = SCRIPT.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        print(f"{datetime.now():%H:%M:%S} CSP downloaded the script")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw)
        except ValueError:
            data = {"not_json": raw[:200].decode("utf-8", "replace")}
        record = {
            "at": datetime.now(UTC).isoformat(),
            "path": self.path,
            "bytes": length,
            "data": data,
        }
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
        summary = (
            {k: v for k, v in data.items() if k != "samples"} if isinstance(data, dict) else data
        )
        print(f"{datetime.now():%H:%M:%S} {self.path} {length} bytes {summary}")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, *args):
        pass  # The prints above are enough.


if __name__ == "__main__":
    print(f"Listening on http://127.0.0.1:{PORT}. Log: {LOG}")
    try:
        ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
