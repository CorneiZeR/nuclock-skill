#!/usr/bin/env bash
# The hooks, exercised against a stubbed tracker.
#
# What is worth testing here is not the happy path — it is the three ways a
# hook can misbehave in somebody's editor: warning when it should be quiet,
# blocking when it must not, and shouting because the network blinked.
#
# The stub is a second copy of `nu-running.py` in a scratch directory, and the
# hooks are pointed at it with NUCLOCK_RUNNING. An earlier version overwrote
# the real script in place; it left a broken stub behind when the run failed,
# which is exactly the kind of test that costs more than it catches.
set -euo pipefail
cd "$(dirname "$0")/.."

WORK=$(mktemp -d)
RUN=${WORK##*/}  # from the random scratch directory: a PID is reused, this is not
trap 'rm -rf "$WORK"' EXIT

failures=0
check() {
  local what=$1 expected=$2 actual=$3
  if [ "$expected" = "$actual" ]; then
    printf '  ok    %s\n' "$what"
  else
    printf '  FAIL  %s\n        expected: %s\n        actual:   %s\n' "$what" "$expected" "$actual"
    failures=$((failures + 1))
  fi
}

# $1 — exit code, $2 — the line it prints.
stub() {
  {
    echo '#!/usr/bin/env python3'
    echo 'import sys'
    printf 'print(%s)\n' "$(python3 -c 'import sys, json; print(json.dumps(sys.argv[1]))' "$2")"
    echo "raise SystemExit($1)"
  } > "$WORK/nu-running.py"
  export NUCLOCK_RUNNING="$WORK/nu-running.py"
}

says() { echo "$1" | grep -q "$2" && echo yes || echo no; }

echo 'editing without a timer'

stub 1 'no timer is running'
out=$(echo '{"session_id":"a-'"$RUN"'","tool_name":"Edit"}' | python3 hooks/editing-without-a-timer.py)
check 'warns when nothing is running' 'yes' "$(says "$out" 'no timer is running')"
check 'and never blocks the tool' 'no' "$(says "$out" 'permissionDecision')"

out=$(echo '{"session_id":"a-'"$RUN"'","tool_name":"Edit"}' | python3 hooks/editing-without-a-timer.py)
check 'says it once per session, not on every edit' '' "$out"

stub 0 'NUC-1 — something (since now)'
out=$(echo '{"session_id":"b-'"$RUN"'","tool_name":"Edit"}' | python3 hooks/editing-without-a-timer.py)
check 'quiet while a timer runs' '' "$out"

stub 2 'nuclock: could not reach the tracker'
out=$(echo '{"session_id":"c-'"$RUN"'","tool_name":"Edit"}' | python3 hooks/editing-without-a-timer.py)
check 'quiet when the tracker cannot be asked' '' "$out"

# Two hooks at once, which is what Claude Code does for tool calls that run in
# parallel: both used to ask the tracker and both used to warn.
stub 1 'no timer is running'
first=$(echo '{"session_id":"par-'"$RUN"'","tool_name":"Edit"}' | python3 hooks/editing-without-a-timer.py) &
second=$(echo '{"session_id":"par-'"$RUN"'","tool_name":"Edit"}' | python3 hooks/editing-without-a-timer.py) &
wait
both=$(
  { echo '{"session_id":"par2-'"$RUN"'","tool_name":"Edit"}' | python3 hooks/editing-without-a-timer.py &
    echo '{"session_id":"par2-'"$RUN"'","tool_name":"Edit"}' | python3 hooks/editing-without-a-timer.py &
    wait; } | grep -c systemMessage || true
)
check 'two hooks at once warn once between them' '1' "$both"

echo 'session end'

stub 0 'NUC-1 — something (since now)'
out=$(echo '{"session_id":"d"}' | python3 hooks/session-end.py)
check 'names a timer left running' 'yes' "$(says "$out" 'still running')"

stub 1 'no timer is running'
out=$(echo '{"session_id":"e"}' | python3 hooks/session-end.py)
check 'quiet when nothing is running' '' "$out"

stub 2 'unreachable'
out=$(echo '{"session_id":"f"}' | python3 hooks/session-end.py)
check 'quiet when the tracker cannot be asked' '' "$out"

echo
if [ "$failures" -eq 0 ]; then
  echo 'all good'
else
  echo "$failures failed"
  exit 1
fi
