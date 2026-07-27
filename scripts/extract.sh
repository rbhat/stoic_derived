#!/usr/bin/env bash
# WP-V §3.2 visual extraction — the single entry point.
#
#   scripts/extract.sh              start it, or tell me it is already running
#   scripts/extract.sh --status     where is it up to
#   scripts/extract.sh --stop       stop it (e.g. the laptop is running hot)
#
# Anything else is forwarded to edu/pipeline/visual_extract.py, so --list,
# --dry-run and --remaining work here too.
#
# Starting is always safe. The job resumes per state, so re-running this after
# a kill, a crash, a power cut or an LM Studio restart redoes only what is
# genuinely missing. There is nothing to clean up first and no flag to
# remember.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

JOB="wpv-32-extract"
JOB_DIR="$REPO/.artifacts/jobs/$JOB"
PID_FILE="$JOB_DIR/pid"
LOG_LINK="$JOB_DIR/latest.log"
PY="$REPO/.venv/bin/python"
EXTRACT_PY="$REPO/edu/pipeline/visual_extract.py"
SUPERVISOR="$REPO/scripts/wpv32_run.sh"

# The recorded pid is the supervisor's. It is only meaningful if that process
# is still alive -- a stale pid file outlives the job it described.
running_pid() {
    [ -f "$PID_FILE" ] || return 1
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null)" || return 1
    [ -n "$pid" ] || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    printf '%s' "$pid"
}

# started_utc is stamped by launch_bg.sh. Report it in Pacific and as an
# elapsed duration, because "2026-07-26T23:03:08Z" answers neither question
# actually being asked: when did I start this, and how long has it been going.
# The elapsed figure is wall time since launch, so it includes the thermal
# pauses -- that is the honest number to compare against the ETA, which also
# includes them.
#
# It must also answer "is it still going", and for a while it did not: this
# printed "running 0h40m" off started_utc alone, so a stopped job reported a
# timer that kept climbing every time it was asked. That is the single most
# dangerous thing this script could get wrong -- --status is what gets checked
# before deciding whether to relaunch, and a job that looks alive is a job
# nobody restarts. The counts underneath were right the whole time, which is
# what made it convincing. Liveness now comes from running_pid(), the same
# check --stop and the launcher use.
#
# When it is dead, the useful number is not "now minus started" but how long it
# actually ran, so the end is taken from the last write to the log. That is the
# supervisor's own heartbeat -- it logs a cooling line every few minutes -- and
# once the process is gone nothing else touches the file.
runtime_line() {
    local started logp
    started="$(cat "$JOB_DIR/started_utc" 2>/dev/null)" || return 0
    [ -n "$started" ] || return 0
    logp="$(readlink "$LOG_LINK" 2>/dev/null || echo "$LOG_LINK")"
    local alive=0 pid
    if pid="$(running_pid)"; then alive=1; else pid=""; fi
    "$PY" - "$started" "$alive" "$logp" "$pid" <<'PYEOF' 2>/dev/null || true
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

started_s, alive_s, logp, pid = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
PT = ZoneInfo("America/Los_Angeles")
started = datetime.strptime(started_s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
now = datetime.now(UTC)


def hm(seconds: float) -> str:
    h, m = divmod(max(0, int(seconds)) // 60, 60)
    return f"{h}h{m:02d}m"


print(f"  started {started.astimezone(PT):%a %d %b %Y %H:%M:%S %Z}")

if alive_s == "1":
    print(f"  running {hm((now - started).total_seconds())}  (pid {pid})")
    sys.exit(0)

# Dead. Prefer the log's last write as the end of the run; fall back to saying
# so rather than quietly reporting wall time as if it were runtime.
end = None
try:
    end = datetime.fromtimestamp(Path(logp).stat().st_mtime, UTC)
except OSError:
    pass
if end is None or end < started:
    print("  STOPPED  (not running; no log activity to date the end of the run)")
else:
    print(f"  STOPPED  ran {hm((end - started).total_seconds())}, "
          f"last activity {end.astimezone(PT):%H:%M:%S %Z} "
          f"({hm((now - end).total_seconds())} ago)")
PYEOF
}

case "${1:-}" in
    --status)
        runtime_line
        exec "$PY" "$EXTRACT_PY" --status
        ;;

    --stop)
        if pid="$(running_pid)"; then
            # Kill the supervisor FIRST. The other order lets it observe the
            # extractor dying and dutifully start a new one.
            kill "$pid" 2>/dev/null
            pkill -f "$SUPERVISOR" 2>/dev/null
            pkill -f "$EXTRACT_PY" 2>/dev/null
            sleep 2
            echo "stopped $JOB (was pid $pid)"
        else
            # Still sweep: the supervisor may have been started outside
            # launch_bg.sh, leaving no pid file to find it by.
            pkill -f "$SUPERVISOR" 2>/dev/null
            pkill -f "$EXTRACT_PY" 2>/dev/null
            echo "$JOB was not running"
        fi
        echo "progress is saved. Resume with: scripts/extract.sh"
        exit 0
        ;;

    "")
        if pid="$(running_pid)"; then
            echo "$JOB is ALREADY RUNNING"
            echo "  pid     $pid"
            echo "  log     $(readlink "$LOG_LINK" 2>/dev/null || echo "$LOG_LINK")"
            runtime_line
            echo
            echo "  tail -f $LOG_LINK"
            echo "  scripts/extract.sh --status     where it is up to"
            echo "  scripts/extract.sh --stop       stop it"
            exit 0
        fi
        echo "$JOB is not running — starting it."
        echo
        exec "$REPO/scripts/launch_bg.sh" "$JOB" -- "$SUPERVISOR"
        ;;

    *)
        exec "$PY" "$EXTRACT_PY" "$@"
        ;;
esac
