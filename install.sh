#!/usr/bin/env bash
# Install the skill BY HAND, for somebody who would rather not use the plugin.
#
# The ordinary way is two lines in Claude Code and no shell at all:
#
#   /plugin marketplace add CorneiZeR/claude-plugins
#   /plugin install nuclock@corneizer
#
# This script stays for the case where a person wants the checkout itself —
# working on the skill, or pinning it to a branch — and it does the same two
# things the plugin does: link the skill, and offer the hooks.
#
#   ./install.sh              # link the skill, print what to add for hooks
#   ./install.sh --hooks      # …and write the hook entries into settings.json
#
# The skill is LINKED rather than copied: a checkout that updates with `git
# pull` is the whole reason this lives in a repository. The hooks are written
# only when asked, because they change what happens around every tool call in
# every session — that is a decision, not a detail of installation.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
SKILLS="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
SETTINGS="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"

mkdir -p "$SKILLS"
if [ -e "$SKILLS/nuclock" ] && [ ! -L "$SKILLS/nuclock" ]; then
  echo "install: $SKILLS/nuclock exists and is not a link — move it aside first" >&2
  exit 1
fi
ln -sfn "$HERE/skills/nuclock" "$SKILLS/nuclock"
echo "skill:    $SKILLS/nuclock -> $HERE/skills/nuclock"

if [ "${1:-}" != '--hooks' ]; then
  cat <<TEXT

hooks:    not installed. Run with --hooks, or merge this INTO the "hooks"
          object in $SETTINGS — each event is a list, so append rather than
          assign, or you will drop whatever hooks are already there:

  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command",
       "command": "$HERE/hooks/session-start.py"}]}],
    "PreToolUse":  [{"matcher": "Edit|Write|NotebookEdit", "hooks": [{"type": "command",
       "command": "$HERE/hooks/editing-without-a-timer.py"}]}],
    "SessionEnd":  [{"hooks": [{"type": "command",
       "command": "$HERE/hooks/session-end.py"}]}]
  }

They warn and never block, and none of them writes time.
TEXT
  exit 0
fi

python3 - "$SETTINGS" "$HERE" <<'PY'
"""Add the three hooks, keeping whatever is already there.

Hooks are a list per event, so an entry is APPENDED rather than assigned: the
alternative overwrites somebody's status-line hook on the way past, which is
the kind of install nobody forgives. An entry already pointing at this
checkout is left alone, so running the installer twice is not two hooks.
"""
import json
import pathlib
import sys

settings_path, here = pathlib.Path(sys.argv[1]), sys.argv[2]
try:
    settings = json.loads(settings_path.read_text(encoding='utf-8'))
except FileNotFoundError:
    settings = {}
except ValueError:
    print(f'install: {settings_path} is not valid JSON — not touching it', file=sys.stderr)
    raise SystemExit(1) from None

wanted = [
    ('SessionStart', None, f'{here}/hooks/session-start.py'),
    ('PreToolUse', 'Edit|Write|NotebookEdit', f'{here}/hooks/editing-without-a-timer.py'),
    ('SessionEnd', None, f'{here}/hooks/session-end.py'),
]

hooks = settings.setdefault('hooks', {})
added = 0
for event, matcher, command in wanted:
    entries = hooks.setdefault(event, [])
    if any(
        hook.get('command') == command
        for entry in entries
        for hook in entry.get('hooks', [])
    ):
        continue
    entry = {'hooks': [{'type': 'command', 'command': command}]}
    if matcher:
        entry['matcher'] = matcher
    entries.append(entry)
    added += 1

if added:
    settings_path.write_text(json.dumps(settings, indent=2) + '\n', encoding='utf-8')
print(f'hooks:    {added} added, {len(wanted) - added} already there')
PY
