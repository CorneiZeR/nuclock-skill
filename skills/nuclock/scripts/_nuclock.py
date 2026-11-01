"""Talking to nuclock from a script, as the person themselves.

Imported by everything else here. Four decisions worth knowing about:

**The plugin signs itself in, as a command line does** (NUC-602). `nu-login`
runs the device grant (RFC 8628) against the provider the API names, and the
token it is given is cached here, 0600, and refreshed when it is spent — no
pasted secret, no key living for ever in a shell profile. The provider is
DISCOVERED, never written in: the API's own protected-resource metadata names
it, so the same plugin signs in to any organisation running nuclock.

**The credential is looked for in one order**: `NUCLOCK_API_KEY` (CI has no
browser), the signed-in token, then the MCP server's own header in a Claude
Code config for whoever still has one. Nothing here prints a credential or
passes one as an argument (an argument is visible in `ps` to everybody on the
machine). Finding none is `NO_CREDENTIAL` rather than a failure to reach
anything — see the two statuses below.

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

import contextlib
import json
import os
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

API = os.environ.get('NUCLOCK_API_URL', 'https://api.clock.nuspect.net').rstrip('/')
TIMEOUT = 15

#: The provider's public client for a command line — published, because a
#: plugin ships it and a public client's id is no secret.
CLIENT_ID = os.environ.get('NUCLOCK_CLIENT_ID', 'nuclock-cli')
#: The assistant's two rights, so the person approving reads the same sentence.
SCOPES = 'nuclock:read nuclock:write'
#: An access token this close to its end is treated as spent: it would expire
#: on the way to the API and come back as a 401.
EARLY = 30
SIGN_IN = 'sign in with /nu-login (or `nu-login.py` in a terminal)'

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


def state_dir() -> pathlib.Path:
    """Where the sign-in is kept: `$XDG_STATE_HOME/nuclock`, `~/.local/state` by default.

    A file rather than the macOS keychain: the plugin runs on Linux too, and a
    0600 file is the same promise everywhere without a dependency. A relative
    `XDG_STATE_HOME` is ignored, as the specification says.
    """
    chosen = os.environ.get('XDG_STATE_HOME', '')
    base = pathlib.Path(chosen) if os.path.isabs(chosen) else pathlib.Path.home() / '.local' / 'state'
    return base / 'nuclock'


def token_file() -> pathlib.Path:
    """The cached sign-in: access token, its end, refresh token, and where to renew them."""
    return state_dir() / 'token.json'


def device_file() -> pathlib.Path:
    """A code `nu-login --start` asked for and `--wait` has not collected yet."""
    return state_dir() / 'device.json'


def write_private(path: pathlib.Path, body: dict) -> None:
    """Write JSON readable by this user alone, replacing the file in one step.

    Created 0600 rather than chmodded after: a token that is world-readable for
    a moment is world-readable. The directory is 0700 for the same reason.
    """
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    scratch = path.with_name(f'.{path.name}.{os.getpid()}')
    with contextlib.suppress(FileNotFoundError):
        scratch.unlink()
    with os.fdopen(os.open(scratch, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as out:
        json.dump(body, out)
    os.replace(scratch, path)


def read_private(path: pathlib.Path) -> dict | None:
    """A file `write_private` wrote, or None when it is missing or unreadable."""
    try:
        body = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return body if isinstance(body, dict) else None


def fetch_json(url: str) -> dict:
    """GET a public document — metadata, discovery — with no credential."""
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as answer:  # noqa: S310 — the API's and its provider's
            body = json.loads(answer.read() or b'null')
    except urllib.error.HTTPError as err:
        raise ApiError(f'{err.code} from {url}') from err
    except (urllib.error.URLError, TimeoutError) as err:
        raise ApiError(f'could not reach {url}: {err}') from err
    except ValueError as err:
        raise ApiError(f'{url} answered something that is not JSON') from err
    if not isinstance(body, dict):
        raise ApiError(f'{url} answered something that is not an object')
    return body


def form(url: str, fields: dict) -> tuple[int, dict]:
    """POST a form to the provider and return its status and body.

    An OAuth refusal is a 400 with a JSON body naming the `error`, and that is
    an ANSWER the caller reads (`authorization_pending`, `invalid_grant`), so
    it is returned rather than raised. Only not reaching the provider raises.
    """
    request = urllib.request.Request(  # noqa: S310 — the provider the API named
        url,
        data=urllib.parse.urlencode(fields).encode(),
        method='POST',
        headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:  # noqa: S310
            status, raw = answer.status, answer.read()
    except urllib.error.HTTPError as err:
        status, raw = err.code, err.read()
    except (urllib.error.URLError, TimeoutError) as err:
        raise ApiError(f'could not reach {url}: {err}') from err
    try:
        body = json.loads(raw or b'{}')
    except ValueError:
        body = {}
    return status, body if isinstance(body, dict) else {}


def provider() -> dict:
    """The identity provider this API trusts, and its endpoints.

    Read from the API's own protected-resource metadata (RFC 9728) — the
    document an assistant reads to find where to sign in — so nothing names a
    host here, and an organisation on its own domain signs in at its own
    realm. `NUCLOCK_ISSUER` overrides it, for a provider the metadata does not
    name. An API that names none has no sign-in to offer; that is said, and
    a key is the way left.
    """
    issuer = os.environ.get('NUCLOCK_ISSUER', '')
    if not issuer:
        try:
            meta = fetch_json(f'{API}/.well-known/oauth-protected-resource/mcp')
        except ApiError as err:
            if str(err).startswith('404 '):
                raise ApiError(f'{API} offers no sign-in — use a key in NUCLOCK_API_KEY instead') from err
            raise
        issuer = next(iter(meta.get('authorization_servers') or []), '')
        if not issuer:
            raise ApiError(f'{API} names no identity provider — use a key in NUCLOCK_API_KEY instead')
    issuer = issuer.rstrip('/')
    found = fetch_json(f'{issuer}/.well-known/openid-configuration')
    endpoints = {
        'issuer': issuer,
        'device_endpoint': found.get('device_authorization_endpoint') or '',
        'token_endpoint': found.get('token_endpoint') or '',
        'revocation_endpoint': found.get('revocation_endpoint') or '',
    }
    if not endpoints['device_endpoint'] or not endpoints['token_endpoint']:
        raise ApiError(f'{issuer} does not offer the device grant a command signs in with')
    return endpoints


def keep(endpoints: dict, answer: dict) -> None:
    """Cache what the token endpoint issued, beside where to renew it.

    The API it was issued FOR is written down too: a token for one
    organisation is not offered to another's API when `NUCLOCK_API_URL` moves.
    """
    write_private(token_file(), {
        'api': API,
        'issuer': endpoints['issuer'],
        'token_endpoint': endpoints['token_endpoint'],
        'revocation_endpoint': endpoints.get('revocation_endpoint', ''),
        'access_token': answer['access_token'],
        'expires_at': time.time() + float(answer.get('expires_in') or 0),
        # RFC 6749 §6: a renewal may come without a new refresh token, and then
        # the one already held is still the one to use.
        'refresh_token': answer.get('refresh_token') or endpoints.get('refresh_token') or '',
    })


def forget() -> None:
    """Drop the cached sign-in and any code still waiting to be approved."""
    with contextlib.suppress(FileNotFoundError):
        token_file().unlink()
    forget_device()


def forget_device() -> None:
    """Drop a code waiting to be approved, and nothing else."""
    with contextlib.suppress(FileNotFoundError):
        device_file().unlink()


def signed_in(renew: bool = False) -> str | None:
    """The cached sign-in as an Authorization header, renewed when it is spent.

    None when there is no sign-in for THIS API. `renew` refreshes whatever the
    clock says — what a 401 means for a token the clock still thought good. A
    refresh the provider refuses ends the sign-in: the cache is dropped and the
    sentence says to sign in again, rather than offering the same dead token
    on every call. A provider that cannot be reached is a blink (`ApiError`).
    """
    saved = read_private(token_file())
    if not saved or saved.get('api') != API or not saved.get('access_token'):
        return None
    if not renew and float(saved.get('expires_at') or 0) - EARLY > time.time():
        return f'Bearer {saved["access_token"]}'
    refresh = saved.get('refresh_token')
    if not refresh:
        forget()
        raise NoKeyError(f'the nuclock sign-in has ended — {SIGN_IN}')
    status, answer = form(saved['token_endpoint'], {
        'grant_type': 'refresh_token', 'refresh_token': refresh, 'client_id': CLIENT_ID,
    })
    if status == 200 and answer.get('access_token'):
        keep(saved, answer)
        return f'Bearer {answer["access_token"]}'
    if status >= 500:
        raise ApiError(f'{status} from {saved["token_endpoint"]}')
    forget()
    reason = answer.get('error_description') or answer.get('error') or status
    raise NoKeyError(f'the nuclock sign-in has ended ({reason}) — {SIGN_IN}')


def credential() -> tuple[str, bool]:
    """The Authorization header value, and whether it is the renewable sign-in.

    Order: the environment, because CI has no browser and must be able to say
    so outright; then the sign-in `nu-login` cached; then every nuclock entry
    in every config this session could mean. Nothing found is `NoKeyError`,
    and its sentence says WHICH of the nothings it was — no entry at all, an
    entry with no header (an assistant signed in at the provider), or a config
    that could not be read — and every one of them says how to sign in.
    """
    from_env = os.environ.get('NUCLOCK_API_KEY')
    if from_env:
        return (from_env if from_env.startswith('Api-Key ') else f'Api-Key {from_env}'), False
    cached = signed_in()
    if cached:
        return cached, True
    connected = unreadable = False
    for config in configs():
        entries, broken = servers(config)
        unreadable = unreadable or broken
        for entry in entries:
            header = (entry.get('headers') or {}).get('Authorization')
            if header:
                return header, False
            connected = True
    if connected:
        raise NoKeyError(
            'the scripts are not signed in, and the nuclock assistant signed in at the identity '
            f'provider leaves them nothing to borrow — {SIGN_IN}',
        )
    if unreadable:
        raise NoKeyError(f'the scripts are not signed in, and the Claude Code config could not be read — {SIGN_IN}')
    raise NoKeyError(f'the scripts are not signed in, and no nuclock MCP server is configured — {SIGN_IN}')


def key() -> str:
    """The Authorization header value, as the API expects it — see `credential`."""
    return credential()[0]


def call(request: urllib.request.Request) -> bytes:
    """Send a request with the person's credential, and read the answer.

    A 401 on the signed-in token is the provider's clock and ours disagreeing,
    or a session ended early: the token is renewed ONCE and the call sent
    again. A second 401 is the answer. A key is never renewed — it has nothing
    to renew with.
    """
    header, renewable = credential()
    for attempt in (1, 2):
        request.add_header('Authorization', header)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:  # noqa: S310 — the app's own host
                return answer.read()
        except urllib.error.HTTPError as err:
            if err.code != 401 or not renewable or attempt == 2:
                raise
            header = signed_in(renew=True) or header


def get(path: str) -> object:
    """GET a path and return the decoded body."""
    request = urllib.request.Request(f'{API}{path}')  # noqa: S310 — the host is this app's own
    try:
        body = call(request) or b'null'
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
        headers={'Content-Type': 'application/json'},
    )
    try:
        return json.loads(call(request) or b'null')
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

