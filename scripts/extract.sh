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

case "${1:-}" in
    --status)
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
            echo "  started $(cat "$JOB_DIR/started_utc" 2>/dev/null || echo '-')"
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
