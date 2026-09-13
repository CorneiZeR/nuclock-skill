---
allowed-tools: Bash(python3:*)
argument-hint: NUC-142 [--anyway]
description: Start a task properly — check blockers, move the status, start the timer
---

## Starting $ARGUMENTS

!`python3 "${CLAUDE_PLUGIN_ROOT}/skills/nuclock/scripts/nu-start.py" $ARGUMENTS`

## Your task

Say what happened, briefly, in the language the person is speaking.

If it refused, the reason is in the output and it is worth repeating rather
than working around:

* **blocked** — the blockers are named. Finish one of those instead, or say
  `--anyway` if the link is stale.
* **a timer already running** — one runs per person. Finish what it belongs
  to (`/nu-finish`) or stop it deliberately; do not replace it quietly.

Never re-run it with `--anyway` on your own: that flag is the person's
decision, not a retry.
