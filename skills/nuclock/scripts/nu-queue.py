#!/usr/bin/env python3
"""What a session starts with: what is running, what is in flight, what is next.

Three questions, and the first is the one that costs money when it is skipped.
Printed together because asking them separately is exactly what people stop
doing on a busy morning.

The queue also says which rows are BLOCKED. "What is next" that lists work
somebody cannot start yet is a queue people learn to distrust — and the answer
is one call per row, which is cheap enough for the ten rows this prints.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _nuclock as nu  # noqa: E402


def main() -> int:
    try:
        timer = nu.running_timer()
        flight = nu.my_tasks('in_progress')
        queued = nu.my_tasks('todo', 10)
    except (nu.NoKeyError, nu.ApiError) as err:
        print(f'nuclock: {err}', file=sys.stderr)
        return 1

    if timer:
        print(f'running   {timer["task_key"]}  {timer["task_title"][:64]}')
        print(f'          since {timer["started_at"]}')
    else:
        print('running   nothing — start one before you write code')

    print('\nin flight')
    if not flight:
        print('          nothing')
    for task in flight:
        mark = '*' if task.get('is_running_by_me') else ' '
        print(f'        {mark} {task["key"]:9} {task["title"][:72]}')

    print('\nnext')
    if not queued:
        print('          nothing queued')
    for task in queued:
        # A blocker nobody can see is a queue that lies about being ready. The
        # call is skipped where it cannot matter — a task with no links comes
        # back empty either way, but this way the failure of ONE lookup does
        # not take the whole queue down with it.
        try:
            waiting = nu.blockers(task['id'])
        except nu.ApiError:
            waiting = []
        mark = '!' if waiting else ' '
        print(f'        {mark} {task["key"]:9} {task["title"][:72]}')
        for blocker in waiting:
            print(f'            blocked by {blocker["task_key"]} '
                  f'({blocker["task_status"]}) {blocker["task_title"][:44]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
