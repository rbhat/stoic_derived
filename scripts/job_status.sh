#!/usr/bin/env bash
# What is pid N doing, and is it healthy? Written for the hand-off case: a
# session that did not launch the job is given nothing but a pid.
#
#   scripts/job_status.sh <pid>          resolve the pid to a job and report
#   scripts/job_status.sh <job-name>     same, by name
#   scripts/job_status.sh <pid> --tail 80
#
# Exit codes are the watcher contract, matching training/win_cuda/scripts/health.sh:
#   0 running or finished clean · 1 crashed or exited non-zero · 2 stalled
#
# STALLED = process alive but nothing it writes has been touched for
# STALE_MIN minutes. That distinction matters more than liveness: a wedged
# CUDA job stays "alive" indefinitely.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JOBS="$REPO/.artifacts/jobs"
STALE_MIN="${STALE_MIN:-25}"
TAIL_N=40

ARG="${1:-}"; [ -n "$ARG" ] || { echo "usage: $0 <pid|job-name> [--tail N]" >&2; exit 1; }
[ "${2:-}" = "--tail" ] && TAIL_N="${3:-40}"

# --- resolve the argument to a job directory -------------------------------
DIR=""
if [ -d "$JOBS/$ARG" ]; then
    DIR="$JOBS/$ARG"
else
    for d in "$JOBS"/*/; do
        [ -f "$d/pid" ] && [ "$(cat "$d/pid")" = "$ARG" ] && DIR="${d%/}" && break
    done
fi
if [ -z "$DIR" ]; then
    echo "no job under $JOBS matches '$ARG'"
    if kill -0 "$ARG" 2>/dev/null; then
        echo "pid $ARG IS alive but was not launched by scripts/launch_bg.sh:"
        ps -o pid,etime,command -p "$ARG" 2>/dev/null || ps -p "$ARG"
        exit 0
    fi
    echo "pid $ARG is not alive either."
    exit 1
fi

NAME="$(basename "$DIR")"
PID="$(cat "$DIR/pid" 2>/dev/null || echo '')"
LOG="$DIR/latest.log"
mtime() { [ -e "$1" ] && { stat -c %Y "$1" 2>/dev/null || stat -f %m "$1"; }; }

echo "job      $NAME"
echo "pid      $PID"
echo "command  $(cat "$DIR/cmd" 2>/dev/null)"
echo "started  $(cat "$DIR/started_utc" 2>/dev/null)  (UTC)"
echo "log      $(readlink "$LOG" 2>/dev/null || echo "$LOG")"

# Freshest evidence of work, not just the bootstrap log: a stage can be quiet
# on stdout for a long time while its own state files tick.
NEWEST="$LOG"; NEWEST_T=$(mtime "$LOG" 2>/dev/null || echo 0)
while IFS= read -r f; do
    t=$(mtime "$f" 2>/dev/null || echo 0)
    [ "$t" -gt "${NEWEST_T:-0}" ] && { NEWEST="$f"; NEWEST_T="$t"; }
done < <(find "$REPO/.artifacts" \
    \( -name 'progress.json' -o -name 'state.json' -o -name 'manifest.json' -o -name '*.jsonl' \) \
    -newermt '-2 days' 2>/dev/null | head -400)

AGE_MIN=$(( ( $(date +%s) - ${NEWEST_T:-0} ) / 60 ))
echo "newest   $NEWEST  (${AGE_MIN}m ago)"

RC=0
if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    ps -o pid,etime,%cpu,rss,command -p "$PID" 2>/dev/null | tail -n +1
    if [ "$AGE_MIN" -ge "$STALE_MIN" ]; then
        echo "STATE    STALLED — alive but nothing written for ${AGE_MIN}m (>= ${STALE_MIN}m)"
        RC=2
    else
        echo "STATE    RUNNING"
    fi
else
    if grep -q "Traceback (most recent call last)" "$LOG" 2>/dev/null; then
        echo "STATE    CRASHED — traceback in the log"
        RC=1
    else
        echo "STATE    EXITED"
    fi
fi

command -v nvidia-smi >/dev/null 2>&1 && {
    echo; echo "--- GPU ---"
    nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu \
        --format=csv,noheader 2>/dev/null
}

echo; echo "--- last $TAIL_N log lines ---"
tail -n "$TAIL_N" "$LOG" 2>/dev/null || echo "(no log yet)"
exit $RC
