#!/usr/bin/env bash
# Health check / watcher for detached stoic_training phases (train,
# evaluate, export). See README "Watcher discipline".
#
#   health.sh                  one-shot status of all phases
#   health.sh <phase>          one-shot status of one phase
#   health.sh --wait <phase>   block until the phase exits, crashes, or
#                              stalls. exit 0=clean exit, 1=crash, 2=stall
#
# Phase liveness uses a bracketed pattern ("[s]toic_training.<phase>") so
# the watcher never matches its own shell. Stall = process alive but its
# newest bootstrap log untouched for STALE_MIN minutes.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
LOGS="$REPO/.artifacts/training/logs"
RUNS="$REPO/.artifacts/training/runs"
STALE_MIN="${STALE_MIN:-20}"
POLL_S="${POLL_S:-300}"

alive() { pgrep -f "[s]toic_training.$1" >/dev/null 2>&1; }
newest_log() { ls -t "$LOGS/$1"-*.log 2>/dev/null | head -1; }
# Stall detection must key on *activity*, not just the bootstrap log: a
# bootstrap log can be off-convention (e.g. baseline-*.log) or long quiet
# while the run dir's <phase>.log / progress.json are still ticking.
newest_activity() {
    ls -t "$LOGS/$1"-*.log "$RUNS"/*/"$1".log "$RUNS"/*/progress.json 2>/dev/null | head -1
}
log_age_min() { echo $(( ( $(date +%s) - $(stat -c %Y "$1") ) / 60 )); }
crashed() { [ -n "$1" ] && tr '\r' '\n' <"$1" | grep -q "Traceback (most recent call last)"; }

# Prints one status line; returns 0=running/done, 1=crashed, 2=stalled.
check_phase() {
    local phase=$1 log age
    log=$(newest_activity "$phase")
    if alive "$phase"; then
        if [ -n "$log" ]; then
            age=$(log_age_min "$log")
            if [ "$age" -ge "$STALE_MIN" ]; then
                echo "$phase: STALLED — process alive but log quiet ${age}m (>$STALE_MIN): $log"
                return 2
            fi
            echo "$phase: RUNNING — log active ${age}m ago: $log"
        else
            echo "$phase: RUNNING — no bootstrap log found under $LOGS"
        fi
        return 0
    fi
    # Crash scan reads the bootstrap log: tracebacks land on the detached
    # process's stdout/stderr, never in progress.json.
    log=$(newest_log "$phase")
    if crashed "$log"; then
        echo "$phase: CRASHED — traceback in $log"
        return 1
    fi
    if [ -n "$log" ]; then
        echo "$phase: not running — exited clean (no traceback): $log"
    else
        echo "$phase: not run"
    fi
    return 0
}

snapshot() {
    local run
    run=$(ls -td "$RUNS"/*/ 2>/dev/null | head -1)
    [ -n "$run" ] && [ -f "$run/progress.json" ] &&
        echo "newest run: $run" && cat "$run/progress.json"
}

if [ "${1:-}" = "--wait" ]; then
    phase="${2:?usage: health.sh --wait <phase>}"
    while alive "$phase"; do
        log=$(newest_activity "$phase")
        if [ -n "$log" ] && [ "$(log_age_min "$log")" -ge "$STALE_MIN" ]; then
            check_phase "$phase"
            exit 2
        fi
        sleep "$POLL_S"
    done
    check_phase "$phase"
    rc=$?
    snapshot
    exit "$rc"
fi

if [ -n "${1:-}" ]; then
    check_phase "$1"
    exit $?
fi

rc=0
for phase in train evaluate export; do
    check_phase "$phase" || rc=$?
done
snapshot
exit "$rc"
