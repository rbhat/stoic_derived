#!/usr/bin/env bash
# WP-V §3.2 VLM extraction — the one script to run, and to re-run.
#
#   scripts/launch_bg.sh wpv-32-extract -- scripts/wpv32_run.sh
#
# Run it again after anything — a kill because the laptop got hot, a power cut,
# LM Studio quitting, a crash — and it picks up exactly where it left off. No
# arguments, ever. There is nothing to remember and nothing to clean up first.
#
# It resumes at *state* granularity, not video or stage: the extractor appends
# and fsyncs every record as it is produced, so at most one state's work is ever
# lost, and only what is genuinely missing is redone.
#
# While it runs it also heals itself, so an unattended overnight stretch does
# not end because LM Studio blinked:
#   - waits (does not fail) when LM Studio is absent or the model is unloaded
#   - retries a crashed video
#   - stops on its own once the corpus is complete
#
# To see where things stand at any time, including while this is running:
#   .venv/bin/python edu/pipeline/visual_extract.py --status
#
# To pause: kill it. It will not restart itself. Re-run this script to continue.
#
# Thermal tuning is via the environment, e.g. a longer rest:
#   STOIC_COOL_FOR=180 scripts/launch_bg.sh wpv-32-extract -- scripts/wpv32_run.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

PY="$REPO/.venv/bin/python"
EXTRACT=("$PY" "$REPO/edu/pipeline/visual_extract.py")
LMSTUDIO_URL="${LMSTUDIO_URL:-http://localhost:1234/v1}"
MODEL="${STOIC_VLM_MODEL:-qwen3-vl-30b-a3b-instruct-mlx}"

WAIT_SERVER_SLEEP=60      # between polls while LM Studio is absent
RETRY_SLEEP=60            # between extractor attempts
MAX_NO_PROGRESS=10        # consecutive attempts that extract nothing -> stop

log() { printf '[%s] supervisor: %s\n' "$(date '+%H:%M:%S')" "$*"; }

remaining() { "${EXTRACT[@]}" --remaining 2>/dev/null || echo "-1"; }

wait_for_server() {
    # Blocks until LM Studio lists the model. After a power cut the machine can
    # be up long before LM Studio is, and failing in that window would waste the
    # restart -- so this waits rather than exits.
    local announced=0
    while true; do
        if curl -sf --max-time 10 "$LMSTUDIO_URL/models" 2>/dev/null | grep -q "$MODEL"; then
            [ "$announced" -eq 1 ] && log "LM Studio is back with $MODEL"
            return 0
        fi
        if [ "$announced" -eq 0 ]; then
            log "waiting for LM Studio at $LMSTUDIO_URL with $MODEL loaded..."
            announced=1
        fi
        sleep "$WAIT_SERVER_SLEEP"
    done
}

no_progress=0
attempt=0

while true; do
    left="$(remaining)"
    if [ "$left" = "0" ]; then
        log "extraction complete -- nothing remaining. Exiting."
        exit 0
    fi
    if [ "$left" = "-1" ]; then
        log "could not read remaining count; is $PY present? retrying in ${RETRY_SLEEP}s"
        sleep "$RETRY_SLEEP"
        continue
    fi

    wait_for_server

    attempt=$((attempt + 1))
    log "attempt $attempt, $left states remaining"
    "${EXTRACT[@]}"
    rc=$?

    after="$(remaining)"
    if [ "$after" = "0" ]; then
        log "extraction complete. Exiting."
        exit 0
    fi

    # "Progress" is measured in states actually extracted, never in exit codes:
    # a run can exit non-zero having done thousands of states, and a run can
    # exit zero having done none.
    if [ "$after" -lt "$left" ] 2>/dev/null; then
        no_progress=0
        log "progress: $left -> $after remaining (exit $rc)"
    else
        no_progress=$((no_progress + 1))
        log "NO PROGRESS ($after remaining, exit $rc) -- strike $no_progress/$MAX_NO_PROGRESS"
    fi

    if [ "$no_progress" -ge "$MAX_NO_PROGRESS" ]; then
        # Something is wrong that restarting cannot fix. Spinning forever would
        # hide it; stopping leaves the resume point intact for a human.
        log "giving up after $MAX_NO_PROGRESS attempts with no progress. $after states remain."
        log "run: ${EXTRACT[*]} --status"
        exit 1
    fi

    sleep "$RETRY_SLEEP"
done
