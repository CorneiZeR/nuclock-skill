#!/usr/bin/env python3
"""Put the queue in front of whoever just opened a session.

What is running, what is in flight, what is next — as context the assistant
reads rather than as a line in a terminal, because the thing that goes wrong
is not "nobody printed it", it is "nobody looked".

Silent when the tracker cannot be reached, and silent when there is nothing to
say: a session that opens with a wall of text teaches people to scroll past it.
Not silent when there is no credential at all: the assistant would otherwise
read an empty queue as an empty backlog (NUC-601).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUEUE = Path(os.environ.get('NUCLOCK_QUEUE', HERE.parent / 'skills' / 'nuclock' / 'scripts' / 'nu-queue.py'))

#: `_nuclock.NO_CREDENTIAL`, kept in step by `tests/run.sh` — see the note in
#: `editing-without-a-timer.py` for why a hook holds the number rather than
#: importing it.
NO_CREDENTIAL = 3


def context(sentence: str) -> int:
    """Hand the assistant one paragraph, which is all this hook can do."""
    print(json.dumps({
        'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': sentence},
    }))
    return 0


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
    if answer.returncode == NO_CREDENTIAL:
        # Said to the ASSISTANT rather than to the person, because that is what
        # this hook can emit — and because the damage is a model that reads
        # silence as "no work is open" and plans against an empty tracker.
        return context(
            'nuclock: the queue could not be read — the scripts that read it have no '
            'credential. The MCP tools are unaffected, so ASK the tracker through them '
            'rather than assuming the backlog is empty. The scripts (`nu-queue`, '
            '`nu-start`, `nu-finish`) and the timer hooks stay off until NUCLOCK_API_KEY '
            'is set — a `write` key with no abilities is enough.',
        )
    if answer.returncode != 0 or not answer.stdout.strip():
        return 0

    return context(
        'nuclock — the tracker this work is billed from:\n\n'
        f'{answer.stdout.strip()}\n\n'
        'Move a task to in_progress and start its timer BEFORE writing '
        'code; stop it when the work stops. Never write time nobody '
        'asked for.',
    )


if __name__ == '__main__':
    raise SystemExit(main())
