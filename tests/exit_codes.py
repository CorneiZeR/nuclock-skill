#!/usr/bin/env python3
"""The exit status for "no credential", as each file that holds it spells it.

A hook runs a script as a subprocess and cannot import it, so the number is
written in three places. `tests/run.sh` compares what this prints against
`3 3 3`; a file that drifts shows up as its own number or as `missing`.
"""

from __future__ import annotations

import pathlib
import re

FILES = (
    'skills/nuclock/scripts/_nuclock.py',
    'hooks/editing-without-a-timer.py',
    'hooks/session-start.py',
)


def spelled(path: str) -> str:
    found = re.search(r'^NO_CREDENTIAL = (\d+)$', pathlib.Path(path).read_text(encoding='utf-8'), re.M)
    return found.group(1) if found else 'missing'


if __name__ == '__main__':
    print(' '.join(spelled(path) for path in FILES))
