---
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/skills/nuclock/scripts/nu-login.py":*)
description: Sign the scripts and hooks in to nuclock — a code to approve in the browser, no key to paste
---

## The code

!`python3 "${CLAUDE_PLUGIN_ROOT}/skills/nuclock/scripts/nu-login.py" --start`

## Your task

Give the person the link and the code above exactly as printed, in the
language they are speaking, and say they approve it in the browser.

Then run the `Then:` line above with the Bash tool, with a timeout of 600000 ms
— the code lives ten minutes and the command waits for the approval — and say
what it answered: who is signed in, or why not.

If the code above failed, repeat its sentence. "Use a key" means this tracker
offers no sign-in for a command: the scripts then need `NUCLOCK_API_KEY`.
Never ask the person to paste a token into the chat.
