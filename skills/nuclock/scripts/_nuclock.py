"""Talking to nuclock from a script, with the person's own key.

Imported by everything else here. Three decisions worth knowing about:

**The key is read from where it already is** — `NUCLOCK_API_KEY`, or the MCP
server's own header in `~/.claude.json`. Somebody who set the tools up once
does not set up a second credential for these scripts, and nothing here writes
the key anywhere, prints it, or passes it as an argument (an argument is
visible in `ps` to everybody on the machine).

**Reads are not retried.** These run in front of a person who is waiting, and a
tracker that is down is worth hearing about at once rather than after three
backoffs.

**A HOOK never writes; a command the person typed does.** That is the line,
and it is not about the HTTP verb. `nu-start` and `nu-finish` move a status
and a timer because somebody ran them on purpose, naming the task — which is
the decision itself, made once instead of through four tool calls. The hooks
next door only warn, and they are the ones that fire without being asked: a
hook that started a timer would be recording time nobody can vouch for.

Backfilling stays out of here entirely. How many hours went untracked is a
judgement, and `log_time` is where a person makes it with a note attached.
"""

from __future__ import annotations

import json
import os
import pathlib
import urllib.error
import urllib.request

API = os.environ.get('NUCLOCK_API_URL', 'https://api.clock.nuspect.net')
TIMEOUT = 15


class NoKeyError(RuntimeError):
    """No credential anywhere this knows to look."""


class ApiError(RuntimeError):
    """The tracker answered, and the answer was not one we can use."""


def key() -> str:
    """The Authorization header value, as the API expects it."""
    from_env = os.environ.get('NUCLOCK_API_KEY')
    if from_env:
        return from_env if from_env.startswith('Api-Key ') else f'Api-Key {from_env}'
    config = pathlib.Path.home() / '.claude.json'
    try:
        servers = json.loads(config.read_text(encoding='utf-8')).get('mcpServers', {})
    except (OSError, ValueError) as err:
        raise NoKeyError('no NUCLOCK_API_KEY, and ~/.claude.json is unreadable') from err
    header = (servers.get('nuclock', {}).get('headers', {}) or {}).get('Authorization')
    if not header:
        raise NoKeyError('no NUCLOCK_API_KEY, and no nuclock MCP server is configured')
    return header


def get(path: str) -> object:
    """GET a path and return the decoded body."""
    request = urllib.request.Request(  # noqa: S310 — the host is this app's own
        f'{API}{path}', headers={'Authorization': key()},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:  # noqa: S310
            body = answer.read() or b'null'
    except urllib.error.HTTPError as err:
        # 403 on a read is the KEY's scope or the person's access, and neither
        # changes by asking again — so it is said plainly rather than retried.
        raise ApiError(f'{err.code} from {path}') from err
    except (urllib.error.URLError, TimeoutError) as err:
        raise ApiError(f'could not reach {API}: {err}') from err
    try:
        return json.loads(body)
    except ValueError as err:
        # A 200 carrying something that is not JSON is the tracker failing,
        # and it has to ARRIVE as a failure: letting the decode escape made
        # `nu-running.py` exit 1, which every hook reads as "no timer is
        # running" — a warning invented by a broken gateway.
        raise ApiError(f'{path} answered something that is not JSON') from err


def send(method: str, path: str, body: dict) -> object:
    """POST or PUT, for the two commands a person runs deliberately.

    Failures are reported rather than retried, for the same reason reads are:
    a refusal here is almost always an answer — a second timer while one runs,
    a task an invoice has frozen, a key scoped for reading — and asking again
    cannot change any of them.
    """
    request = urllib.request.Request(  # noqa: S310 — the host is this app's own
        f'{API}{path}',
        data=json.dumps(body).encode(),
        method=method,
        headers={'Authorization': key(), 'Content-Type': 'application/json'},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:  # noqa: S310
            return json.loads(answer.read() or b'null')
    except urllib.error.HTTPError as err:
        detail = ''
        try:
            said = json.loads(err.read() or b'{}')
            detail = said.get('message') or said.get('detail') or ''
        except (ValueError, OSError):
            detail = ''
        # The tracker's own sentence, where it sent one: "an invoice has
        # claimed this task" tells somebody what to do; "409" does not.
        raise ApiError(f'{err.code} from {path}{f": {detail}" if detail else ""}') from err
    except (urllib.error.URLError, TimeoutError) as err:
        raise ApiError(f'could not reach {API}: {err}') from err
    except ValueError as err:
        raise ApiError(f'{path} answered something that is not JSON') from err


def post(path: str, body: dict) -> object:
    """A deliberate write — see `send`."""
    return send('POST', path, body)


def put(path: str, body: dict) -> object:
    """A deliberate write — see `send`."""
    return send('PUT', path, body)


def rows(body: object) -> list[dict]:
    """The rows out of a page or out of a bare list — both shapes come back."""
    if isinstance(body, dict):
        body = body.get('items', body)
    if isinstance(body, list):
        return [row for row in body if isinstance(row, dict)]
    return [body] if isinstance(body, dict) else []


def running_timer() -> dict | None:
    """What this person is tracking right now, across every project."""
    answer = get('/v1/project/timer')
    return answer if isinstance(answer, dict) and answer.get('task_id') else None


def my_tasks(status: str, limit: int = 20) -> list[dict]:
    """This person's tasks in one status, in the order somebody arranged."""
    return rows(get(f'/v1/project/tasks?mine=true&status={status}&sort=rank&limit={limit}'))


def task_by_key(key: str) -> dict:
    """One task, by the key people say out loud — `NUC-142`.

    Matched whole by the API, so `NUC-1` never answers with `NUC-14`, and it
    searches only what this key may already see: an unknown key and somebody
    else's task give the same empty answer, which is the same thing from the
    outside and deliberately so.
    """
    found = rows(get(f'/v1/project/tasks?key={key}&with_cancelled=true&limit=1'))
    if not found:
        raise ApiError(f'no task {key} that this key can see')
    return found[0]


def blockers(task_id: str) -> list[dict]:
    """The tasks standing in front of this one, still unfinished.

    `blocks` is stored once and read from both ends: the end that WAITS sees
    it as `incoming`. A blocker already done or cancelled is history rather
    than an obstacle, so it is left out — a list that keeps them is a list
    people stop reading.
    """
    links = rows(get(f'/v1/project/tasks/{task_id}/links'))
    return [
        link
        for link in links
        if link.get('kind') == 'blocks'
        and link.get('direction') == 'incoming'
        and link.get('task_status') not in ('done', 'cancelled')
    ]

