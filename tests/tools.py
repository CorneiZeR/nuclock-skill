#!/usr/bin/env python3
"""Every tool call this plugin shows is one the server takes.

The documents teach calls in prose — `log_time(task_id, hours, date, note)` —
and prose is checked by nothing. When the server moved `log_time`
from `date` to `started_at` on 2026-10-10, the skill and `nu-untracked` went on
teaching the old shape, and a model that followed them was refused.

`tool_schemas.json` is a copy of the server's own snapshot
(nuclock_back: mcp_server/tests/tool_schemas.json). Two checks:

* every `name(args)` naming a tool, in every document and script, uses only
  arguments the tool has — and, unless it elides with `…`, all it requires;
* the copy is what the live server publishes, so a server change that was
  never carried here fails this test instead of the next person who follows
  the documents. Without a key or a network the live check says it was
  skipped — loudly, because skipped is not passed.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'skills' / 'nuclock' / 'scripts'))
import _nuclock  # noqa: E402

SNAPSHOT = json.loads((ROOT / 'tests' / 'tool_schemas.json').read_text(encoding='utf-8'))
SOURCES = ('skills', 'commands', 'hooks', 'README.md')
ELIDED = {'…', '...'}


def documents() -> list[pathlib.Path]:
    found = []
    for source in SOURCES:
        path = ROOT / source
        found += [path] if path.is_file() else sorted(p for p in path.rglob('*') if p.suffix in {'.md', '.py', '.sh'})
    return found


def call_problems() -> tuple[int, list[str]]:
    names = '|'.join(sorted(SNAPSHOT, key=len, reverse=True))
    pattern = re.compile(rf'(?<![\w.])(?:mcp__nuclock__)?({names})\(([^()]*)\)')
    calls, problems = 0, []
    for path in documents():
        text = path.read_text(encoding='utf-8')
        for match in pattern.finditer(text):
            calls += 1
            tool, raw = match.group(1), match.group(2)
            where = f'{path.relative_to(ROOT)}:{text.count(chr(10), 0, match.start()) + 1}  {tool}(…)'
            schema = SNAPSHOT[tool]
            given = []
            for part in raw.replace('\n', ' ').split(','):
                part = part.strip()
                if not part or part in ELIDED:
                    continue
                # `a | b` offers a choice between two arguments.
                given += [alt.split('=')[0].strip() for alt in part.split('|')]
            unknown = [arg for arg in given if arg not in schema.get('properties', {})]
            if unknown:
                problems.append(f'{where}: {tool} takes no {", ".join(unknown)}')
            if not ELIDED & {p.strip() for p in raw.split(',')}:
                missing = [arg for arg in schema.get('required', ()) if arg not in given]
                if missing:
                    problems.append(f'{where}: leaves out required {", ".join(missing)}')
    return calls, problems


def live() -> dict | str:
    """The server's tool list, or why it could not be read."""
    try:
        auth = _nuclock.key()
    except _nuclock.NoKeyError as err:
        return str(err)
    request = urllib.request.Request(  # noqa: S310 — the host is this app's own
        f'{_nuclock.API}/mcp',
        data=json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}).encode(),
        headers={
            'Authorization': auth,
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/event-stream',
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_nuclock.TIMEOUT) as answer:  # noqa: S310
            body = answer.read().decode()
    except (urllib.error.URLError, TimeoutError) as err:
        return f'could not reach {_nuclock.API}/mcp: {err}'
    # Streamable HTTP answers as one server-sent event.
    payload = next((line[5:] for line in body.splitlines() if line.startswith('data:')), body)
    return {tool['name']: tool['inputSchema'] for tool in json.loads(payload)['result']['tools']}


def main() -> int:
    failures = 0
    calls, problems = call_problems()
    print(f'tool calls in the documents: {calls}')
    for problem in problems:
        print(f'  FAIL  {problem}')
    failures += len(problems)
    if calls == 0:
        print('  FAIL  found no tool calls at all — the pattern no longer matches the documents')
        failures += 1

    server = live()
    if isinstance(server, str):
        print(f'live server: SKIPPED — {server}')
    else:
        stale = sorted(n for n in set(server) | set(SNAPSHOT) if server.get(n) != SNAPSHOT.get(n))
        if stale:
            named = ', '.join(stale[:8]) + (f' and {len(stale) - 8} more' if len(stale) > 8 else '')
            print(f'  FAIL  tests/tool_schemas.json is not what the server publishes: {named}')
            print('        copy nuclock_back/mcp_server/tests/tool_schemas.json here, then run this again')
            failures += 1
        else:
            print(f'live server: {len(server)} tools, the same as tests/tool_schemas.json')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
