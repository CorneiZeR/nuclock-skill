#!/usr/bin/env python3
"""What is being tracked right now, in one line. Exit 1 when nothing is.

Written to be asked by a hook as well as by a person, which is why it is quiet
and why the exit status carries the answer: a hook reads the status, a person
reads the line.

An unreachable tracker exits 2, kept apart from "nothing is running" on
purpose — a hook must not tell somebody their timer is off because the network
was down for a second.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _nuclock as nu  # noqa: E402


def main() -> int:
    try:
        timer = nu.running_timer()
    except (nu.NoKeyError, nu.ApiError) as err:
        print(f'nuclock: {err}', file=sys.stderr)
        return 2
    if not timer:
        print('no timer is running')
        return 1
    print(f'{timer["task_key"]} — {timer["task_title"][:70]} (since {timer["started_at"]})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
