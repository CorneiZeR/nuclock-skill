#!/usr/bin/env python3
"""A tracker that answers whatever the test told it to.

    stub_api.py <port> <scenario.json>

The scenario names what each read returns; every write is APPENDED to
`writes.log` beside the scenario file, which is what the tests assert on. That
is the point of the whole stub: `nu-start` and `nu-finish` are worth testing
for what they REFUSE to do, and a refusal is only visible as a write that
never happened.
"""

from __future__ import annotations

import json
import pathlib
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

SCENARIO: dict = {}
WRITES: pathlib.Path


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        """Quiet: the tests read stdout of the script under test, not ours."""

    def _answer(self, body: object, code: int = 200) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802 — the base class names it
        path = self.path.split('?')[0]
        if path == '/v1/project/timer':
            self._answer(SCENARIO.get('timer'))
        elif path == '/v1/project/tasks':
            self._answer({'items': SCENARIO.get('tasks', [])})
        elif path.endswith('/links'):
            self._answer(SCENARIO.get('links', []))
        elif path.endswith('/merge-requests'):
            self._answer(SCENARIO.get('merge_requests', []))
        else:
            self._answer({'message': 'not stubbed'}, 404)

    def _write(self, method: str) -> None:
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length).decode() if length else ''
        with WRITES.open('a', encoding='utf-8') as log:
            log.write(f'{method} {self.path} {body}\n')
        refuse = SCENARIO.get('refuse_writes')
        if refuse:
            self._answer({'message': refuse}, 409)
            return
        self._answer({'ok': True})

    def do_POST(self) -> None:  # noqa: N802
        self._write('POST')

    def do_PUT(self) -> None:  # noqa: N802
        self._write('PUT')


def main() -> int:
    global SCENARIO, WRITES  # noqa: PLW0603 — one process, one scenario
    port = int(sys.argv[1])
    scenario = pathlib.Path(sys.argv[2])
    SCENARIO = json.loads(scenario.read_text(encoding='utf-8'))
    WRITES = scenario.with_name('writes.log')
    HTTPServer(('127.0.0.1', port), Handler).serve_forever()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
