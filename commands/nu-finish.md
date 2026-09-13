---
allowed-tools: Bash(python3:*)
argument-hint: NUC-142 [--done] [--anyway]
description: Stop the timer, and close the task only when it is really closed
---

## Finishing $ARGUMENTS

!`python3 "${CLAUDE_PLUGIN_ROOT}/skills/nuclock/scripts/nu-finish.py" $ARGUMENTS`

## Your task

Say what happened in one line.

Without `--done` this only stops the clock, and that is usually right: work
stops for lunch and for the day, and `in_progress` with no timer running is an
honest description of a thing put down.

With `--done` it may refuse because a merge request is still open — `done`
makes the task billable, so that refusal is protecting a number somebody will
be sent. Merge it first. `--anyway` exists for the case where the person can
see the merge request is not this task's, and it is their call, not yours.
