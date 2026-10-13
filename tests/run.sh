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
# The hooks keep session markers in one of these; a run must not leave them in the real ones.
export XDG_RUNTIME_DIR="$WORK" TMPDIR="$WORK/tmp"
mkdir -m 700 "$TMPDIR"

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

# The holder releases its claim between this hook's `O_EXCL` refusal and its
# look at the claim's age. That used to be a `FileNotFoundError` traceback.
status=0
python3 - "$RUN" > /dev/null 2>&1 <<'PY' || status=$?
import importlib.util, io, sys
spec = importlib.util.spec_from_file_location('hook', 'hooks/editing-without-a-timer.py')
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)
hook.tempfile.gettempdir()  # it probes with `os.open`, so before that is replaced
def refused(path, flags, *rest):
    raise FileExistsError(path)
hook.os.open = refused
sys.stdin = io.StringIO('{"session_id":"gone-%s"}' % sys.argv[1])
raise SystemExit(hook.main())
PY
check 'a claim released mid-check is not a crash' '0' "$status"

echo 'where the markers live'

# $1 — a directory under the scratch one, or `unset` to remove the variable;
# $2 — what `XDG_RUNTIME_DIR` is set to, the directory's full path by default;
# $3 — `stranger` to run the hook as if another user owned the directory.
# Prints the directory the session's marker landed in.
told_in() {
  local session="where-$1-${3:-self}-$RUN" runtime=() as=()
  [ "$1" = unset ] || runtime=("XDG_RUNTIME_DIR=${2:-$WORK/$1}")
  # `os.getuid` is moved one up, so the directory's owner is somebody else.
  [ "${3:-}" = stranger ] && as=(-c 'import os, runpy; uid = os.getuid(); os.getuid = lambda: uid + 1; runpy.run_path("hooks/editing-without-a-timer.py", run_name="__main__")')
  echo '{"session_id":"'"$session"'","tool_name":"Edit"}' |
    env -u XDG_RUNTIME_DIR "${runtime[@]}" python3 "${as[@]:-hooks/editing-without-a-timer.py}" > /dev/null
  for dir in "$WORK/$1" "$TMPDIR"; do
    [ -e "$dir/nuclock-told-$session" ] && echo "$dir" && return
  done
  echo nowhere
}

stub 1 'no timer is running'
mkdir -m 700 "$WORK/private" "$WORK/relative" "$WORK/read-only"
chmod 500 "$WORK/read-only"
mkdir -m 777 "$WORK/shared"
install -m 600 /dev/null "$WORK/file"
check 'a private runtime directory holds them' "$WORK/private" "$(told_in private)"
check 'one other users can write to is not trusted' "$TMPDIR" "$(told_in shared)"
check 'one that does not exist is not used' "$TMPDIR" "$(told_in missing)"
# Root writes through any mode, so there the directory is writable after all.
if [ "$(id -u)" != 0 ]; then
  check 'one this user cannot write to is not used' "$TMPDIR" "$(told_in read-only)"
fi
check 'a file is not a directory' "$TMPDIR" "$(told_in file)"
check 'one another user owns is not used' "$TMPDIR" "$(told_in private '' stranger)"
check 'a relative one is not used, as the spec says' "$TMPDIR" "$(told_in relative "$(python3 -c 'import os, sys; print(os.path.relpath(sys.argv[1]))' "$WORK/relative")")"
check 'without one, the temporary directory' "$TMPDIR" "$(told_in unset)"

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
