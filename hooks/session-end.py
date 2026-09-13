#!/usr/bin/env python3
"""Say so when a session ends with a timer still running.

A timer left running overnight is the other half of the problem this skill is
about: the first half invents hours that were never recorded, this one records
hours nobody worked. The tracker stops a runaway timer on its own eventually,
and the entry it leaves behind is marked as auto-stopped — which is a repair,
not a record.

It stops nothing. A session ending is not proof the work ended: somebody may
be closing one window and carrying on in another.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
#: Overridable so the tests can hand it a stub — nothing else sets it, and a
#: test that rewrote the real script in place is what this replaced.
RUNNING = Path(os.environ.get('NUCLOCK_RUNNING', HERE.parent / 'skills' / 'nuclock' / 'scripts' / 'nu-running.py'))


def main() -> int:
    try:
        json.loads(sys.stdin.read() or '{}')
    except ValueError:
        return 0

    try:
        answer = subprocess.run(  # noqa: S603
            [sys.executable, str(RUNNING)],
            capture_output=True, text=True, timeout=8, check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return 0
    if answer.returncode != 0:
        # 1 is "nothing running", which is the good case; 2 is "could not
        # ask", which is not worth a message either.
        return 0

    print(json.dumps({
        'systemMessage': (
            f'nuclock: a timer is still running — {answer.stdout.strip()}. '
            'Stop it if the work stopped; the tracker will otherwise close it '
            'for you and mark the entry as auto-stopped.'
        ),
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
