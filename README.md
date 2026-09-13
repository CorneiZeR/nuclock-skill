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
| `editing-without-a-timer.py` | the first edit in a session | “no timer is running, and this session is changing code” |
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
session opens, one warns on the first edit if no timer is running, one speaks
up at the end if a timer was left running. They only ever print, and the one
that could interrupt an edit deliberately does not — see *What the hooks do*.

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

Both writing commands take `--anyway` for the case where the person can see
the reason is stale — and it is written into the commands that an assistant
must not reach for that flag on its own: a retry is not a decision.

## The key

The scripts use the person's OWN key, read from `NUCLOCK_API_KEY` or from the
nuclock MCP server's header in `~/.claude.json` — so somebody who set the tools
up once does not set up a second credential. Nothing here writes a key
anywhere, prints one, or passes one as a command-line argument.

A key carries its owner's access, and the scripts say so rather than retrying:
a read-only key fails a write because of its scope, and "permission denied" is
an answer about what that person may see.

## The scripts

| Script | What it answers |
| --- | --- |
| `scripts/nu-queue.py` | what is running, what is in flight, what is next — and which rows are blocked |
| `scripts/nu-start.py` | blockers → `in_progress` → timer, as one command |
| `scripts/nu-finish.py` | timer off; `--done` closes it when nothing is still open |
| `scripts/nu-running.py` | what is being tracked right now (exit 1 when nothing is) |
| `scripts/nu-untracked.py` | days with commits and no time recorded |

`nu-start.py` and `nu-finish.py` are the two that WRITE, and they write
because somebody typed them with a task named. The hooks never do: one that
started a timer would be recording time nobody can vouch for.

```
scripts/nu-start.py NUC-142           # refuses a blocked task; --anyway overrides
scripts/nu-finish.py NUC-142          # stop the clock, leave the status alone
scripts/nu-finish.py NUC-142 --done   # …and close it, if no merge request is open
```

`nu-untracked.py` compares two records — git's log and the tracker's entries —
and names the days where one exists and the other does not. It is a prompt to
remember, not a measurement: nothing can know what somebody was doing, and
backfilling is a decision the person makes with `log_time`.

```bash
scripts/nu-untracked.py --days 14 --repo ../nuclock_back
```

## Tests

```bash
tests/run.sh          # the hooks
tests/commands.sh     # nu-start and nu-finish
```

The first is about the ways a hook can misbehave in somebody's editor:
warning when it should be quiet, blocking when it must not, and shouting
because the network blinked.

The second is about what the two writing commands REFUSE — a blocked task, a
timer already running on something else, `--done` while a merge request is
open — and a refusal is only visible as a write that never happened, so the
stub logs every one and the cases count them.

Both run against a stub, so they need no key and no network.

## Everything written into nuclock is in English

Titles, descriptions, comments. The conversation around the work is whatever
language the people are speaking; the record is not.
