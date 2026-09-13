---
name: nuclock
description: Working in the nuclock tracker — planning a backlog into a queue, reading what is next and what is blocked, taking a task from start to done, and above all keeping the timer honest (start it when work starts, stop it when it stops, backfill what ran untracked). Use whenever work is about to be done on a tracked project, a task needs creating or re-statusing, something is waiting on something else, hours look wrong or missing, or a session is ending with work behind it.
---

# nuclock

The tracker this team bills from. The MCP server already exposes the API; what
follows is the **operating procedure** — which tool to reach for, in what
order, and what must never be skipped.

The rule in one line: **the tracker holds the plan, and the timer follows the
work.**

Everything written INTO nuclock is in English — titles, descriptions,
comments. The conversation around it is whatever language the people are
speaking.

## Why the timer is the whole point

The tracker survives a forgotten status. It does not survive a forgotten
timer: an hour nobody recorded is an hour reconstructed from memory a week
later, and reconstructed hours are the ones that get argued about on an
invoice. Everything below exists to make the recording happen at the moment
the work does.

**The skill never writes time on its own.** A timer somebody did not start is
time nobody can vouch for. The hooks warn, offer, and stop there — the person
decides.

## The four moments

| When | Do this |
| --- | --- |
| A plan is agreed | Create the task(s), in queue order. Never keep a plan only in a chat. |
| Starting on one | `set_task_status` → `in_progress`, then `start_timer` |
| It is merged and verified | `set_task_status` → `done`, then `stop_timer` |
| Priorities change | `move_task` — the tracker is the queue, so reordering happens there |

## Reading the queue

`list_tasks(mine=true, status='todo', sort='rank')` is "what is next", in the
order somebody arranged rather than in the order things were created. Two more
that answer real questions:

* `list_tasks(mine=true, status='in_progress')` — what is in flight. More than
  two rows here is usually a lie: work was put down and the status never moved.
* `my_running_timer()` — what is being tracked RIGHT NOW, across every project.
  Ask it before starting anything; only one timer may run per person, and the
  refusal is the tracker telling you something is already open.

`scripts/nu-queue.py` prints all three in one go, which is what a session
starts with.

## Is it ready to be started?

A queue ordered by rank answers "what is next" and not "what can I start" —
those differ whenever one task waits for another. The tracker knows: a
`blocks` link is stored once and read from both ends, so the task that WAITS
sees it as incoming.

* `list_task_links(task_id)` — what this task has to do with others.
* `scripts/nu-queue.py` marks a blocked row with `!` and names the blockers
  under it, so the answer arrives without asking per task.
* `scripts/nu-start.py NUC-142` refuses to start a blocked one, and takes
  `--anyway` for the case where the link is stale. The choice then lives in
  the command rather than in a shrug.

A blocker that is `done` or `cancelled` is history rather than an obstacle and
is left out of all three. Nothing else is treated as blocking: `relates` is
"these are about the same thing" and carries no promise, which is why the
tracker has exactly two kinds of link.

## Breaking work into a queue

One task per merge request is the rule for SIZE, and it decides most splits on
its own. What it does not decide is ORDER, and that is where a backlog is
either useful or a list nobody reads.

* **Sequence by what the next task needs.** If B cannot be written until A
  lands, that is a `blocks` link and A goes first — not a sentence in B's
  description that somebody has to notice. The link is what `nu-queue` reads.
* **A research task says what the deliverable IS.** "Decide whether X" needs
  the options, the trade-offs and a recommendation written down, or it closes
  with nothing anybody can act on.
* **Split by what a person can finish, not by layer.** `[BE]` and `[FE]` are
  two tasks when they land separately and one task when they are one change —
  the branch name is the test: same branch, same task.
* **Put the reason in the description, not the recipe.** What was reported,
  why it matters, what to check before calling it done. A recipe rots the
  first time the code moves; a reason survives.
* `move_task` takes the tasks that end up ABOVE and BELOW it, not a position:
  the queue is a shape, not a set of numbers to keep in step.

## Creating a task

```
create_task(performer_id=…, title=…, description=…, status='todo')
```

* **A title says what changes for a person**, not which file moves: "Tasks stay
  in the order somebody put them in", not "add rank column". Prefix the surface
  it touches — `[BE]`, `[FE]`, `[DO]`, or `[BE][FE]` for work that spans both.
* **The description carries the reason**, not the recipe: what was reported,
  why it matters, what to check before calling it done. It is what the next
  reader has instead of you.
* **A task belongs to a PERFORMER, not to a user.** A person on two projects is
  two performers; `list_performers(project_id=…)` is where the id comes from.
* One task per merge request. Work spanning two repositories is ONE task — it
  is one piece of work, and the branch name is the same on both sides.

## Working a task

Two commands cover the whole cycle, and they exist so the ORDER is not
somebody's memory:

```
scripts/nu-start.py NUC-142      # blockers → in_progress → timer
scripts/nu-finish.py NUC-142     # timer off, status left alone
scripts/nu-finish.py NUC-142 --done   # …and closed, if nothing is open
```

`nu-start` refuses a blocked task and refuses to replace a timer that is
already running — which one it should be is a decision, and it prints what is
open instead of guessing. `nu-finish` stops the clock and leaves the status
alone unless `--done` is typed, because stopping is ordinary and closing is a
claim: `done` makes a task billable. With a merge request still open it
refuses `--done` and says which one.

The steps by hand, when something needs doing differently:

Move the status when the work STARTS. A board that only changes at the end
answers "what is done" and never "what is happening", which is the question
people actually open it with.

Then start the timer. Then write code.

**Write down what you FOUND, not only what you fixed.** A comment on the task
is where a finding belongs — a defect noticed in passing, a decision taken, a
thing that turned out to be untrue. A chat scrolls away; the task is still
there in March.

If the work is interrupted: stop the timer and leave the status alone.
`in_progress` with no timer is an honest description of a thing put down.

## Finishing

`done` and `stop_timer` belong at the END of the whole change — after the
merge request is merged and its pipeline is green, not when the code compiles.
`done` makes a task billable, so calling it done early bills work nobody has
accepted yet.

**A task with halves is not finished by one merge.** Two crafts on it, or
somebody helping, means a person closes it rather than a branch — the tracker
already refuses to close those automatically, and the reason is the same here.

## The timer, and backfilling what it missed

The failure is not dramatic. Work happens, the timer does not, and two hours
later somebody writes "about two hours" into a form. What to do instead:

* **`my_running_timer()` at the start of a session**, and at the start of any
  stretch of work. It costs one call and answers the only question that
  matters.
* **When it was missed, backfill deliberately**: `log_time(task_id, date,
  hours, note)` with a note saying what the hours were — "review fixes, merge,
  deploy" — rather than a bare number. A note is what makes an hour
  defensible three weeks later.
* **Correct rather than guess.** `update_time_entry` exists for the case where
  the timer ran on the wrong task, or ran through lunch. A corrected entry with
  a note beats an invented one.
* **Hours are read from the entries, never from a task's own field.** A task
  shows `total_seconds`; untracked work is added by hand, and that is the only
  way it gets there.

## What the hooks do

Installed from `hooks/` (see the README), they catch what a person forgets.
None of them writes anything to the tracker:

| Hook | When | What it says |
| --- | --- | --- |
| `session-start` | a session opens | what is in flight and whether a timer is running |
| `editing-without-a-timer` | first edit in a repository | "you are changing code with no timer running" — once per session, never blocks |
| `session-end` | the session ends | "a timer is still running on NUC-123" |

They are warnings on purpose. A hook that started a timer would be writing time
nobody can vouch for; a hook that blocked an edit would be a tracker holding
somebody's editor hostage.

## When the API refuses

The key is the person's own, and it carries their access:

* **403 on a write** with a read-only key is the key's scope, not the user's
  permissions. Say so and stop — retrying cannot change it.
* **"Permission denied"** is an answer about what that person may see. An
  administrator sees everything; a manager or executor the projects they are
  on; a client the projects they own.
* **A second timer is refused while one runs.** That is the intended answer,
  not an obstacle: finish or park what was already open.
* **An invoice freezes what it billed.** No new time on a claimed task — the
  refusal is the invoice protecting a number somebody has already been sent.

## The useful side effect

Using the tracker on the work of building it is how its own defects surface:
the blinking timer pill, the invoice filter that filtered nothing, the task
finished by a merge request with no completion moment on it. Notice what
annoys you while tracking, and write it down as a task — that is the shortest
path from a wart to a fix.
