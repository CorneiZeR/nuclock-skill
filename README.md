<h1 align="center">nuclock-skill</h1>

<p align="center"><em>“The tracker holds the plan, and the timer follows the work.”</em></p>

<p align="center">An operating procedure for the <strong>nuclock</strong> tracker, as a skill for coding agents —<br>
plus three hooks that catch the one thing people reliably forget.</p>

---

## What this is

nuclock's MCP server already exposes the API: tasks, timers, invoices, the lot.
What it does not carry is the **procedure** — which tool to reach for, in what
order, and what must never be skipped. That is what `SKILL.md` is.

The procedure is short because most of it is one rule. A tracker survives a
forgotten status; it does not survive a forgotten timer. An hour nobody
recorded is an hour reconstructed from memory a week later, and reconstructed
hours are the ones that get argued about on an invoice.

## What the hooks do

Three, and none of them writes anything to the tracker:

| Hook | When | What it says |
| --- | --- | --- |
| `session-start.py` | a session opens | what is running, what is in flight, what is next |
| `editing-without-a-timer.py` | an edit while no timer runs, once per session | “no timer is running, and this session is changing code” |
| `session-end.py` | the session ends | “a timer is still running on NUC-123” |

**They warn; they never block and never write time.** A hook that started a
timer would be recording time nobody can vouch for. A hook that blocked an
edit would be a tracker holding somebody's editor hostage — and a tracker
people turn off records nothing at all.

**Silence is deliberate where the tracker cannot be reached.** "Your timer is
off" because the network blinked teaches people to ignore the hook, so an
unreachable tracker says nothing. The warning about an idle timer fires once
per session, not once per edit, for the same reason.

## Install

Two lines in Claude Code, and no shell at all:

```
/plugin marketplace add CorneiZeR/claude-plugins
/plugin install nuclock@corneizer
```

That brings the skill and the three hooks together, and `/plugin update` keeps
them current.

**The hooks come with it, and that is worth one sentence before you install.**
They run around every tool call in every session: one reads the queue when a
session opens, one warns once per session on an edit made while no timer runs,
one speaks up at the end if a timer was left running. They only ever print, and
the one that could interrupt an edit deliberately does not — see *What the
hooks do*.

<details>
<summary>By hand, without the plugin</summary>

For working on the skill itself, or pinning it to a branch:

```bash
git clone git@github.com:CorneiZeR/nuclock-skill.git
cd nuclock-skill
./install.sh            # links the skill, prints the hook entries
./install.sh --hooks    # …and writes them into ~/.claude/settings.json
```

The skill is LINKED rather than copied, so `git pull` updates it. The hooks are
written only when asked, and the installer appends to whatever is already in
`settings.json` and does nothing on a second run.

</details>

## Commands

Installed with the plugin, so the scripts need no path and no remembering:

| Command | What it does |
| --- | --- |
| `/nu-queue` | what is running, what is in flight, what is next — blocked rows marked |
| `/nu-start NUC-142` | blockers → `in_progress` → timer, refusing rather than guessing |
| `/nu-finish NUC-142` | stop the clock; `--done` closes it when nothing is still open |
| `/nu-login` | sign the scripts and hooks in: a link and a code to approve in the browser |
| `/nu-logout` | sign them out: revoked at the provider, removed here |

Both writing commands take `--anyway` for the case where the person can see
the reason is stale — and it is written into the commands that an assistant
must not reach for that flag on its own: a retry is not a decision.

## Signing in

The scripts act as the person, with the person's OWN credential — and they
sign in the way a command line does, so nobody pastes a token anywhere:

```
/nu-login                                   # in Claude Code
skills/nuclock/scripts/nu-login.py          # in a terminal
```

It runs the device authorization grant (RFC 8628): it prints a link and a short
code, the person approves on the identity provider's own page — the same
consent page an assistant gets, asking the same two rights, `nuclock:read` and
`nuclock:write` — and the script collects the token. The provider is not
written into the plugin: the API names it in its protected-resource metadata
(`/.well-known/oauth-protected-resource/mcp`), so the same plugin signs in to
any organisation running nuclock. `NUCLOCK_ISSUER` overrides it, and
`NUCLOCK_CLIENT_ID` the client (`nuclock-cli`).

**What is kept, and where.** `$XDG_STATE_HOME/nuclock/token.json`
(`~/.local/state/nuclock/token.json` by default), created `0600` in a `0700`
directory: the access token, when it ends, the refresh token, and the API it
was issued for — a token for one organisation is never offered to another's.
A file rather than the macOS keychain, because the plugin runs on Linux too. A
spent access token is renewed silently, and a 401 renews it once and sends the
call again; a refresh the provider refuses ends the sign-in, and the scripts
say to sign in again rather than offering the dead token on every call.

**Signing out** is `/nu-logout`: the refresh token is revoked at the provider,
which ends that session there, and the file is removed. A provider that cannot
be reached still loses the file, and that is said.

**The order a credential is looked for in** — and nothing here prints one or
passes one as a command-line argument (an argument is visible in `ps` to
everybody on the machine):

1. `NUCLOCK_API_KEY` — CI has no browser, so a service key there wins;
2. the sign-in `nu-login` cached;
3. the nuclock MCP server's `Authorization` header in the Claude Code config,
   for whoever still connects with a key — `$CLAUDE_CONFIG_DIR/.claude.json`
   when that variable is set, and `~/.claude.json`, in the person's own scope
   and in each project's, because `claude mcp add` writes the project one by
   default.

An assistant signed in through the identity provider leaves nothing to borrow:
its token lives inside Claude Code, which is another application's private
store, and reading it would break the day it changed shape. The scripts sign
in for themselves instead.

A credential carries its owner's access, and the scripts say so rather than
retrying: a read-only one fails a write because of its scope, and "permission
denied" is an answer about what that person may see.

**Three exit statuses, because the hooks must tell them apart.** `0` and `1`
are answers; `2` means the tracker could not be ASKED — a blink, and the hooks
stay silent, because "your timer is off" when the network hiccupped teaches
people to ignore the warning. `3` means no credential was found at all, which
is a gap somebody can close: the editing hook says it once per session and the
session's start tells the assistant, so an unreadable queue is not mistaken for
an empty backlog; both point at `/nu-login`. Those two shared `2` once, and the day the assistant moved to
the identity provider the whole plugin went off without a word.

## The scripts

| Script | What it answers |
| --- | --- |
| `skills/nuclock/scripts/nu-queue.py` | what is running, what is in flight, what is next — and which rows are blocked |
| `skills/nuclock/scripts/nu-start.py` | blockers → `in_progress` → timer, as one command |
| `skills/nuclock/scripts/nu-finish.py` | timer off; `--done` closes it when nothing is still open |
| `skills/nuclock/scripts/nu-running.py` | what is being tracked right now (exit 1 when nothing is) |
| `skills/nuclock/scripts/nu-untracked.py` | days with commits and no time recorded |

`nu-start.py` and `nu-finish.py` are the two that WRITE, and they write
because somebody typed them with a task named. The hooks never do: one that
started a timer would be recording time nobody can vouch for.

```
skills/nuclock/scripts/nu-start.py NUC-142           # refuses a blocked task; --anyway overrides
skills/nuclock/scripts/nu-finish.py NUC-142          # stop the clock, leave the status alone
skills/nuclock/scripts/nu-finish.py NUC-142 --done   # …and close it, if no merge request is open
```

`nu-untracked.py` compares two records — git's log and the tracker's entries —
and names the days where one exists and the other does not. It is a prompt to
remember, not a measurement: nothing can know what somebody was doing, and
backfilling is a decision the person makes with `log_time`.

```bash
skills/nuclock/scripts/nu-untracked.py --days 14 --repo ../nuclock_back
```

## Tests

```bash
tests/run.sh          # the hooks, the credential lookup and the sign-in (tests/signin.py)
tests/commands.sh     # nu-start and nu-finish
tests/tools.py        # every tool call the documents show
```

The first is about the ways a hook can misbehave in somebody's editor:
warning when it should be quiet, blocking when it must not, and shouting
because the network blinked.

The second is about what the two writing commands REFUSE — a blocked task, a
timer already running on something else, `--done` while a merge request is
open — and a refusal is only visible as a write that never happened, so the
stub logs every one and the cases count them.

The third is about the prose. The skill teaches calls by name and argument —
and it went on teaching `log_time` with a `date` after the server stopped
taking one, so a model that followed it was refused.
`tests/tool_schemas.json` is a copy of the server's own snapshot
(`nuclock_back/mcp_server/tests/tool_schemas.json`); every `tool(args)` in the
skill, the commands, the hooks and this README must use arguments the tool
has, and all it requires unless it elides with `…`. The copy is then compared
with what the live server publishes, so a server change never carried here
fails this test rather than whoever follows the documents next. Without a key
or a network that comparison says SKIPPED — which is not a pass.

The first two run against a stub, so they need no key and no network. The
third reads the documents offline and asks the live server only for the
schema comparison.

## Everything written into nuclock is in English

Titles, descriptions, comments. The conversation around the work is whatever
language the people are speaking; the record is not.
