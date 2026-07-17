#!/usr/bin/env python3
# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Client-side Splunk-HEC capture server (self-contained).

Stands in for a real Splunk HTTP Event Collector so the client-side integration
is runnable without provisioning Splunk. The connector's SplunkEventSink can
POST to it; every accepted envelope's inner `event` is appended (one JSON object
per line) to the capture file for assertions.

  POST /services/collector/event
    Authorization: Splunk <token>
    body: {"time":..,"sourcetype":..,"index":..,"event":{..}}
  -> 200 {"text":"Success","code":0}

  GET /health -> 200

Usage:
  fake_hec.py --port 18088 --out events.jsonl [--token TOK]

Stdlib only. A self-contained local HEC sink for offline/dev runs, so the
governance loop can be exercised without a full Splunk install.
"""
import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def make_handler(out_path, expect_token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_a):
            pass

        def _json(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/health"):
                self._json(200, {"status": "ok"})
            else:
                self._json(404, {"text": "not found", "code": 404})

        def do_POST(self):
            if "/services/collector" not in self.path:
                self._json(404, {"text": "not found", "code": 404})
                return
            auth = self.headers.get("Authorization", "")
            if expect_token and auth != f"Splunk {expect_token}":
                self._json(401, {"text": "Invalid token", "code": 4})
                return
            n = int(self.headers.get("content-length", 0))
            raw = self.rfile.read(n) if n else b""
            try:
                env = json.loads(raw)
            except json.JSONDecodeError:
                self._json(400, {"text": "Invalid data format", "code": 6})
                return
            event = env.get("event", env)
            with open(out_path, "a") as f:
                f.write(json.dumps(event) + "\n")
            self._json(200, {"text": "Success", "code": 0})

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18088)
    ap.add_argument("--out", required=True)
    ap.add_argument("--token", default="")
    args = ap.parse_args()
    with open(args.out, "w"):
        pass  # truncate the sink file to start empty
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.out, args.token))
    print(f"[fake-hec] listening on 127.0.0.1:{args.port} -> {args.out}", file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("[fake-hec] interrupted; shutting down", file=sys.stderr)
        srv.server_close()


if __name__ == "__main__":
    main()
