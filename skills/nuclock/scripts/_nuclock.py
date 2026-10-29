"""Talking to nuclock from a script, with the person's own key.

Imported by everything else here. Three decisions worth knowing about:

**The key is read from where it already is** — `NUCLOCK_API_KEY`, or the MCP
server's own header in a Claude Code config. Somebody who set the tools up
once does not set up a second credential for these scripts, and nothing here
writes the key anywhere, prints it, or passes it as an argument (an argument is
visible in `ps` to everybody on the machine). An assistant signed in through
the identity provider has no header to borrow, and that is `NO_CREDENTIAL`
rather than a failure to reach anything — see the two statuses below.

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
import urllib.parse
import urllib.request

API = os.environ.get('NUCLOCK_API_URL', 'https://api.clock.nuspect.net')
TIMEOUT = 15

#: What a script exits with when it could not ASK — the network, the host, a
#: refusal. A hook stays quiet on this one: "your timer is off" because a
#: connection blinked is worse than silence.
UNREACHABLE = 2

#: And what it exits with when nobody told it WHO the person is. Kept apart
#: from `UNREACHABLE`, because the two want different answers: a blink is
#: waited out, a missing credential is somebody's to fix. The hooks swallowed
#: both while they shared `2`, so the day the assistant moved to the identity
#: provider — and the header these scripts had been borrowing stopped existing
#: — the whole plugin went silently off (NUC-601).
NO_CREDENTIAL = 3


class NoKeyError(RuntimeError):
    """No credential anywhere this knows to look."""


class ApiError(RuntimeError):
    """The tracker answered, and the answer was not one we can use."""


def configs() -> list[pathlib.Path]:
    """The Claude Code configs to look in, the session's own first.

    `CLAUDE_CONFIG_DIR` is how one machine holds several installations side by
    side, and a script runs inside whichever session asked it — so that
    session's config is the one describing its tracker. `~/.claude.json` is
    the default and is read as well, because somebody with aliases still keeps
    one of them plain.
    """
    paths = []
    chosen = os.environ.get('CLAUDE_CONFIG_DIR')
    if chosen:
        paths.append(pathlib.Path(chosen).expanduser() / '.claude.json')
    paths.append(pathlib.Path.home() / '.claude.json')
    return [path for index, path in enumerate(paths) if path not in paths[:index]]


def servers(config: pathlib.Path) -> tuple[list[dict], bool]:
    """Every nuclock entry in one config, and whether the file defeated us.

    Two scopes hold one: the person's own `mcpServers`, and each project's —
    `claude mcp add` writes the second by default, so a tracker configured in
    the repository somebody works in lives there and nowhere else.
    """
    try:
        body = json.loads(config.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return [], False
    except (OSError, ValueError):
        # Unreadable or half-written. Said in the refusal below rather than
        # raised here: one unreadable config must not hide a key in the next.
        return [], True
    found = []
    scopes = [body.get('mcpServers')]
    scopes += [(project or {}).get('mcpServers') for project in (body.get('projects') or {}).values()]
    for scope in scopes:
        entry = (scope or {}).get('nuclock')
        if isinstance(entry, dict):
            found.append(entry)
    return found, False


def key() -> str:
    """The Authorization header value, as the API expects it.

    Order: the environment, because CI has no browser and must be able to say
    so outright; then every nuclock entry in every config this session could
    mean. Nothing found is `NoKeyError`, and its sentence says WHICH of the
    three nothings it was — no entry at all, an entry with no header (an
    assistant signed in at the provider), or a config that could not be read.
    """
    from_env = os.environ.get('NUCLOCK_API_KEY')
    if from_env:
        return from_env if from_env.startswith('Api-Key ') else f'Api-Key {from_env}'
    connected = unreadable = False
    for config in configs():
        entries, broken = servers(config)
        unreadable = unreadable or broken
        for entry in entries:
            header = (entry.get('headers') or {}).get('Authorization')
            if header:
                return header
            connected = True
    if connected:
        raise NoKeyError(
            'no NUCLOCK_API_KEY, and the nuclock assistant is signed in at the identity provider, '
            'which leaves a script nothing to read — issue a key for the scripts (a `write` key with '
            'no abilities is enough)',
        )
    if unreadable:
        raise NoKeyError('no NUCLOCK_API_KEY, and the Claude Code config could not be read')
    raise NoKeyError('no NUCLOCK_API_KEY, and no nuclock MCP server is configured')


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
    query = urllib.parse.urlencode({'mine': 'true', 'status': status, 'sort': 'rank', 'limit': limit})
    return rows(get(f'/v1/project/tasks?{query}'))


def task_by_key(key: str) -> dict:
    """One task, by the key people say out loud — `NUC-142`.

    Matched whole by the API, so `NUC-1` never answers with `NUC-14`, and it
    searches only what this key may already see: an unknown key and somebody
    else's task give the same empty answer, which is the same thing from the
    outside and deliberately so.
    """
    if not key.strip():
        raise ApiError('no task key given')
    query = urllib.parse.urlencode({'key': key, 'with_cancelled': 'true', 'limit': 1})
    found = rows(get(f'/v1/project/tasks?{query}'))
    # A filter the server did not apply returns the first task of the list,
    # and the timer would start on that one.
    if not found or (found[0].get('key') or '').casefold() != key.casefold():
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

