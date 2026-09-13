#!/usr/bin/env python3
"""Put the queue in front of whoever just opened a session.

What is running, what is in flight, what is next — as context the assistant
reads rather than as a line in a terminal, because the thing that goes wrong
is not "nobody printed it", it is "nobody looked".

Silent when the tracker cannot be reached, and silent when there is nothing to
say: a session that opens with a wall of text teaches people to scroll past it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUEUE = Path(os.environ.get('NUCLOCK_QUEUE', HERE.parent / 'scripts' / 'nu-queue.py'))


def main() -> int:
    try:
        json.loads(sys.stdin.read() or '{}')
    except ValueError:
        return 0

    try:
        answer = subprocess.run(  # noqa: S603
            [sys.executable, str(QUEUE)],
            capture_output=True, text=True, timeout=12, check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return 0
    if answer.returncode != 0 or not answer.stdout.strip():
        return 0

    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'SessionStart',
            'additionalContext': (
                'nuclock — the tracker this work is billed from:\n\n'
                f'{answer.stdout.strip()}\n\n'
                'Move a task to in_progress and start its timer BEFORE writing '
                'code; stop it when the work stops. Never write time nobody '
                'asked for.'
            ),
        },
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
