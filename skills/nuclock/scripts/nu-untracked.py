#!/usr/bin/env python3
"""Work that happened with no timer on it, as far as anything can tell.

The honest limit first: nothing can KNOW what somebody was doing. What this
does is compare two records — the commits in a repository and the time entries
in the tracker — and name the days where one exists and the other does not.
It is a prompt to remember, not a measurement.

    nu-untracked.py            # this repository, the last 7 days
    nu-untracked.py --days 30
    nu-untracked.py --repo ../nuclock_back

It writes nothing. Backfilling is `log_time`, with a note saying what the
hours were, and the person deciding the number.
"""

from __future__ import annotations

import argparse
import collections
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _nuclock as nu  # noqa: E402


def commits_by_day(repo: Path, since: date, author: str) -> dict[str, int]:
    """How many commits this author made on each day, out of git's own log.

    The author is matched HERE rather than by `--author`, which git reads as a
    regular expression: an address like `dev+work@example.com` then fails to
    match its own commits, and the answer — "no commits" — looks exactly like
    a week off.
    """
    try:
        out = subprocess.run(  # noqa: S603
            [
                'git', '-C', str(repo), 'log',
                f'--since={since.isoformat()}',
                '--pretty=%ad\t%ae', '--date=short',
            ],
            capture_output=True, text=True, check=True, timeout=20,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return {}
    wanted = author.strip().lower()
    days = [
        line.split('\t', 1)[0]
        for line in out.splitlines()
        if '\t' in line and line.split('\t', 1)[1].strip().lower() == wanted
    ]
    return dict(collections.Counter(days))


def tracked_days(days: int) -> set[str]:
    """The days this person recorded any time on, tracker-side."""
    entries = nu.rows(nu.get(f'/v1/project/time-entries?mine=true&limit={max(days * 8, 50)}'))
    return {
        (entry.get('started_at') or '')[:10]
        for entry in entries
        if entry.get('started_at')
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--days', type=int, default=7)
    parser.add_argument('--repo', default='.')
    parser.add_argument(
        '--author',
        default=None,
        help='git author to count; defaults to this repository’s user.email',
    )
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    author = args.author
    if author is None:
        author = subprocess.run(  # noqa: S603
            ['git', '-C', str(repo), 'config', 'user.email'],
            capture_output=True, text=True, check=False, timeout=10,
        ).stdout.strip()
    if not author:
        print('nuclock: no git author to compare against', file=sys.stderr)
        return 2

    since = date.today() - timedelta(days=args.days)
    commits = commits_by_day(repo, since, author)
    if not commits:
        print(f'no commits by {author} in {repo.name} since {since}')
        return 0

    try:
        tracked = tracked_days(args.days)
    except (nu.NoKeyError, nu.ApiError) as err:
        print(f'nuclock: {err}', file=sys.stderr)
        return 2

    missing = sorted(day for day in commits if day not in tracked)
    if not missing:
        print(f'every day with commits in {repo.name} has time on it')
        return 0

    print(f'days with commits in {repo.name} and no time recorded:')
    for day in missing:
        print(f'  {day}  {commits[day]} commit(s)')
    print('\nBackfill what you can vouch for: log_time(task_id, date, hours, note).')
    print('A note saying what the hours were is what makes them defensible later.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
