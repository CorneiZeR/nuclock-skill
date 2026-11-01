#!/usr/bin/env python3
"""Sign the scripts out: the token is revoked at the provider, then forgotten here.

Revoking the REFRESH token ends the session it belongs to, so logging out means
something on the server and not only a file removed. The file goes either way —
a provider that cannot be reached must not leave somebody signed in on a
machine they asked to sign out of — and that case is said, because the session
then lives on until the provider ends it.

Exit 0 when signed out (or never signed in), 2 when the provider could not be
told and only the local copy is gone.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _nuclock as nu  # noqa: E402


def main() -> int:
    saved = nu.read_private(nu.token_file())
    if not saved:
        nu.forget()
        print('nuclock: not signed in')
        return 0
    endpoint, token = saved.get('revocation_endpoint'), saved.get('refresh_token')
    try:
        if endpoint and token:
            status, _ = nu.form(endpoint, {
                'token': token, 'token_type_hint': 'refresh_token', 'client_id': nu.CLIENT_ID,
            })
            if status != 200:
                raise nu.ApiError(f'{status} from {endpoint}')
    except nu.ApiError as err:
        nu.forget()
        print(f'nuclock: signed out here, but the provider was not told ({err}) — '
              'the session ends when the provider ends it', file=sys.stderr)
        return nu.UNREACHABLE
    nu.forget()
    print('nuclock: signed out')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
