#!/usr/bin/env python3
"""Stop the clock, and close the task only if it is really closed.

    nu-finish.py NUC-142            # stop the timer, leave the status alone
    nu-finish.py NUC-142 --done     # …and mark it done

The split is the point. Stopping is almost always right — work stops for
lunch, for a meeting, for the day — and `in_progress` with no timer running is
an honest description of a thing put down. Marking something `done` is a
different claim: it makes the task BILLABLE, so it belongs after the merge
request is merged and its pipeline is green, not when the code compiles.

So `--done` is typed on purpose, and this refuses it while the work visibly is
not finished: an open merge request on the task is the one check a script can
make honestly. Everything else — "is it actually reviewed", "did anybody try
it" — a script cannot know, and pretending otherwise would make the refusal
worth ignoring.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _nuclock as nu  # noqa: E402


def open_merge_requests(task_id: str) -> list[dict]:
    """Merge requests attached to the task that nobody has merged or closed."""
    try:
        rows = nu.rows(nu.get(f'/v1/project/tasks/{task_id}/merge-requests'))
    except nu.ApiError:
        # A tracker that cannot answer is not evidence that the work is
        # finished — but it is also not a reason to block somebody's day, so
        # this says nothing and lets the person decide.
        return []
    return [row for row in rows if (row.get('state') or '').lower() in ('opened', 'open')]


def main() -> int:
    parsed = argparse.ArgumentParser(description='Stop the timer, and optionally close the task.')
    parsed.add_argument('key', help='the key people say out loud, e.g. NUC-142')
    parsed.add_argument('--done', action='store_true', help='also mark the task done')
    parsed.add_argument(
        '--anyway',
        action='store_true',
        help='mark it done even with a merge request still open',
    )
    args = parsed.parse_args()

    try:
        task = nu.task_by_key(args.key)
        running = nu.running_timer()
    except (nu.NoKeyError, nu.ApiError) as err:
        print(f'nuclock: {err}', file=sys.stderr)
        return 1

    if running and running.get('task_id') == task['id']:
        try:
            nu.post(f'/v1/project/tasks/{task["id"]}/timer/stop', {})
        except nu.ApiError as err:
            print(f'nuclock: could not stop the timer: {err}', file=sys.stderr)
            return 1
        print(f'timer     stopped on {task["key"]}')
    elif running:
        print(f'timer     left alone — it is running on {running["task_key"]}, not {task["key"]}')
    else:
        print(f'timer     nothing was running on {task["key"]}')

    if not args.done:
        print(f'status    left at {task.get("status")} — say --done when it really is')
        return 0

    waiting = open_merge_requests(task['id'])
    if waiting and not args.anyway:
        print(f'{task["key"]} still has a merge request open:')
        for one in waiting:
            print(f'  !{one.get("external_id") or "?"} {str(one.get("title"))[:60]}')
        print('done makes it billable — merge it first, or say --anyway')
        return 1

    try:
        nu.put(f'/v1/project/tasks/{task["id"]}/status', {'status': 'done'})
    except nu.ApiError as err:
        print(f'nuclock: could not close {task["key"]}: {err}', file=sys.stderr)
        return 1
    print(f'status    {task["key"]} → done')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
