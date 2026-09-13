#!/usr/bin/env bash
# `nu-start` and `nu-finish`, against a tracker that answers on command.
#
# These two are the only scripts that WRITE, so what is worth pinning is what
# they refuse: a blocked task, a timer already running on something else, and
# `--done` while a merge request is still open. A refusal is only visible as a
# write that never happened, which is why the stub logs every one.
set -euo pipefail
cd "$(dirname "$0")/.."

WORK=$(mktemp -d)
PORT=$((20000 + RANDOM % 20000))
trap 'stop_stub; rm -rf "$WORK"' EXIT

export NUCLOCK_API_URL="http://127.0.0.1:$PORT"
export NUCLOCK_API_KEY='nuc_test'

STUB_PID=''
# NOT `kill ${STUB_PID:-0}`: zero means "everything in my process group",
# which on the first call — when there is no stub yet — is this shell.
stop_stub() {
  [ -n "$STUB_PID" ] || return 0
  kill "$STUB_PID" 2>/dev/null || true
  # Waited for, and its "Terminated" swallowed: the shell announces a killed
  # background job on the next prompt, and twelve of those bury the results
  # this file exists to print.
  wait "$STUB_PID" 2>/dev/null || true
  STUB_PID=''
}

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

# Re-point the running stub at a new scenario and forget the writes so far.
scenario() {
  printf '%s' "$1" > "$WORK/scenario.json"
  : > "$WORK/writes.log"
  stop_stub
  python3 tests/stub_api.py "$PORT" "$WORK/scenario.json" &
  STUB_PID=$!
  for _ in $(seq 1 50); do
    if curl -sf "$NUCLOCK_API_URL/v1/project/timer" >/dev/null 2>&1; then return; fi
    sleep 0.1
  done
  echo 'the stub never came up' >&2
  exit 1
}

writes() { wc -l < "$WORK/writes.log" | tr -d ' '; }
says() { case "$1" in *"$2"*) echo yes ;; *) echo '' ;; esac; }

TASK='{"id":"t-1","key":"NUC-1","title":"A task","status":"todo"}'

echo 'nu-start'

scenario "{\"timer\":null,\"tasks\":[$TASK],\"links\":[]}"
out=$(python3 skills/nuclock/scripts/nu-start.py NUC-1)
check 'moves the status and starts the timer' '2' "$(writes)"
check 'says what it did' 'yes' "$(says "$out" 'timer     running')"

scenario "{\"timer\":null,\"tasks\":[$TASK],\"links\":[{\"kind\":\"blocks\",\"direction\":\"incoming\",\"task_key\":\"NUC-9\",\"task_status\":\"todo\",\"task_title\":\"First\"}]}"
out=$(python3 skills/nuclock/scripts/nu-start.py NUC-1 || true)
check 'refuses a blocked task' '0' "$(writes)"
check 'names the blocker' 'yes' "$(says "$out" 'NUC-9')"

out=$(python3 skills/nuclock/scripts/nu-start.py NUC-1 --anyway)
check '--anyway starts it anyway' '2' "$(writes)"
check 'and says the blockers are still open' 'yes' "$(says "$out" 'blocker')"

scenario "{\"timer\":null,\"tasks\":[$TASK],\"links\":[{\"kind\":\"blocks\",\"direction\":\"incoming\",\"task_key\":\"NUC-9\",\"task_status\":\"done\",\"task_title\":\"Finished\"}]}"
python3 skills/nuclock/scripts/nu-start.py NUC-1 >/dev/null
check 'a finished blocker is history, not an obstacle' '2' "$(writes)"

scenario "{\"timer\":{\"task_id\":\"t-2\",\"task_key\":\"NUC-2\",\"task_title\":\"Elsewhere\"},\"tasks\":[$TASK],\"links\":[]}"
out=$(python3 skills/nuclock/scripts/nu-start.py NUC-1 || true)
check 'refuses to replace a running timer' '0' "$(writes)"
check 'and names what is open' 'yes' "$(says "$out" 'NUC-2')"

echo
echo 'nu-finish'

RUNNING='{"task_id":"t-1","task_key":"NUC-1","title":"A task"}'
scenario "{\"timer\":$RUNNING,\"tasks\":[$TASK],\"merge_requests\":[]}"
out=$(python3 skills/nuclock/scripts/nu-finish.py NUC-1)
check 'stops the timer and leaves the status alone' '1' "$(writes)"
check 'says the status was left' 'yes' "$(says "$out" 'left at')"

scenario "{\"timer\":$RUNNING,\"tasks\":[$TASK],\"merge_requests\":[{\"external_id\":\"42\",\"title\":\"Still open\",\"state\":\"opened\"}]}"
out=$(python3 skills/nuclock/scripts/nu-finish.py NUC-1 --done || true)
check 'stops the clock but refuses --done with a merge request open' '1' "$(writes)"
check 'and names it' 'yes' "$(says "$out" '!42')"

scenario "{\"timer\":$RUNNING,\"tasks\":[$TASK],\"merge_requests\":[{\"external_id\":\"42\",\"title\":\"Merged\",\"state\":\"merged\"}]}"
python3 skills/nuclock/scripts/nu-finish.py NUC-1 --done >/dev/null
check 'closes it once nothing is open' '2' "$(writes)"

scenario "{\"timer\":null,\"tasks\":[$TASK],\"merge_requests\":[],\"refuse_writes\":\"an invoice has claimed this task\"}"
out=$(python3 skills/nuclock/scripts/nu-finish.py NUC-1 --done 2>&1 || true)
check 'repeats what the tracker said rather than a bare code' 'yes' "$(says "$out" 'invoice has claimed')"

echo
if [ "$failures" -eq 0 ]; then
  echo 'all good'
else
  echo "$failures failed"
  exit 1
fi
