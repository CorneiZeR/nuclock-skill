---
allowed-tools: Bash(python3:*)
description: What is running, what is in flight, what is next — and what is blocked
---

## The queue

!`python3 "${CLAUDE_PLUGIN_ROOT}/skills/nuclock/scripts/nu-queue.py"`

## Your task

Read it back to the person in one short paragraph, in the language they are
speaking. Say what is running (or that nothing is), what is in flight, and
what the next startable task is — a row marked `!` is BLOCKED and is not the
next thing to pick up, whatever its position.

If nothing is running and something is in flight, say so plainly: that is an
hour being lost while somebody works. Do not start anything; this command
reports.
