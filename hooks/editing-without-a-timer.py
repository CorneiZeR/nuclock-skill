#!/usr/bin/env python3
"""Warn once when a session edits code with no timer running.

This is the hook the whole skill exists for. The failure it catches is not
dramatic: work starts, the timer does not, and two hours later somebody writes
"about two hours" into a form.

Three rules it keeps, each of them load-bearing:

**It never blocks.** A tracker holding somebody's editor hostage is a tracker
people turn off. The tool call goes through; the warning goes beside it.

**It never writes time.** A timer nobody started is time nobody can vouch for.
It says what is missing and leaves the decision where it belongs.

**It asks the tracker at most once per session, and never on the critical
path twice.** A network call on every edit would make a slow morning slower;
the answer is cached in a marker file keyed by the session, and a session that
has already been warned is left alone — a warning repeated forty times is a
warning nobody reads.

An unreachable tracker says NOTHING. "Your timer is off" because the network
blinked is worse than silence: it teaches people to ignore the hook.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
#: Overridable so the tests can hand it a stub — nothing else sets it, and a
#: test that rewrote the real script in place is what this replaced.
RUNNING = Path(os.environ.get('NUCLOCK_RUNNING', HERE.parent / 'skills' / 'nuclock' / 'scripts' / 'nu-running.py'))

#: How long "a timer was running" is trusted, so a burst of edits costs one
#: call. Only that answer expires — being TOLD does not.
CACHE_SECONDS = 300

#: How long a claim to be ASKING is trusted before another process takes it
#: over. Longer than the call's own timeout, so a slow tracker is waited out
#: rather than asked twice; short enough that a killed hook does not silence
#: the next one for the session.
CLAIM_SECONDS = 20


def marker(kind: str, session: str) -> Path:
    return Path(tempfile.gettempdir()) / f'nuclock-{kind}-{session or "unknown"}'


def asked_recently(path: Path) -> bool:
    """Whether the tracker was asked lately and said a timer was running."""
    try:
        return (time.time() - path.stat().st_mtime) < CACHE_SECONDS
    except OSError:
        return False


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or '{}')
    except ValueError:
        return 0

    session = str(event.get('session_id', ''))
    told, asked = marker('told', session), marker('asked', session)
    # Told once, and that is the end of it for this session: a warning
    # repeated every five minutes is a warning people learn to scroll past.
    if told.exists() or asked_recently(asked):
        return 0

    # One asker at a time. Claude Code fires this hook for tool calls that run
    # in parallel, so two processes reach here together, both find no marker,
    # both ask the tracker and both warn. The claim is `O_EXCL`, which is the
    # only check-and-create that cannot interleave.
    claim = marker('asking', session)
    try:
        os.close(os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        if (time.time() - claim.stat().st_mtime) < CLAIM_SECONDS:
            return 0
        # Stale: whoever held it was killed mid-call. Take it over rather than
        # leave the session unwarned for ever.
        claim.touch()
    except OSError:
        return 0

    try:
        answer = subprocess.run(  # noqa: S603
            [sys.executable, str(RUNNING)],
            capture_output=True, text=True, timeout=8, check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return 0
    finally:
        with contextlib.suppress(OSError):
            claim.unlink()

    # 2 is "could not ask" — the network, the key, the tracker. Silence.
    if answer.returncode != 1:
        if answer.returncode == 0:
            asked.touch()
        return 0

    told.touch()
    print(json.dumps({
        'systemMessage': (
            'nuclock: no timer is running, and this session is changing code. '
            'Start one (start_timer) or, if the work belongs to something '
            'already open, park it — hours reconstructed later are the ones '
            'that get argued about.'
        ),
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
