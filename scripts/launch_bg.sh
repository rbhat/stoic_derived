#!/usr/bin/env bash
# Detached launcher for the long jobs in this repo (WP-V §3.2 on the Mac,
# the retrain chain on WSL). Survives the terminal closing, keeps the machine
# awake for the duration, and leaves one directory an agent can be pointed at
# later with nothing but the pid.
#
#   scripts/launch_bg.sh                      the default job: report it if it
#                                             is already running, else start it
#   scripts/launch_bg.sh --status             where the default job is up to
#   scripts/launch_bg.sh <job-name> -- <command...>
#   scripts/launch_bg.sh --list
#
# Bare and --status are conveniences for the one long job this machine runs
# (WP-V §3.2). They forward to scripts/extract.sh, which owns that job's
# definition -- so there is one place where "the default job" is decided, not
# two that can drift. Everything else still takes an explicit <job-name>.
#
# On exit it prints the pid. That pid is the only thing you need to hand back:
#   scripts/job_status.sh <pid>
#
# Keeping the machine awake differs by platform and both are handled here,
# because a 17 h job that dies when the lid closes is the failure this script
# exists to prevent:
#   macOS  caffeinate -dimsu -w <pid>  (sleeps when the job does)
#   WSL    a Windows-side SetThreadExecutionState keeper, no admin needed --
#          systemd-inhibit only holds the Linux side, which is not what puts
#          the box to sleep.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JOBS="$REPO/.artifacts/jobs"

# Two plain expressions, not 's/^# \?//': BSD sed has no \? in a basic regex,
# so on macOS that pattern silently matched nothing and printed the comment
# markers verbatim.
usage() { sed -n '2,27p' "$0" | sed -e 's/^#//' -e 's/^ //'; exit "${1:-1}"; }

# The default job. extract.sh is the owner: bare, it reports a live job's pid
# and log or starts one, and --status reports progress. Forwarding rather than
# reimplementing keeps the already-running check in one place.
#
# No recursion risk: extract.sh comes back here with an explicit
# "<job-name> -- <command>", which never re-enters this branch.
DEFAULT_ENTRY="$REPO/scripts/extract.sh"

if [ $# -eq 0 ] || [ "${1:-}" = "--status" ]; then
    exec "$DEFAULT_ENTRY" "$@"
fi

if [ "${1:-}" = "--list" ]; then
    printf '%-28s %-8s %-9s %s\n' JOB PID STATE STARTED
    for d in "$JOBS"/*/; do
        [ -d "$d" ] || continue
        pid=$(cat "$d/pid" 2>/dev/null || echo -)
        state=$(kill -0 "$pid" 2>/dev/null && echo running || echo exited)
        printf '%-28s %-8s %-9s %s\n' "$(basename "$d")" "$pid" "$state" \
            "$(cat "$d/started_utc" 2>/dev/null || echo -)"
    done
    exit 0
fi

[ $# -ge 3 ] || usage 1
NAME="$1"; shift
[ "$1" = "--" ] || usage 1
shift

case "$NAME" in
    *[!A-Za-z0-9._-]*) echo "job name must be [A-Za-z0-9._-]: $NAME" >&2; exit 1 ;;
esac

DIR="$JOBS/$NAME"
if [ -f "$DIR/pid" ] && kill -0 "$(cat "$DIR/pid")" 2>/dev/null; then
    # Re-launching over a live job is how two 8B models end up on one GPU.
    echo "REFUSING: job '$NAME' is already running as pid $(cat "$DIR/pid")." >&2
    echo "  scripts/job_status.sh $(cat "$DIR/pid")" >&2
    exit 3
fi
mkdir -p "$DIR"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$DIR/$STAMP.log"
printf '%s\n' "$*" > "$DIR/cmd"
date -u +%Y-%m-%dT%H:%M:%SZ > "$DIR/started_utc"
ln -sfn "$LOG" "$DIR/latest.log"

# setsid is util-linux: present on WSL, absent on macOS. nohup alone already
# detaches from the terminal's SIGHUP, so it is the correct fallback rather
# than a degraded one -- setsid only additionally makes the job a session
# leader, which matters for process-group signalling, not for surviving a
# closed lid.
if command -v setsid >/dev/null 2>&1; then DETACH=(setsid nohup); else DETACH=(nohup); fi

# The job runs from the repo root so every relative .artifacts/ path in the
# command resolves the way the rest of the repo expects.
cd "$REPO"
"${DETACH[@]}" "$@" >>"$LOG" 2>&1 < /dev/null &
PID=$!
disown "$PID" 2>/dev/null || true
echo "$PID" > "$DIR/pid"

# --- keep the machine awake for exactly as long as the job lives -----------
KEEPER=""
if command -v caffeinate >/dev/null 2>&1; then
    "${DETACH[@]}" caffeinate -dimsu -w "$PID" >/dev/null 2>&1 < /dev/null &
    KEEPER=$!
elif command -v powershell.exe >/dev/null 2>&1; then
    # ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED = 0x80000003.
    # Held only while this powershell lives, so the reaper below releases it.
    "${DETACH[@]}" powershell.exe -NoProfile -Command '
        $sig = "[DllImport(\"kernel32.dll\")] public static extern uint SetThreadExecutionState(uint e);";
        $k = Add-Type -MemberDefinition $sig -Name Keep -Namespace Win32 -PassThru;
        $k::SetThreadExecutionState(0x80000003) | Out-Null;
        while ($true) { Start-Sleep -Seconds 60 }' >/dev/null 2>&1 < /dev/null &
    KEEPER=$!
    # reaper: release the wake-lock the moment the real job exits
    "${DETACH[@]}" bash -c "while kill -0 $PID 2>/dev/null; do sleep 30; done; kill $KEEPER 2>/dev/null" \
        >/dev/null 2>&1 < /dev/null &
else
    echo "note: no caffeinate or powershell.exe found — machine sleep is NOT inhibited" | tee -a "$LOG"
fi
# `&&` alone would trip set -e when there is no keeper, killing the script
# right before it prints the pid the user needs.
[ -n "$KEEPER" ] && echo "$KEEPER" > "$DIR/keeper_pid" || true

cat <<EOF

  job     $NAME
  pid     $PID
  log     $LOG
  status  scripts/job_status.sh $PID

EOF
