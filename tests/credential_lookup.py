#!/usr/bin/env python3
"""Where `_nuclock.key()` looks, and what it says when it finds nothing.

Three shapes, in scratch homes under `$WORK`: a tracker connected through the
identity provider (an entry with no header, which is what broke the plugin),
a header in the project scope `claude mcp add` writes by default, and the
per-person scope the scripts were originally written against — reached through
`CLAUDE_CONFIG_DIR`, which is how one machine holds several installations.

Prints three words for `tests/run.sh` to compare: why the first failed, and
the header found in each of the other two.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib

spec = importlib.util.spec_from_file_location('nu', 'skills/nuclock/scripts/_nuclock.py')
nu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nu)

WORK = pathlib.Path(os.environ['WORK'])

AT_PROVIDER = {'projects': {'/w': {'mcpServers': {'nuclock': {'url': 'https://x/mcp'}}}}}
PER_PROJECT = {'projects': {'/w': {'mcpServers': {'nuclock': {'headers': {'Authorization': 'nuc_local'}}}}}}
PER_PERSON = {'mcpServers': {'nuclock': {'headers': {'Authorization': 'nuc_top'}}}}


def home(name: str, body: dict) -> str:
    """A scratch home holding one config."""
    directory = WORK / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / '.claude.json').write_text(json.dumps(body), encoding='utf-8')
    return str(directory)


def found() -> str:
    """What `key()` gives back, as one word — a raise included.

    Never raises itself: `run.sh` runs under `set -e`, so a helper that died
    would abort the whole suite instead of failing one check, and the proof
    that a check CAN fail is half of what a check is worth.
    """
    try:
        return nu.key().replace(' ', '-')
    except nu.NoKeyError as err:
        return 'provider' if 'identity provider' in str(err) else f'no-key({err})'
    except Exception as err:  # noqa: BLE001 — a crash is a result here, not an exit
        return f'raised({type(err).__name__})'


def main() -> None:
    os.environ.pop('NUCLOCK_API_KEY', None)
    os.environ.pop('CLAUDE_CONFIG_DIR', None)
    said = []

    os.environ['HOME'] = home('home-oauth', AT_PROVIDER)
    said.append(found())

    os.environ['HOME'] = home('home-local', PER_PROJECT)
    said.append(found())

    os.environ['HOME'] = home('home-oauth', AT_PROVIDER)
    os.environ['CLAUDE_CONFIG_DIR'] = home('home-top', PER_PERSON)
    said.append(found())

    print(' '.join(said))


if __name__ == '__main__':
    main()
