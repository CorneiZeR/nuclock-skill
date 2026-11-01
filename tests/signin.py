#!/usr/bin/env python3
"""The sign-in, against a stubbed provider and a stubbed tracker (NUC-602).

One local server plays both: the API's protected-resource metadata naming the
provider, the provider's discovery, device, token and revocation endpoints,
and two API paths that want a bearer. Each check tells it what to answer, and
`time.sleep` is replaced by a recorder, so the polling interval is asserted
rather than waited out.

Prints one line per check in `tests/run.sh`'s own format and exits with the
number that failed.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import pathlib
import stat
import sys
import tempfile
import threading
import time
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

HERE = pathlib.Path(__file__).resolve().parent.parent / 'skills' / 'nuclock' / 'scripts'

#: What the stub answers. `token` is a list of (status, body) the token
#: endpoint hands out in turn; `api_401` is how many API calls are refused
#: before one is let through.
STATE: dict = {}
CALLS: list[tuple[str, dict]] = []


class Stub(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        """Quiet."""

    def _answer(self, body: object, code: int = 200) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        base = f'http://127.0.0.1:{self.server.server_port}'
        if self.path == '/.well-known/oauth-protected-resource/mcp':
            self._answer({'authorization_servers': [f'{base}/realms/r']})
        elif self.path == '/realms/r/.well-known/openid-configuration':
            self._answer({
                'issuer': f'{base}/realms/r',
                'device_authorization_endpoint': f'{base}/realms/r/device',
                'token_endpoint': f'{base}/realms/r/token',
                'revocation_endpoint': f'{base}/realms/r/revoke',
            })
        elif self.path in ('/v1/user/me', '/v1/project/timer'):
            CALLS.append(('api', {'authorization': self.headers.get('Authorization', '')}))
            if STATE.get('api_401', 0) > 0:
                STATE['api_401'] -= 1
                self._answer({'detail': 'expired'}, 401)
            elif self.path == '/v1/user/me':
                self._answer({'email': 'ann@example.com'})
            else:
                self._answer({'task_id': 't', 'task_key': 'NUC-1'})
        else:
            self._answer({'message': 'not stubbed'}, 404)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get('Content-Length') or 0)
        fields = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}
        CALLS.append((self.path, fields))
        if self.path == '/realms/r/device':
            self._answer({
                'device_code': 'dev', 'user_code': 'ABCD-EFGH', 'interval': 1, 'expires_in': 600,
                'verification_uri': 'https://id/device',
                'verification_uri_complete': 'https://id/device?user_code=ABCD-EFGH',
            })
        elif self.path == '/realms/r/token':
            status, body = STATE['token'].pop(0)
            self._answer(body, status)
        elif self.path == '/realms/r/revoke':
            self._answer({}, STATE.get('revoke', 200))
        else:
            self._answer({'message': 'not stubbed'}, 404)


def load(name: str):
    """A script as a module, so its pieces can be called and its sleep replaced."""
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), HERE / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def issued(access: str, refresh: str = 'r1', expires: int = 300) -> tuple[int, dict]:
    return 200, {'access_token': access, 'refresh_token': refresh, 'expires_in': expires}


def oauth_error(error: str) -> tuple[int, dict]:
    return 400, {'error': error}


failures = 0


def check(what: str, expected: object, actual: object) -> None:
    global failures  # noqa: PLW0603 — one counter for one run
    if expected == actual:
        print(f'  ok    {what}')
    else:
        print(f'  FAIL  {what}\n        expected: {expected}\n        actual:   {actual}')
        failures += 1


def run(module, *argv: str) -> tuple[int, str]:
    """A script's `main`, with what it printed — both streams, as a person sees them."""
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(out):
        code = module.main(list(argv)) if argv or module.__name__ == 'nu_login' else module.main()
    return code, out.getvalue()


def main() -> int:
    server = ThreadingHTTPServer(('127.0.0.1', 0), Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    work = pathlib.Path(tempfile.mkdtemp())
    os.environ.pop('NUCLOCK_API_KEY', None)
    os.environ.pop('NUCLOCK_ISSUER', None)
    os.environ.pop('CLAUDE_CONFIG_DIR', None)
    os.environ['HOME'] = str(work / 'home')
    os.environ['XDG_STATE_HOME'] = str(work / 'state')
    os.environ['NUCLOCK_API_URL'] = f'http://127.0.0.1:{server.server_port}'

    nu = load('_nuclock')
    sys.modules['_nuclock'] = nu
    login, logout = load('nu-login'), load('nu-logout')
    slept: list[float] = []
    login.time.sleep = slept.append  # the module's own `time`, which is the one `wait` calls

    def fresh(*tokens: tuple[int, dict]) -> None:
        nu.forget()
        slept.clear()
        CALLS.clear()
        STATE.clear()
        STATE['token'] = list(tokens)

    print('signing in')

    fresh(issued('a1'))
    code, said = run(login)
    check('the link and the code are printed', True, 'user_code=ABCD-EFGH' in said and 'ABCD-EFGH there' in said)
    check('signs in and says who', (0, True), (code, 'signed in as ann@example.com' in said))
    device = next(fields for path, fields in CALLS if path == '/realms/r/device')
    check('asks the assistant\'s two rights, as nuclock-cli', ('nuclock-cli', 'nuclock:read nuclock:write'),
          (device.get('client_id'), device.get('scope')))
    mode = stat.S_IMODE(nu.token_file().stat().st_mode)
    check('the cache is readable by this user alone', '0o600', oct(mode))
    check('in a directory nobody else can list', '0o700', oct(stat.S_IMODE(nu.state_dir().stat().st_mode)))
    check('and the code waiting for approval is gone', False, nu.device_file().exists())

    fresh(oauth_error('authorization_pending'), issued('a1'))
    code, _ = run(login)
    check('waits while the person is still reading the page', (0, [1, 1]), (code, slept))

    fresh(oauth_error('slow_down'), oauth_error('authorization_pending'), issued('a1'))
    run(login)
    check('slow_down adds five seconds to every poll after it', [1, 6, 6], slept)

    fresh(oauth_error('expired_token'))
    code, said = run(login)
    check('a code that ran out is said plainly', (1, True), (code, 'run /nu-login again' in said))
    check('and nothing is cached', False, nu.token_file().exists())

    fresh(oauth_error('access_denied'))
    code, said = run(login)
    check('a declined sign-in is an answer, not a crash', (1, True), (code, 'declined' in said))

    fresh(issued('a2'))
    code, said = run(login, '--start')
    check('--start prints the code and returns without polling', (0, [], True),
          (code, slept, nu.device_file().exists()))
    check('and names the second half by its real path', True, f'"{HERE / "nu-login.py"}" --wait' in said)
    code, said = run(login, '--wait')
    check('--wait collects what --start asked for', (0, True), (code, 'signed in' in said))

    print('using it')

    fresh(issued('a1'))
    run(login)
    check('the cached token is what the scripts send', 'Bearer a1', nu.key())

    os.environ['NUCLOCK_API_KEY'] = 'ci'
    check('a key in the environment still wins — CI has no browser', 'Api-Key ci', nu.key())
    del os.environ['NUCLOCK_API_KEY']

    saved = json.loads(nu.token_file().read_text())
    saved['expires_at'] = time.time() - 1
    nu.token_file().write_text(json.dumps(saved))
    STATE['token'] = [issued('a3', 'r3')]
    CALLS.clear()
    check('a spent access token is renewed silently', 'Bearer a3', nu.key())
    renewal = next(fields for path, fields in CALLS if path == '/realms/r/token')
    check('with the refresh token it was given', ('refresh_token', 'r1'),
          (renewal.get('grant_type'), renewal.get('refresh_token')))
    check('and the renewed one is kept, 0600', ('r3', '0o600'),
          (json.loads(nu.token_file().read_text())['refresh_token'], oct(stat.S_IMODE(nu.token_file().stat().st_mode))))

    STATE['token'] = [issued('a4', 'r4')]
    STATE['api_401'] = 1
    CALLS.clear()
    try:
        timer = nu.running_timer()
    except nu.ApiError:
        timer = None
    sent = [fields['authorization'] for path, fields in CALLS if path == 'api']
    check('a 401 renews once and sends the call again', (['Bearer a3', 'Bearer a4'], 'NUC-1'),
          (sent, (timer or {}).get('task_key')))

    STATE['token'] = [issued('a5', 'r5')]
    STATE['api_401'] = 5
    CALLS.clear()
    try:
        nu.running_timer()
        outcome = 'answered'
    except nu.ApiError as err:
        outcome = str(err).split(' ')[0]
    check('and a second 401 is the answer, not a loop', ('401', 2),
          (outcome, sum(1 for path, _ in CALLS if path == 'api')))

    saved = json.loads(nu.token_file().read_text())
    saved['expires_at'] = time.time() - 1
    nu.token_file().write_text(json.dumps(saved))
    STATE['token'] = [oauth_error('invalid_grant')]
    try:
        nu.key()
        outcome = 'no refusal'
    except nu.NoKeyError as err:
        outcome = 'sign in again' if '/nu-login' in str(err) else str(err)
    check('a refused refresh says to sign in again', 'sign in again', outcome)
    check('and drops the dead token', False, nu.token_file().exists())

    fresh(issued('a1'))
    run(login)
    os.environ['NUCLOCK_API_URL'] = 'http://127.0.0.1:1'
    nu.API = os.environ['NUCLOCK_API_URL']
    try:
        nu.key()
        outcome = 'offered'
    except nu.NoKeyError:
        outcome = 'not offered'
    check('a token for one API is never offered to another', 'not offered', outcome)
    nu.API = f'http://127.0.0.1:{server.server_port}'

    print('signing out')

    STATE['revoke'] = 200
    CALLS.clear()
    code, said = run(logout)
    revoked = next((fields for path, fields in CALLS if path == '/realms/r/revoke'), {})
    check('the refresh token is revoked at the provider', ('r1', 'nuclock-cli'),
          (revoked.get('token'), revoked.get('client_id')))
    check('and the cache is gone', (0, False), (code, nu.token_file().exists()))

    fresh(issued('a1'))
    run(login)
    STATE['revoke'] = 503
    code, said = run(logout)
    check('a provider that cannot be told still loses the file, and that is said',
          (2, False, True), (code, nu.token_file().exists(), 'not told' in said))

    server.shutdown()
    return failures


if __name__ == '__main__':
    raise SystemExit(main())
