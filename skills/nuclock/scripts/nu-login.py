#!/usr/bin/env python3
"""Sign the scripts and hooks in to nuclock, the way a command line does (NUC-602).

    nu-login.py           # ask for a code, print it, wait for the approval
    nu-login.py --start   # ask for a code, print it, and return at once
    nu-login.py --wait    # wait for the code `--start` printed

The device grant (RFC 8628): the provider gives a short code and a URL, the
person approves THERE — in a browser they already trust, on the same consent
page an assistant gets — and this polls until the token is issued, then caches
it 0600 for every other script (`_nuclock.keep`). Nothing is pasted, and the
token ends with the person's session rather than living for ever in a profile.

Two halves because `/nu-login` cannot show a line while it waits: a command's
`!` output arrives when the command ENDS, so a code printed by a process still
polling is a code nobody sees. `--start` prints and returns; `--wait` is then
run on its own. In a terminal the plain form does both.

Exit 0 when signed in (or the code is out, for `--start`); 1 when the person
declined or the code ran out — an answer; 2 when the provider or the API could
not be asked.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _nuclock as nu  # noqa: E402

#: RFC 8628 §3.5: a `slow_down` adds five seconds to every poll after it.
SLOW_DOWN = 5
GRANT = 'urn:ietf:params:oauth:grant-type:device_code'


class Declined(RuntimeError):
    """The person said no, or let the code run out — an answer, not a failure."""


def start() -> dict:
    """Ask the provider for a code, keep it for `wait`, and say where to approve it."""
    endpoints = nu.provider()
    status, answer = nu.form(endpoints['device_endpoint'], {'client_id': nu.CLIENT_ID, 'scope': nu.SCOPES})
    if status != 200 or not answer.get('device_code'):
        reason = answer.get('error_description') or answer.get('error') or status
        if answer.get('error') in ('invalid_client', 'unauthorized_client'):
            raise nu.ApiError(
                f'{endpoints["issuer"]} has no `{nu.CLIENT_ID}` client to sign a command in with ({reason}) — '
                'use a key in NUCLOCK_API_KEY instead',
            )
        raise nu.ApiError(f'the provider would not start a sign-in: {reason}')
    pending = {
        **endpoints,
        'api': nu.API,
        'device_code': answer['device_code'],
        'interval': int(answer.get('interval') or 5),
        'expires_at': time.time() + float(answer.get('expires_in') or 600),
    }
    nu.write_private(nu.device_file(), pending)
    link = answer.get('verification_uri_complete') or answer.get('verification_uri')
    minutes = max(1, round(float(answer.get('expires_in') or 600) / 60))
    print(f'Open {link}')
    print(f'and confirm the code {answer.get("user_code")} there. It is good for {minutes} minutes.')
    return pending


def wait(pending: dict | None = None) -> str:
    """Poll for the token, cache it, and return who it signed in.

    `authorization_pending` is the person still reading the page; `slow_down`
    is the provider asking for a longer interval, and it is honoured for every
    poll after it, as the RFC says.
    """
    pending = pending or nu.read_private(nu.device_file())
    if not pending or pending.get('api') != nu.API:
        raise Declined('no sign-in is waiting — run /nu-login first')
    interval = int(pending.get('interval') or 5)
    while True:
        if time.time() >= float(pending['expires_at']):
            nu.forget_device()
            raise Declined('the code ran out before it was approved — run /nu-login again')
        time.sleep(interval)
        status, answer = nu.form(pending['token_endpoint'], {
            'grant_type': GRANT, 'device_code': pending['device_code'], 'client_id': nu.CLIENT_ID,
        })
        if status == 200 and answer.get('access_token'):
            break
        error = answer.get('error')
        if error == 'authorization_pending':
            continue
        if error == 'slow_down':
            interval += SLOW_DOWN
            continue
        nu.forget_device()
        if error == 'expired_token':
            raise Declined('the code ran out before it was approved — run /nu-login again')
        if error == 'access_denied':
            raise Declined('the sign-in was declined at the provider')
        if status >= 500:
            raise nu.ApiError(f'{status} from {pending["token_endpoint"]}')
        raise Declined(f'the provider refused the sign-in: {answer.get("error_description") or error or status}')
    nu.keep(pending, answer)
    nu.forget_device()
    try:
        me = nu.get('/v1/user/me')
    except (nu.ApiError, nu.NoKeyError):
        return 'signed in'
    return f'signed in as {me.get("email")}' if isinstance(me, dict) and me.get('email') else 'signed in'


def main(argv: list[str]) -> int:
    mode = argv[0] if argv else ''
    if mode not in ('', '--start', '--wait'):
        print('usage: nu-login.py [--start | --wait]', file=sys.stderr)
        return 2
    try:
        pending = start() if mode in ('', '--start') else None
        if mode == '--start':
            # Said so the one running it knows the second half, by its real path.
            print(f'Then: python3 "{Path(__file__).resolve()}" --wait')
            return 0
        print(f'nuclock: {wait(pending)}')
    except Declined as err:
        print(f'nuclock: {err}', file=sys.stderr)
        return 1
    except nu.ApiError as err:
        print(f'nuclock: {err}', file=sys.stderr)
        return nu.UNREACHABLE
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
