---
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/skills/nuclock/scripts/nu-logout.py":*)
description: Sign the scripts out of nuclock — revoked at the provider, removed here
---

## Signing out

!`python3 "${CLAUDE_PLUGIN_ROOT}/skills/nuclock/scripts/nu-logout.py"`

## Your task

Say what happened in one sentence, in the language the person is speaking. If
the provider could not be told, say that the session lives on until the
provider ends it. The MCP tools are a separate sign-in and are unaffected.
