#!/usr/bin/env python3
"""Everything that has to happen before the first line of code, in one place.

    nu-start.py NUC-142
    nu-start.py NUC-142 --anyway    # a blocker you have decided to ignore

Three checks and two writes, in this order, because the order is the whole
value: a task nobody may start yet is not started, a timer already running is
not silently replaced, and the status moves BEFORE the work rather than after
it — a board that only changes at the end answers "what is done" and never
"what is happening".

What it refuses to do:

* **Stop somebody else's timer, or your own.** One timer runs per person, and
  which one it should be is a decision. This prints what is open and stops.
* **Push past a blocker quietly.** A blocked task can still be started —
  sometimes the blocker is stale, and the person can see that — but it takes
  `--anyway`, which puts the choice in the command rather than in a shrug.
* **Guess the task.** An unknown key and somebody else's task answer the same
  way, and both are a refusal rather than a new task created helpfully.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _nuclock as nu  # noqa: E402


def main() -> int:
    parsed = argparse.ArgumentParser(description='Start work on a task, honestly.')
    parsed.add_argument('key', help='the key people say out loud, e.g. NUC-142')
    parsed.add_argument(
        '--anyway',
        action='store_true',
        help='start even though something still blocks it',
    )
    args = parsed.parse_args()

    try:
        task = nu.task_by_key(args.key)
        running = nu.running_timer()
        waiting = nu.blockers(task['id'])
    except (nu.NoKeyError, nu.ApiError) as err:
        print(f'nuclock: {err}', file=sys.stderr)
        return 1

    if running and running.get('task_id') != task['id']:
        print(f'a timer is already running on {running["task_key"]} '
              f'— {running["task_title"][:56]}')
        print('stop it first, or finish what it belongs to: nu-finish.py '
              f'{running["task_key"]}')
        return 1

    if waiting and not args.anyway:
        print(f'{task["key"]} is blocked by:')
        for blocker in waiting:
            print(f'  {blocker["task_key"]} ({blocker["task_status"]}) '
                  f'{blocker["task_title"][:60]}')
        print('finish those first, or say --anyway if the link is stale')
        return 1

    if task.get('status') != 'in_progress':
        try:
            nu.put(f'/v1/project/tasks/{task["id"]}/status', {'status': 'in_progress'})
        except nu.ApiError as err:
            print(f'nuclock: could not move {task["key"]} to in_progress: {err}', file=sys.stderr)
            return 1
        print(f'status    {task["key"]} → in_progress')
    else:
        print(f'status    {task["key"]} was already in_progress')

    if running:
        print(f'timer     already running on {task["key"]}')
        return 0
    try:
        nu.post(f'/v1/project/tasks/{task["id"]}/timer/start', {})
    except nu.ApiError as err:
        # The status moved and the timer did not: said plainly, because the
        # half-done state is exactly what somebody has to know to fix it.
        print(f'nuclock: status moved, but the timer did not start: {err}', file=sys.stderr)
        return 1
    print(f'timer     running on {task["key"]}')
    if waiting:
        print(f'note      started with {len(waiting)} blocker(s) still open')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
