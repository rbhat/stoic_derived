#!/usr/bin/env python3
"""
WP-V §3.2 — VLM extraction pass over the harvested visual states.

visual_harvest.py produced 10,120 "distinct visual states" (one full-res JPEG
each) across the 16 education videos, purely with ffmpeg + numpy. This file is
the model-driven pass that reads each of those JPEGs with the local LM Studio
VLM and produces an archival, citable, per-frame record: OCR transcript, frame
classification, and any chart levels drawn on screen. Nothing here re-derives
what states.jsonl / keyframes_v2 already computed -- this stage only adds a
model's reading of pixels that already exist.

Stages (per video, each idempotent and independently resumable)
  extract     visual_records.jsonl   one VLM call per state -> OCR + chart read
  crosscheck  chart_checks.jsonl     deterministic: drawn levels vs daily bars
  report      extract_report.json    deterministic: counts, no verdicts

Usage
  .venv/bin/python edu/pipeline/visual_extract.py --list
  .venv/bin/python edu/pipeline/visual_extract.py --dry-run
  .venv/bin/python edu/pipeline/visual_extract.py --only concept_simple_stoic_setups_sss
  .venv/bin/python edu/pipeline/visual_extract.py --force extract

This file intentionally does not import edu/pipeline/visual_harvest.py (per
spec, so this stage stands alone the same way the harvest stage does); the
small set of shared idioms (log/hhmmss/human, atomic writes, heartbeat-style
stage state, VideoJob/discover_jobs, ProgressTracker, manifest writer) are
copied here in the same house style rather than imported.

The one rule this whole work package exists to enforce: the model never sees
narration, only pixels. §0 of the extraction plan documents a caption that was
hallucinated from narration onto a frame that did not show it -- so ocr_text
here must be independently verifiable against the image alone, and
narration_window is copied through from states.jsonl untouched, never sent to
the VLM as context.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import socket
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import requests

# ----------------------------------------------------------------------------- config

EDU_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = EDU_ROOT.parent
DERIVED_ROOT = EDU_ROOT / "derived"

_DEFAULT_VISUAL_HOME = REPO_ROOT / ".artifacts" / "research" / "visual"
VISUAL_HOME = Path(os.environ.get("STOIC_VISUAL_HOME", str(_DEFAULT_VISUAL_HOME))).resolve()
# Same contract as visual_harvest.py: STOIC_VISUAL_HOME is overridable, but
# every run artefact must land under <repo>/.artifacts/. Fail loudly on a
# misconfigured override rather than silently writing somewhere unexpected.
if REPO_ROOT / ".artifacts" not in VISUAL_HOME.parents and VISUAL_HOME != REPO_ROOT / ".artifacts":
    raise RuntimeError(
        f"STOIC_VISUAL_HOME must resolve under {REPO_ROOT / '.artifacts'}, got {VISUAL_HOME}"
    )

BARS_DIR = REPO_ROOT / ".artifacts" / "research" / "bars"

LMSTUDIO_URL = os.environ.get("LMSTUDIO_URL", "http://localhost:1234/v1")
VLM_MODEL = os.environ.get("STOIC_VLM_MODEL", "qwen3-vl-30b-a3b-instruct-mlx")
VLM_TIMEOUT = 600          # cold model load measured at 74 s; warm calls ~5 s
# A dual-chart frame carries two full price-axis ladders (~60 five-decimal
# prices) plus two time axes. At 1600 the model ran out of budget mid-string on
# exactly those frames, and because the response_format is a strict json_schema
# a truncated response is unparseable -- the state was lost, not merely verbose.
# _strip_axis_ladders cannot help: it is a post-parse filter, so it never sees a
# response that died before parsing.
#
# This is a ceiling, not a target. A compliant frame still returns a few hundred
# tokens; the headroom only exists so a non-compliant one degrades into a slow
# record that the filter then cleans, instead of into an error.
#
# It is bounded by LM Studio's *loaded* context, not the model's 262144 maximum.
# Measured: prompt + one 1920x1080 keyframe = 895 tokens. The model was loaded
# at 4096, which left ~3.2k and is what made 1600 look like a safe cap. Load it
# with room for this value or the truncation simply returns at a higher number.
# scripts/wpv32_run.sh reloads the model at VLM_CONTEXT_LENGTH if it finds it
# loaded smaller, so this holds without anyone remembering to do it by hand.
#
# Sized against wall-clock, not tokens -- the model is local, so tokens are
# free, but time is not. Measured output rate on this machine is ~16.6 tok/s,
# and 5,139 chart states are still ahead, so an unbounded ceiling would let one
# pathological frame idle the run for a quarter of an hour. 6000 is ~20x the
# largest legitimate output seen (~300 tokens) and comfortably clears a full
# dual-axis transcription (~1,500), while still being reachable inside
# VLM_TIMEOUT: 6000 / 16.6 = 361 s.
#
# These three move together. VLM_TIMEOUT must exceed
# VLM_MAX_TOKENS / observed-rate, or the cap is unreachable and the real
# failure becomes a read timeout. STALL_SECONDS must in turn exceed
# VLM_RETRIES * VLM_TIMEOUT + COOL_FOR, or a slow-but-healthy state looks dead.
VLM_MAX_TOKENS = 6000
VLM_CONTEXT_LENGTH = 32768  # what the supervisor loads LM Studio with

# The ceiling above is necessary but NOT sufficient, and 6000 was measured
# failing on the same AUD/USD dual chart that broke 1600. The failure is not
# verbosity: on that frame the model transcribes the visible ladder
# (0.71940 down to 0.69520) and then keeps extrapolating the arithmetic
# sequence *past the bottom of the image* -- 0.66, 0.62, ... 0.57460 -- numbers
# that are nowhere on the chart. It is a decode loop, so it does not terminate,
# and no value of VLM_MAX_TOKENS bounds it; raising the cap only moves the wall
# and costs 361 s to hit it. Prompt RULE 1 already forbids exactly this and the
# model ignores it here, so the prompt is not the lever either.
#
# maxLength on the ocr_text string IS the lever, because LM Studio enforces it
# in the structured-output grammar rather than asking the model to cooperate:
# the string is force-closed at the cap and generation continues into the
# remaining fields. That matters more than it sounds -- chart.drawn_levels and
# chart.annotations come after ocr_text, and they are where this frame's real
# content lives (PDH / PDC / PDL / "Monday Close"). Verified on 0180_002503.jpg:
# finish_reason "stop", record parses, chart block recovered. A lost state
# becomes a recorded one.
#
# 3000 is ~5x the largest legitimate ocr_text measured (574 chars over the first
# 805 records), and verified non-binding: re-running a healthy chart frame with
# the cap in place reproduced its stored record byte for byte. Being generous is
# deliberate -- a genuinely text-dense slide must never be clipped to make a
# pathological chart cheaper. When the cap does bind the record says so
# (ocr_text_capped), so it is auditable and never a silent truncation.
OCR_TEXT_MAX_CHARS = 3000
VLM_RETRIES = 3            # per state, within one run
MAX_STATE_ATTEMPTS = 3     # across runs, before a state is recorded as a permanent error
CONSECUTIVE_FAILURE_ABORT = 10

TICK_SIZE = 0.25
LEVEL_MATCH_TICKS = 1      # a proposal within this many ticks of a daily OHLC is a hit

# Thermal duty cycle. A 30B VL model pinning the GPU for a day straight cooks a
# laptop, and a thermally throttled Mac is slower than one that pauses on
# purpose. Work COOL_EVERY seconds, then idle COOL_FOR seconds, always between
# states so a pause never lands mid-request. The idle time is deliberately left
# inside the throughput measurement -- the ETA has to predict when the job
# actually finishes, not how fast it would run if it never rested.
COOL_EVERY = float(os.environ.get("STOIC_COOL_EVERY", 300))   # seconds of work
COOL_FOR = float(os.environ.get("STOIC_COOL_FOR", 90))        # seconds of idle

# Second, longer tier. The 90 s pause keeps a burst from spiking, but it is far
# too short to shed heat soaked into the chassis over a multi-day run, and this
# job now measures in days rather than the original 17 hours. Every REST_EVERY
# seconds of work the run stops for REST_FOR and lets the machine return to
# something near ambient. Costs ~17 % on top of the short cycle; the alternative
# is sustained high junction temperature for days, which is what actually
# damages hardware. Same rules as the short pause: taken between states, and
# left inside the throughput measurement so the ETA stays honest.
#
# 15 min every 90 min rather than the first cut of 20 min every 2 h: the machine
# was still reported hot. Note the duty ratio is identical (1:6 either way) --
# what changes is how long heat is allowed to accumulate before it is shed, and
# the shorter soak is the thermally kinder of the two at the same cost.
REST_EVERY = float(os.environ.get("STOIC_REST_EVERY", 5400))   # seconds of work
REST_FOR = float(os.environ.get("STOIC_REST_FOR", 900))        # seconds of idle

SCHEMA_VERSION = "wpv-visual-record/v1"
PROGRESS_EVERY = 25        # states between progress log lines
# A "running" stage whose heartbeat is older than this is dead -> redo. The
# heartbeat is beaten after every single state (not every PROGRESS_EVERY), so
# the largest legitimate gap is one state plus one COOL_FOR pause.
#
# The old 900 was sized against a healthy dense frame (75 s measured). That was
# the wrong bound: a state is only given up on after VLM_RETRIES calls, so the
# real worst case is VLM_RETRIES * VLM_TIMEOUT + COOL_FOR = 3*600 + 90 = 1890 s,
# and at 900 a state that merely timed out twice would have been declared dead
# while it was still working. 2400 restores the margin. The cost is that a
# genuinely killed run now takes 40 minutes to be reclaimed rather than 15 --
# paid only on the recovery path, never on the happy one.
STALL_SECONDS = 2400
MAX_ATTEMPTS = 3           # per-video stage attempts before giving up (mirrors visual_harvest.py)
STAGE_NAMES = ["extract", "crosscheck", "report"]

# EXTRACT_PROMPT is sent verbatim -- see docs/notes/2026-07-26-exhaustive-visual-extraction-plan.md
# §3.2. Do not paraphrase this string; the wording (e.g. "Do NOT" repeated per
# failure mode) is deliberate, tuned against the hallucination this pass exists to fix.
# Built from concatenated literal pieces (each <=100 chars) rather than one
# long triple-quoted block purely to satisfy the repo's line-length lint --
# every character of the resulting string is unchanged from the spec.
EXTRACT_PROMPT = "\n\n".join([
    "You are transcribing a single frame from a trading-education video into "
    "an archival, citable record. Return JSON only.",

    "RULE 1, THE MOST IMPORTANT ONE — NEVER transcribe a chart's axis scale. "
    "A charting platform prints a long, regularly-spaced ladder of numbers "
    "down each side of a chart (26,480.00 / 26,440.00 / 26,400.00 / ...) and "
    "a row of clock times or dates along the bottom (01:30 PM / 03:00 PM / "
    "...). Those ladders are furniture. They are NEVER content. Writing them "
    "out is the single worst thing you can do here. If you find yourself "
    "emitting a third consecutive evenly-spaced number, STOP — you are "
    "transcribing an axis and you must skip the rest of it.",

    "ocr_text — a VERBATIM transcription of the frame's real text content, "
    "read top to bottom, one line per visual line, obeying RULE 1. Copy "
    "exactly what is printed: same words, same casing, same punctuation, "
    "same numbers. Do NOT paraphrase. Do NOT complete a truncated word or "
    "sentence. Do NOT correct spelling. Do NOT describe anything. Do NOT add "
    "a single word that is not printed in the image. If a line of text is "
    "present but you cannot read it, write the token [unreadable] on its own "
    "line in its place — never guess at it. If the frame has no text "
    "content, ocr_text is the empty string. Your interpretation of the frame "
    "never belongs in this field.",

    "What ocr_text DOES include: titles and headings; rule statements and "
    "bullet lines; the chart's own header (\"NASDAQ 100 E-mini Futures · 1D "
    "· CME\"); every label the instructor drew on the chart (\"PDH\", "
    "\"PDC\", \"HCOM\", \"Thursday\"); a single highlighted or boxed price "
    "readout that is called out on its own; and watermarks such as "
    "\"StoicEdge.com\".",

    "ocr_confidence — \"high\" if every visible text line was read cleanly; "
    "\"partial\" if some lines are [unreadable] or you are unsure of them; "
    "\"unreadable\" if text is present but essentially none of it can be "
    "read.",

    "frame_class — exactly one of:\n"
    "  slide            a text or graphic slide, no price chart\n"
    "  chart            a price chart with no hand-drawn annotation\n"
    "  chart_annotated  a price chart carrying drawn levels, boxes, arrows "
    "or labels\n"
    "  mixed            both slide-style text and a price chart in the "
    "same frame\n"
    "  talking_head     mostly a person or a webcam view\n"
    "  other            anything else — desktop, platform UI, transition, "
    "black frame",

    "chart — fill this only if a price chart is visible. Otherwise set "
    "instrument and timeframe to \"\" and leave both lists empty.\n"
    "  instrument    the ticker exactly as shown on the chart, e.g. "
    "\"NQ1!\", \"NQ\", \"GC1!\", \"6B\". \"\" if it is not shown.\n"
    "  timeframe     exactly as shown, e.g. \"1D\", \"15m\", \"1H\". \"\" "
    "if it is not shown.\n"
    "  drawn_levels  one entry per horizontal line or level that has a "
    "price printed on or beside it. label = the printed text beside it, "
    "\"\" if unlabelled. value = the price EXACTLY as printed, with the "
    "same digits and separators shown, e.g. \"25,138.00\". These numbers "
    "are read off pixels and are treated downstream as proposals to be "
    "checked against market data — so never round one, never infer one, "
    "never invent one. If a level has no price printed, leave it out "
    "entirely.\n"
    "  annotations   short factual descriptions of drawings that are not "
    "text, e.g. \"down arrow over the fourth candle\", \"red box around "
    "the range high\". Describe only what is drawn.",

    "summary — one sentence, at most 200 characters, saying what this "
    "frame shows. Interpretation belongs here, not in ocr_text.",

    "concepts — up to 6 short trading-concept tags evident in the frame, "
    "e.g. \"break and retest\", \"highest close of the month\", \"SFP\". "
    "Empty list if none is evident.",
])

# Every record carries the sha of the prompt that produced it. The prompt is
# the specification for ocr_text, so two prompts make two different corpora --
# and a corpus silently blended from both is the kind of thing ADR-0021 exists
# to catch. Recorded, and surfaced by --list and the reports, rather than used
# to auto-invalidate: re-extracting 10,120 states must always be a human's
# decision, never a side effect of editing a string.
PROMPT_SHA = hashlib.sha256(EXTRACT_PROMPT.encode("utf-8")).hexdigest()[:12]

RECORD_SCHEMA = {
    "type": "object",
    "properties": {
        "frame_class": {"type": "string", "enum": [
            "slide", "chart", "chart_annotated", "mixed", "talking_head", "other"]},
        # maxLength is a grammar-enforced circuit breaker on the axis-ladder
        # decode loop, not a statement about how long a transcription may be.
        # See OCR_TEXT_MAX_CHARS. It does not change what ocr_text means, and it
        # is non-binding on every record extracted so far, so it does not split
        # the corpus -- prompt_sha, which is what defines ocr_text, is untouched.
        "ocr_text": {"type": "string", "maxLength": OCR_TEXT_MAX_CHARS},
        "ocr_confidence": {"type": "string", "enum": ["high", "partial", "unreadable"]},
        "chart": {
            "type": "object",
            "properties": {
                "instrument": {"type": "string"},
                "timeframe": {"type": "string"},
                "drawn_levels": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"label": {"type": "string"}, "value": {"type": "string"}},
                    "required": ["label", "value"], "additionalProperties": False}},
                "annotations": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["instrument", "timeframe", "drawn_levels", "annotations"],
            "additionalProperties": False,
        },
        "summary": {"type": "string"},
        "concepts": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["frame_class", "ocr_text", "ocr_confidence", "chart", "summary", "concepts"],
    "additionalProperties": False,
}

REQUIRED_MODEL_KEYS = set(RECORD_SCHEMA["required"])


# ------------------------------------------------------------------------------ utils

def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def hhmmss(t: float) -> str:
    t = max(0.0, float(t))
    h, rem = divmod(int(t), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def human(seconds: float) -> str:
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"


def write_atomic(path: Path, data: str | bytes) -> None:
    """Write via temp + rename so a partial file can never be mistaken for done."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    mode = "wb" if isinstance(data, bytes) else "w"
    with open(tmp, mode, **({} if isinstance(data, bytes) else {"encoding": "utf-8"})) as fh:
        fh.write(data)
    os.replace(tmp, path)


def write_json(path: Path, obj) -> None:
    write_atomic(path, json.dumps(obj, indent=2, ensure_ascii=False))


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def read_jsonl(path: Path) -> list[dict]:
    """Tolerant reader: silently drops a trailing unparseable line -- the
    signature of a crash mid-append -- rather than failing the whole load."""
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if i != len(lines) - 1:
                raise  # only the last line may be a partial write
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    write_atomic(path, body + ("\n" if body else ""))


def append_jsonl_durable(path: Path, row: dict) -> None:
    """Append one line and force it to disk so a kill loses at most one record.

    Used only during the extract stage's per-state loop; the end-of-video
    rewrite (write_jsonl) is what normalizes ordering and dedupes afterward.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


# ------------------------------------------------------------------------------- jobs

@dataclass
class VideoJob:
    id: str
    src: Path
    duration_sec: float

    @property
    def out(self) -> Path:
        return VISUAL_HOME / self.id

    @property
    def state_path(self) -> Path:
        return self.out / "extract_state.json"

    @property
    def states_path(self) -> Path:
        return self.out / "states.jsonl"

    @property
    def keyframes_dir(self) -> Path:
        return self.out / "keyframes_v2"

    @property
    def records_path(self) -> Path:
        return self.out / "visual_records.jsonl"

    @property
    def checks_path(self) -> Path:
        return self.out / "chart_checks.jsonl"

    @property
    def report_path(self) -> Path:
        return self.out / "extract_report.json"

    @property
    def group(self) -> str:
        return self.id.split("_", 1)[0]

    @property
    def state_count(self) -> int:
        """Number of distinct visual states, counted without parsing the JSON.

        This is the unit of cost for this pass -- see ProgressTracker for why
        it is not video seconds.
        """
        if not self.states_path.exists():
            return 0
        with open(self.states_path, encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())


def discover_jobs() -> list[VideoJob]:
    """Every video is enumerated from edu/derived/*/meta.json (source of truth),
    exactly as visual_harvest.py does it."""
    jobs = []
    for meta_path in sorted(DERIVED_ROOT.glob("*/meta.json")):
        meta = read_json(meta_path)
        if not meta or "source" not in meta or "id" not in meta:
            continue
        jobs.append(VideoJob(
            id=meta["id"], src=EDU_ROOT / meta["source"],
            duration_sec=float(meta["duration_sec"]),
        ))
    # concept_* first, then cs_*, then live_*, alphabetical within each group.
    # The 5,139 live-session states are ~half the corpus and the least
    # rule-dense; if the ~17-hour run is cut short, the concept and
    # case-study material -- the material the retrain plan actually leans
    # on -- must already be done.
    group_rank = {"concept": 0, "cs": 1, "live": 2}
    jobs.sort(key=lambda j: (group_rank.get(j.group, 9), j.id))
    return jobs


# ------------------------------------------------------------------------ state engine

def _idle(seconds: float, state: VideoState) -> None:
    """Sleep for a thermal pause, beating the heartbeat as it goes.

    The 20-minute rest is long enough that a single beat at the start would
    leave a gap another process could read as a dead stage, so the sleep is
    broken up. Beating during an idle is honest: the process is alive and
    intends to continue -- which is exactly what the heartbeat claims.
    """
    deadline = time.time() + seconds
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            return
        state.beat("extract")
        time.sleep(min(60.0, remaining))


def _pid_alive(pid: int) -> bool:
    """Is this pid running? Signal 0 checks without delivering anything.

    EPERM counts as alive: the process exists, it just is not ours. Erring
    towards "alive" is the safe direction -- a wrong "dead" would let a second
    process open a records file the first is still appending to.
    """
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError, TypeError, ValueError):
        return True
    return True


class VideoState:
    """Per-video stage tracker: status/attempts/heartbeat, one entry per stage.

    Deliberately a separate state file (extract_state.json) from
    visual_harvest.py's state.json -- this pass has its own stage names and
    must not collide with, or be reset by, the harvest stage's bookkeeping.
    """

    def __init__(self, job: VideoJob):
        self.job = job
        self.path = job.state_path
        self.data = read_json(self.path) or {}
        self.data.setdefault("stages", {})

    def _flush(self) -> None:
        write_json(self.path, self.data)

    def entry(self, stage: str) -> dict:
        return self.data["stages"].get(stage, {})

    def status(self, stage: str) -> str:
        e = self.entry(stage)
        if not e:
            return "pending"
        if e.get("status") != "running":
            return e.get("status", "pending")

        # Liveness beats the timer. A "running" marker means one of two very
        # different things -- a process really is working on this stage, or a
        # killed one never got to clear it -- and the heartbeat age cannot tell
        # them apart. The owning pid can: if it is gone, the stage is free now,
        # with no waiting. That matters because the user kills this job whenever
        # the laptop runs hot, and without this an immediate restart skips every
        # video the previous run had open until STALL_SECONDS expires.
        #
        # Guarded by host, because a pid from another machine says nothing about
        # this one -- .artifacts/ does not travel, but the state file is small
        # enough to be copied by hand, and a false "dead" would let two
        # processes write one records file.
        owner, host = e.get("pid"), e.get("host")
        if owner and host == socket.gethostname():
            # Authoritative in both directions. Falling through to the timer
            # when the owner is alive would reintroduce exactly the false
            # positive this replaces: a state legitimately sitting in a long
            # VLM call would be declared dead while it was still working.
            if _pid_alive(owner):
                return "running"
            log(f"    ! recovering stalled stage '{stage}' (owner pid {owner} is gone)")
            e["status"] = "pending"
            self._flush()
            return "pending"

        # Fallback for the cases liveness cannot answer: no pid recorded (a
        # state file written by an older build), or a run that died on another
        # host. Only here does the heartbeat age decide anything.
        if (time.time() - e.get("heartbeat", 0)) < STALL_SECONDS:
            return "running"
        log(f"    ! recovering stalled stage '{stage}' (heartbeat stale)")
        e["status"] = "pending"
        self._flush()
        return "pending"

    def attempts(self, stage: str) -> int:
        return self.entry(stage).get("attempts", 0)

    def start(self, stage: str) -> None:
        e = self.data["stages"].setdefault(stage, {})
        e.update(
            status="running", heartbeat=time.time(), attempts=e.get("attempts", 0) + 1,
            pid=os.getpid(), host=socket.gethostname(),
        )
        self._flush()

    def beat(self, stage: str) -> None:
        e = self.data["stages"].get(stage)
        if e is not None:
            e["heartbeat"] = time.time()
            self._flush()

    def done(self, stage: str, elapsed_sec: float, **extra) -> None:
        e = self.data["stages"].setdefault(stage, {})
        e.update(
            status="done", elapsed_sec=round(elapsed_sec, 3),
            finished=datetime.now().isoformat(timespec="seconds"), **extra,
        )
        e.pop("error", None)
        self._flush()

    def failed(self, stage: str, elapsed_sec: float, error: str) -> None:
        e = self.data["stages"].setdefault(stage, {})
        e.update(status="failed", elapsed_sec=round(elapsed_sec, 3), error=error[:500])
        self._flush()

    def reset_from(self, stage: str) -> None:
        """Drop `stage` and everything downstream of it (for --force)."""
        idx = STAGE_NAMES.index(stage)
        for name in STAGE_NAMES[idx:]:
            self.data["stages"].pop(name, None)
        self._flush()


# ---------------------------------------------------------------------------- VLM call

class LMStudioError(RuntimeError):
    pass


class TruncatedResponse(LMStudioError):
    """The model ran out of token budget mid-response.

    Split out from LMStudioError because it is the one failure that must NOT
    be retried: the call is made at temperature 0, so a second and third
    attempt regenerate the same tokens and hit the same wall, turning one
    361 s loss into 18 minutes of it. A transport error is worth retrying; a
    deterministic overrun is not.
    """


def _parse_model_json(content: str) -> dict | None:
    try:
        obj = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or not REQUIRED_MODEL_KEYS.issubset(obj.keys()):
        return None
    return obj


def call_vlm(image_path: Path, timeout: float = VLM_TIMEOUT) -> dict:
    """One chat/completions call, strict json_schema response_format.

    The schema constraint is not cosmetic here -- on this model it is
    measured at ~5 s/state warm vs ~74 s for free-form generation, which is
    the difference between a several-hour run and an overnight-plus one.
    Narration is never included in the message: the documented failure this
    whole work package exists to fix was a caption hallucinated from
    narration onto a frame that did not show it, so this call must be purely
    visual and independently checkable against the image alone.
    """
    b64 = base64.b64encode(image_path.read_bytes()).decode()
    payload = {
        "model": VLM_MODEL,
        "temperature": 0,
        "max_tokens": VLM_MAX_TOKENS,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": EXTRACT_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "visual_record", "strict": True, "schema": RECORD_SCHEMA},
        },
    }
    r = requests.post(f"{LMSTUDIO_URL}/chat/completions", json=payload, timeout=timeout)
    if r.status_code != 200:
        raise LMStudioError(f"HTTP {r.status_code}: {r.text[:300]}")
    body = r.json()
    if "error" in body:
        raise LMStudioError(f"server error: {str(body['error'])[:300]}")
    choices = body.get("choices")
    if not choices:
        raise LMStudioError("no choices in response")
    content = choices[0].get("message", {}).get("content", "")
    parsed = _parse_model_json(content)
    if parsed is None:
        # Under a strict json_schema the only routine way to get unparseable
        # output is to run out of budget mid-string, and "did not parse" sent
        # three hours of diagnosis down the wrong path. Name the real cause,
        # and report both numbers, because the binding limit may be LM Studio's
        # loaded context rather than max_tokens.
        if choices[0].get("finish_reason") == "length":
            used = body.get("usage", {})
            raise TruncatedResponse(
                f"truncated at max_tokens={VLM_MAX_TOKENS} "
                f"(prompt {used.get('prompt_tokens', '?')} + completion "
                f"{used.get('completion_tokens', '?')} tokens) despite the "
                f"ocr_text maxLength={OCR_TEXT_MAX_CHARS} grammar cap -- the "
                f"overrun is in some other field: {content[:120]}"
            )
        raise LMStudioError(f"response did not parse as the required schema: {content[:200]}")
    return parsed


# ----------------------------------------------------------------------- stage: extract

class ServerDown(RuntimeError):
    """LM Studio stopped answering. This aborts the WHOLE run, not just the
    current video.

    Per-video failure is the wrong response to a dead server: the next video
    would fail its own 10 states, and the one after that, marching through the
    corpus laying down error records that say nothing except "the server was
    off". Stopping immediately keeps the resume point honest -- everything on
    disk is real work, and the run picks up exactly where the server died.
    """


def _count_ocr_lines(ocr_text: str) -> tuple[int, int]:
    """Deterministic (unreadable_lines, ocr_line_count) from ocr_text -- never
    taken from the model, since a model can't be trusted to count its own
    output honestly and this is cheap to compute exactly."""
    lines = [ln for ln in ocr_text.split("\n") if ln.strip()]
    unreadable = sum(1 for ln in lines if ln.strip() == "[unreadable]")
    return unreadable, len(lines)


_AXIS_PRICE_RE = re.compile(r"^\$?\d{1,3}(?:,\d{3})*(?:\.\d+)?$|^\d+(?:\.\d+)?$")
_AXIS_TIME_RE = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?$", re.IGNORECASE)
AXIS_RUN_MIN = 4  # consecutive ladder lines before a run is treated as an axis


def _strip_axis_ladders(ocr_text: str) -> tuple[str, int]:
    """Remove chart-axis ladders from ocr_text, deterministically.

    The prompt tells the model to skip a chart's price/time axis, and it
    obeys on most frames but not all -- measured compliance was roughly half.
    Corpus quality must not depend on that, so the ladders are also removed
    here, in plain code that behaves the same way every time.

    A "ladder" is a run of >= AXIS_RUN_MIN consecutive lines that are all
    bare prices, or all bare clock times. The run-length requirement is what
    keeps a genuinely called-out price -- "26,037.25" sitting alone between
    "PDC" and "Thursday" -- from being mistaken for axis furniture, since a
    called-out number never arrives in a block of four.

    Returns (cleaned_text, lines_removed). The caller keeps the original as
    ocr_text_raw whenever this removes anything, so nothing is ever lost.
    """
    lines = ocr_text.split("\n")
    keep = [True] * len(lines)
    i = 0
    while i < len(lines):
        for pattern in (_AXIS_PRICE_RE, _AXIS_TIME_RE):
            j = i
            while j < len(lines) and pattern.match(lines[j].strip()):
                j += 1
            if j - i >= AXIS_RUN_MIN:
                for k in range(i, j):
                    keep[k] = False
                i = j - 1
                break
        i += 1
    cleaned = [ln for ln, k in zip(lines, keep, strict=True) if k]
    removed = sum(1 for k in keep if not k)
    return "\n".join(cleaned).strip("\n"), removed


def _chart_block(model_json: dict) -> dict | None:
    """chart is included iff frame_class involves a chart, or the model
    returned any non-empty chart content anyway (belt and suspenders against
    a model that draws a level but mis-classifies the frame)."""
    frame_class = model_json["frame_class"]
    chart = model_json.get("chart") or {}
    has_content = bool(
        chart.get("instrument") or chart.get("timeframe")
        or chart.get("drawn_levels") or chart.get("annotations")
    )
    if frame_class not in ("chart", "chart_annotated", "mixed") and not has_content:
        return None
    levels = [
        lvl for lvl in chart.get("drawn_levels", [])
        if str(lvl.get("value", "")).strip()
    ]
    return {
        "instrument": chart.get("instrument", ""),
        "timeframe": chart.get("timeframe", ""),
        "drawn_levels": levels,
        "annotations": chart.get("annotations", []),
    }


def _build_ok_record(s: dict, model_json: dict, elapsed: float, attempts: int) -> dict:
    raw_ocr = model_json["ocr_text"]
    ocr_text, axis_stripped = _strip_axis_ladders(raw_ocr)
    unreadable, line_count = _count_ocr_lines(ocr_text)
    record = {
        "id": s["id"],
        "schema_version": SCHEMA_VERSION,
        "video": s["video"],
        "state_id": s["state_id"],
        "t_start": s["t_start"], "t_end": s["t_end"], "duration_sec": s["duration_sec"],
        "hms_start": s["hms_start"], "hms_end": s["hms_end"],
        "rep_t": s["rep_t"], "rep_hms": s["rep_hms"],
        "frame_count": s["frame_count"], "recur_group": s["recur_group"],
        "source_frame": s["source_frame"],
        "status": "ok",
        "frame_class": model_json["frame_class"],
        "ocr_text": ocr_text,
        "ocr_confidence": model_json["ocr_confidence"],
        "unreadable_lines": unreadable,
        "ocr_line_count": line_count,
    }
    if axis_stripped:
        # Only carried when the filter actually fired, so the audit can diff
        # cleaned against raw on exactly the frames where it matters.
        record["axis_lines_stripped"] = axis_stripped
        record["ocr_text_raw"] = raw_ocr
    if len(raw_ocr) >= OCR_TEXT_MAX_CHARS:
        # The grammar closed the string rather than the model finishing it, so
        # this transcription is incomplete by construction. Usually it is the
        # axis decode loop being cut off, which is the cap working as intended
        # and costs nothing real -- but a text-dense slide could land here too,
        # and that would be a genuine loss. Flagged either way so §3.3 can tell
        # the two apart by inspection instead of the difference going unseen.
        record["ocr_text_capped"] = True
        record["ocr_text_raw"] = raw_ocr
    chart = _chart_block(model_json)
    if chart is not None:
        record["chart"] = chart
    record.update({
        "summary": model_json["summary"],
        "concepts": model_json.get("concepts", []),
        "narration_window": s["narration_window"],
        "model": VLM_MODEL,
        "prompt_sha": PROMPT_SHA,
        "extracted_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "elapsed_sec": round(elapsed, 2),
        "attempts": attempts,
    })
    return record


def _build_error_record(s: dict, error: str, attempts: int) -> dict:
    return {
        "id": s["id"],
        "schema_version": SCHEMA_VERSION,
        "video": s["video"],
        "state_id": s["state_id"],
        "t_start": s["t_start"], "t_end": s["t_end"], "duration_sec": s["duration_sec"],
        "hms_start": s["hms_start"], "hms_end": s["hms_end"],
        "rep_t": s["rep_t"], "rep_hms": s["rep_hms"],
        "frame_count": s["frame_count"], "recur_group": s["recur_group"],
        "source_frame": s["source_frame"],
        "status": "error",
        "narration_window": s["narration_window"],
        "error": error,
        "attempts": attempts,
    }


def _load_existing_records(path: Path) -> dict[str, dict]:
    """Load visual_records.jsonl tolerantly and dedupe by id, last wins."""
    by_id: dict[str, dict] = {}
    for row in read_jsonl(path):
        rid = row.get("id")
        if rid:
            by_id[rid] = row
    return by_id


def _extract_intact(job: VideoJob) -> bool:
    """Cheap on-disk check mirroring visual_harvest.py's _extract_intact: does
    every state have an 'ok' or terminal-error record? A stage marked done
    whose file is missing coverage for some state must be re-entered and
    repair only what is missing -- gate on disk state, not a flag."""
    states = read_jsonl(job.states_path)
    if not states:
        return False
    existing = _load_existing_records(job.records_path)
    for s in states:
        rec = existing.get(s["id"])
        if rec is None:
            return False
        if rec.get("status") == "ok":
            continue
        if rec.get("status") == "error" and rec.get("attempts", 0) >= MAX_STATE_ATTEMPTS:
            continue
        return False
    return True


def stage_extract(
    job: VideoJob, state: VideoState, tracker: ProgressTracker, max_states: int | None = None
) -> dict:
    """One VLM call per distinct state, in state_id order. Resumable at state
    granularity: an 'ok' record is skipped, an 'error' record under
    MAX_STATE_ATTEMPTS is retried (attempts carried forward), and an error at
    the cap is left alone. Every finished record is appended + fsynced
    immediately so a kill loses at most one record; the file is rewritten
    atomically (deduped, state_id-sorted) at the end of the video.
    """
    states = read_jsonl(job.states_path)
    if not states:
        raise RuntimeError(f"no states.jsonl for {job.id}")
    states.sort(key=lambda s: s["state_id"])

    existing = _load_existing_records(job.records_path)

    todo: list[dict] = []
    skipped = 0
    for s in states:
        rec = existing.get(s["id"])
        if rec is not None:
            if rec.get("status") == "ok":
                skipped += 1
                continue
            if rec.get("status") == "error" and rec.get("attempts", 0) >= MAX_STATE_ATTEMPTS:
                skipped += 1
                continue
        todo.append(s)
    if max_states is not None:
        # max_states is a cumulative cap on this video's total extracted
        # states (across resumes), not a per-run cap -- otherwise re-running
        # the same --max-states command would advance to the next batch
        # instead of being a true no-op once the cap is already met.
        budget = max(0, max_states - skipped)
        todo = todo[:budget]

    total = len(states)
    start = time.time()
    consecutive_failures = 0
    extracted_this_run = 0
    errors_this_run = 0
    # high-water marks so each progress tick hands the tracker only the
    # increment since the last one, never the running total again
    reported, reported_wall = 0, 0.0
    last_cool = time.time()
    last_rest = time.time()

    if not todo:
        log(f"    extract: nothing to do (skipped {skipped} already done, {total} total)")

    for i, s in enumerate(todo, 1):
        prior_attempts = existing.get(s["id"], {}).get("attempts", 0)
        img_path = job.out / s["source_frame"]

        if not img_path.exists():
            attempts = prior_attempts + 1
            rec = _build_error_record(s, f"keyframe missing: {img_path}", attempts)
            append_jsonl_durable(job.records_path, rec)
            existing[s["id"]] = rec
            errors_this_run += 1
            consecutive_failures += 1
            if consecutive_failures >= CONSECUTIVE_FAILURE_ABORT:
                raise ServerDown(
                    f"{consecutive_failures} consecutive state failures -- "
                    "is LM Studio still up and the model loaded?"
                )
            continue

        last_err = ""
        model_json = None
        call_start = time.time()
        for attempt in range(1, VLM_RETRIES + 1):
            try:
                model_json = call_vlm(img_path)
                break
            except TruncatedResponse as exc:
                # Deterministic at temperature 0 -- see TruncatedResponse.
                last_err = f"{type(exc).__name__}: {exc}"
                break
            except Exception as exc:
                last_err = f"{type(exc).__name__}: {exc}"
                if attempt < VLM_RETRIES:
                    time.sleep(min(30, 5 * attempt))
        elapsed = time.time() - call_start

        attempts = prior_attempts + 1
        if model_json is None:
            rec = _build_error_record(s, last_err[:500], attempts)
            errors_this_run += 1
            consecutive_failures += 1
        else:
            rec = _build_ok_record(s, model_json, elapsed, attempts)
            extracted_this_run += 1
            consecutive_failures = 0

        append_jsonl_durable(job.records_path, rec)
        existing[s["id"]] = rec
        # Beaten every state, not every PROGRESS_EVERY: a 25-state gap on
        # chart-heavy video exceeds STALL_SECONDS and would make a healthy run
        # look dead to the next process that inspects it.
        state.beat("extract")

        if consecutive_failures >= CONSECUTIVE_FAILURE_ABORT:
            raise ServerDown(
                f"{consecutive_failures} consecutive state failures -- "
                "is LM Studio still up and the model loaded?"
            )

        # Thermal pause, taken between states so it never interrupts a request
        # in flight. Skipped after the final state -- there is nothing left to
        # cool down for.
        if REST_FOR > 0 and i < len(todo) and time.time() - last_rest >= REST_EVERY:
            worked = int(time.time() - last_rest)
            log(f"    resting {int(REST_FOR / 60)}m (after {worked // 60}m of work)")
            _idle(REST_FOR, state)
            # A long rest cools the machine at least as well as the short pause
            # would have, so the short cycle restarts from here rather than
            # firing again the moment work resumes.
            last_rest = last_cool = time.time()
        elif COOL_FOR > 0 and i < len(todo) and time.time() - last_cool >= COOL_EVERY:
            log(f"    cooling {int(COOL_FOR)}s (after {int(time.time() - last_cool)}s of work)")
            _idle(COOL_FOR, state)
            last_cool = time.time()

        if i % PROGRESS_EVERY == 0 or i == len(todo):
            wall = time.time() - start
            # Throughput is scoped to states this run actually extracted --
            # already-done states appear in neither numerator nor
            # denominator, per coding_rules.md, so resumed runs never
            # understate the true rate.
            tracker.note_extracted(i - reported, wall - reported_wall)
            reported, reported_wall = i, wall
            write_progress(tracker.all_jobs, tracker, job.id)
            rate = i / wall if wall > 0 else 0.0
            video_remaining = len(todo) - i
            video_eta = video_remaining / rate if rate > 0 else 0.0
            state.beat("extract")
            log(
                f"    extract {i}/{len(todo)} (skipped {skipped} already done, "
                f"{total} total)  elapsed {human(wall)}  {rate:.2f} states/s  "
                f"video ETA {human(video_eta)}  | {tracker.corpus_line()}"
            )

    write_jsonl(job.records_path, [existing[s["id"]] for s in states if s["id"] in existing])

    return {
        "total_states": total,
        "extracted_this_run": extracted_this_run,
        "skipped": skipped,
        "errors": errors_this_run,
    }


# -------------------------------------------------------------------- stage: crosscheck

_BARS_CACHE: dict[str, list[dict]] = {}


def _load_bars(instrument: str) -> list[dict] | None:
    """Load and cache <instrument>_D.jsonl once per run, prices in points
    (ticks * TICK_SIZE), never re-read per level."""
    if instrument in _BARS_CACHE:
        return _BARS_CACHE[instrument]
    path = BARS_DIR / f"{instrument}_D.jsonl"
    if not path.exists():
        _BARS_CACHE[instrument] = None
        return None
    bars = []
    for row in read_jsonl(path):
        bars.append({
            "trading_date": row["trading_date"],
            "open": row["open_ticks"] * TICK_SIZE,
            "high": row["high_ticks"] * TICK_SIZE,
            "low": row["low_ticks"] * TICK_SIZE,
            "close": row["close_ticks"] * TICK_SIZE,
        })
    _BARS_CACHE[instrument] = bars or None
    return _BARS_CACHE[instrument]


# The VLM reads whatever the charting platform prints in the header, and
# TradingView prints a *description*, not a ticker: "NASDAQ 100 E-mini
# Futures", not "NQ1!". Matching tickers alone silently sent every NQ level
# down the no_bars path -- the crosscheck did nothing on the one instrument
# the corpus actually has bars for. Substrings are checked in order, first
# match wins, and the non-NQ symbols are named too so "no bars for CL" reads
# as a fact rather than as an unparsed string.
# Descriptive phrases, matched as substrings. These are long enough that a
# substring test is safe.
_INSTRUMENT_PHRASES: list[tuple[tuple[str, ...], str]] = [
    (("NASDAQ",), "NQ"),
    (("CRUDE OIL", "LIGHT CRUDE", "WTI"), "CL"),
    (("BITCOIN",), "BTC"),
    (("GOLD",), "GC"),
    (("RUSSELL",), "RTY"),
    (("S&P",), "ES"),
    (("GBP/JPY", "GBPJPY", "GBP JPY"), "GBPJPY"),
]

# Bare tickers, matched as WHOLE TOKENS only. A substring test here is a trap:
# "ES" is inside "Wheat FuturES" and "CL" is inside "CLose", so substring
# matching silently mislabels instruments -- which is worse than not matching
# at all, because a wrong symbol sends real levels to the wrong bars.
_INSTRUMENT_TICKERS: dict[str, str] = {
    "NQ": "NQ", "MNQ": "NQ", "NDX": "NQ",
    "CL": "CL", "MCL": "CL",
    "BTC": "BTC", "XBT": "BTC",
    "GC": "GC", "MGC": "GC",
    "RTY": "RTY", "M2K": "RTY",
    "ES": "ES", "MES": "ES",
}


def _normalize_instrument(raw: str) -> str:
    """Map whatever the chart header says to a symbol. Anything unrecognised
    is returned uppercased and simply has no bars -- a fact to report (the
    corpus covers gold, GBP/JPY, RTY, BTC and CL as well as NQ), not a
    failure.

    The VLM reads whatever the charting platform prints in the header, and
    TradingView prints a *description*, not a ticker: "NASDAQ 100 E-mini
    Futures", not "NQ1!". Matching tickers alone silently sent every NQ level
    down the no_bars path -- the crosscheck did nothing on the one instrument
    the corpus actually has bars for.
    """
    s = raw.strip().upper()
    for suffix in ("1!", "!", ".C.0"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    s = s.strip()

    for needles, symbol in _INSTRUMENT_PHRASES:
        if any(n in s for n in needles):
            return symbol
    for token in re.findall(r"[A-Z0-9&]+", s):
        if token in _INSTRUMENT_TICKERS:
            return _INSTRUMENT_TICKERS[token]
    return s


def _parse_level_value(raw: str) -> float | None:
    cleaned = raw.replace(",", "").replace("$", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _check_level(video: str, t_start: float, hms_start: str, rec_id: str,
                  instrument_raw: str, label: str, value_raw: str) -> dict:
    row = {
        "id": rec_id, "video": video, "t_start": t_start, "hms_start": hms_start,
        "instrument_raw": instrument_raw, "instrument": _normalize_instrument(instrument_raw),
        "label": label, "value_raw": value_raw,
    }
    parsed = _parse_level_value(value_raw)
    row["parsed"] = parsed
    if parsed is None:
        row["in_range"] = None
        row["daily_ohlc_match"] = None
        row["verdict"] = "unparseable"
        return row

    bars = _load_bars(row["instrument"]) if row["instrument"] == "NQ" else None
    if bars is None:
        row["in_range"] = None
        row["daily_ohlc_match"] = None
        row["verdict"] = "no_bars"
        return row

    lo = min(b["low"] for b in bars)
    hi = max(b["high"] for b in bars)
    in_range = lo <= parsed <= hi
    row["in_range"] = in_range

    best = None
    best_delta = None
    for b in bars:
        for field in ("open", "high", "low", "close"):
            delta_ticks = round(abs(parsed - b[field]) / TICK_SIZE, 2)
            if best_delta is None or delta_ticks < best_delta:
                best_delta = delta_ticks
                best = {
                    "field": field, "trading_date": b["trading_date"],
                    "price": b[field], "delta_ticks": delta_ticks,
                }
    match = best if best is not None and best["delta_ticks"] <= LEVEL_MATCH_TICKS else None
    row["daily_ohlc_match"] = match

    # A level not matching a daily OHLC is NOT an error -- it may sit on a
    # 15-minute swing high/low the daily bars never touch. This is a
    # citation-quality signal, not a gate; never turn "in_range_no_match"
    # into a failure condition downstream.
    if match is not None:
        row["verdict"] = "ohlc_match"
    elif in_range:
        row["verdict"] = "in_range_no_match"
    else:
        row["verdict"] = "out_of_range"
    return row


def stage_crosscheck(job: VideoJob, state: VideoState) -> dict:
    """Deterministic, no model: join visual_records.jsonl's drawn_levels
    against the daily bars, one output row per proposed level.

    Never mutates visual_records.jsonl -- raw model output stays immutable
    and citable exactly as extracted; this stage is a derived annotation
    joined on `id`, written to its own file.
    """
    records = read_jsonl(job.records_path)
    rows = []
    for rec in records:
        chart = rec.get("chart")
        if not chart:
            continue
        for lvl in chart.get("drawn_levels", []):
            rows.append(_check_level(
                rec["video"], rec["t_start"], rec["hms_start"], rec["id"],
                chart.get("instrument", ""), lvl.get("label", ""), lvl.get("value", ""),
            ))
    write_jsonl(job.checks_path, rows)

    verdicts: dict[str, int] = {}
    for row in rows:
        verdicts[row["verdict"]] = verdicts.get(row["verdict"], 0) + 1
    return {"levels": len(rows), "verdicts": verdicts}


# ------------------------------------------------------------------------ stage: report

def _build_video_report(job: VideoJob) -> dict | None:
    records = read_jsonl(job.records_path)
    if not records:
        return None
    checks = read_jsonl(job.checks_path)

    ok = [r for r in records if r.get("status") == "ok"]
    err = [r for r in records if r.get("status") == "error"]

    by_class: dict[str, int] = {}
    by_conf: dict[str, int] = {}
    total_lines = 0
    total_unreadable = 0
    charts = 0
    drawn_levels = 0
    for r in ok:
        by_class[r["frame_class"]] = by_class.get(r["frame_class"], 0) + 1
        by_conf[r["ocr_confidence"]] = by_conf.get(r["ocr_confidence"], 0) + 1
        total_lines += r.get("ocr_line_count", 0)
        total_unreadable += r.get("unreadable_lines", 0)
        if "chart" in r:
            charts += 1
            drawn_levels += len(r["chart"].get("drawn_levels", []))

    verdicts: dict[str, int] = {}
    for c in checks:
        verdicts[c["verdict"]] = verdicts.get(c["verdict"], 0) + 1

    # More than one sha here means this video's records were produced by two
    # different prompts, i.e. two different definitions of ocr_text. Surfaced
    # as a count so a human sees it; never silently reconciled.
    by_prompt: dict[str, int] = {}
    for r in ok:
        sha = r.get("prompt_sha", "unknown")
        by_prompt[sha] = by_prompt.get(sha, 0) + 1

    elapsed_list = [r["elapsed_sec"] for r in ok if "elapsed_sec" in r]

    return {
        "video": job.id,
        "total_states": len(records),
        "ok": len(ok),
        "error": len(err),
        "prompt_sha_counts": by_prompt,
        "current_prompt_sha": PROMPT_SHA,
        "frame_class_counts": by_class,
        "ocr_confidence_counts": by_conf,
        "total_ocr_lines": total_lines,
        "total_unreadable_lines": total_unreadable,
        "unreadable_line_rate": (
            round(total_unreadable / total_lines, 4) if total_lines else None
        ),
        "records_with_chart": charts,
        "total_drawn_levels": drawn_levels,
        "crosscheck_verdict_counts": verdicts,
        "elapsed_sec_mean": round(statistics.mean(elapsed_list), 3) if elapsed_list else None,
        "elapsed_sec_median": round(statistics.median(elapsed_list), 3) if elapsed_list else None,
    }


def stage_report(job: VideoJob, state: VideoState) -> dict:
    """Deterministic counts only -- ADR-0021 / §3.3 want numbers a human
    reads, never a pass/fail verdict baked into the artifact."""
    report = _build_video_report(job)
    if report is None:
        report = {"video": job.id, "total_states": 0}
    write_json(job.report_path, report)
    return {"ok": report.get("ok", 0), "error": report.get("error", 0)}


# ------------------------------------------------------------------------------ driver

def _stage_stale(input_path: Path, output_path: Path) -> bool:
    """crosscheck/report are cheap and deterministic -- always re-run when
    their input is newer than their last output, not just when not-done."""
    if not output_path.exists():
        return True
    if not input_path.exists():
        return False
    return input_path.stat().st_mtime > output_path.stat().st_mtime


def process_video(
    job: VideoJob, tracker: ProgressTracker, pos: int, total: int, max_states: int | None
) -> bool:
    """Run every pending stage of one video in order. Returns True iff the
    video ends fully done (all stages 'done')."""
    job.out.mkdir(parents=True, exist_ok=True)
    state = VideoState(job)
    ok = True

    for name in STAGE_NAMES:
        status = state.status(name)

        if name == "extract":
            # Same on-disk integrity re-check visual_harvest.py's extract
            # stage has: a stage marked done whose visual_records.jsonl does
            # not cover every state with an ok-or-terminal-error record is
            # re-entered and repairs only what is missing -- gate on disk
            # state, not a flag (coding_rules.md).
            if status == "done" and not _extract_intact(job):
                log("    extract: marked done but record(s) missing/incomplete, repairing")
                status = "pending"
        else:
            input_path = job.records_path if name == "crosscheck" else job.checks_path
            output_path = job.checks_path if name == "crosscheck" else job.report_path
            if status == "done" and _stage_stale(input_path, output_path):
                status = "pending"

        if status == "done":
            continue
        if status == "running":
            owner = state.entry(name).get("pid", "?")
            log(f"    {name}: already running (owner pid {owner} alive), skipping video")
            return False
        if status == "failed" and state.attempts(name) >= MAX_ATTEMPTS:
            log(f"    {name}: failed {state.attempts(name)}x, giving up on this video")
            return False

        stage_start = time.time()
        state.start(name)
        try:
            if name == "extract":
                extra = stage_extract(job, state, tracker, max_states=max_states)
            elif name == "crosscheck":
                extra = stage_crosscheck(job, state)
            else:
                extra = stage_report(job, state)
        except Exception as exc:
            elapsed = time.time() - stage_start
            state.failed(name, elapsed, f"{type(exc).__name__}: {exc}")
            log(f"    {name}: FAILED ({type(exc).__name__}: {str(exc)[:200]})")
            ok = False
            break
        elapsed = time.time() - stage_start
        state.done(name, elapsed, **extra)
        # Only stage_extract feeds the tracker's throughput, and it does so
        # per state (note_extracted). crosscheck/report are deterministic and
        # near-instant; folding their wall time into the rate would make the
        # 17 h+ ETA drift for no reason.
        tracker.log_stage_line(job, pos, total, name, elapsed)

    return ok


class ProgressTracker:
    """Corpus-wide progress bookkeeping, counted in **states, not video seconds**.

    visual_harvest.py measures progress in seconds of footage because its cost
    is one ffmpeg decode pass -- linear in duration. This pass is one VLM call
    per distinct state, so its cost is linear in *states*, and the two units
    disagree badly across this corpus: the four live sessions are 26 % of the
    footage but 51 % of the states (5,139 of 10,120). A seconds-based ETA
    would sprint through the concept videos and then appear to stall for the
    entire second half of a 20-hour run.

    Same split as visual_harvest.py otherwise: `done_states` is scoped to the
    whole 16-video corpus (so the percentage means the same thing regardless
    of --only), while throughput and ETA come only from states this run
    actually extracted -- already-done work is in neither numerator nor
    denominator (coding_rules.md).
    """

    def __init__(self, all_jobs: list[VideoJob]):
        self.all_jobs = all_jobs
        self.total_states = sum(j.state_count for j in all_jobs) or 1
        self.done_states = 0
        for j in all_jobs:
            recs = _load_existing_records(j.records_path)
            self.done_states += sum(1 for r in recs.values() if not _state_remaining(r))
        # states extracted by THIS run, and the wall time they took -- the only
        # numbers the ETA is allowed to be built from
        self.work_states = 0
        self.work_wall_elapsed = 0.0
        self.run_start = time.time()

    def note_extracted(self, n: int, wall: float) -> None:
        """Called from the extract loop so the corpus ETA is live during a
        video, not only at its end -- a 1,792-state video is many hours and
        must not go that long without a corpus-level number."""
        self.done_states += n
        self.work_states += n
        self.work_wall_elapsed += wall

    @property
    def rate(self) -> float:
        """States per second, from this run's extraction work only."""
        return self.work_states / self.work_wall_elapsed if self.work_wall_elapsed > 0 else 0.0

    def corpus_line(self) -> str:
        pct = 100.0 * self.done_states / self.total_states
        remaining = max(0, self.total_states - self.done_states)
        rate = self.rate
        eta = human(remaining / rate) if rate > 0 else "n/a"
        return (
            f"corpus {self.done_states}/{self.total_states} states ({pct:.1f}%)"
            f"  ETA {eta}"
        )

    def log_stage_line(
        self, job: VideoJob, pos: int, total: int, stage: str, elapsed: float
    ) -> None:
        log(
            f"[{pos:2d}/{total}] {job.id}  {stage} {elapsed:.1f}s"
            f"  | {self.corpus_line()}"
            f"  | run elapsed {human(time.time() - self.run_start)}"
        )


# ------------------------------------------------------------------------------ manifest

def build_manifest(all_jobs: list[VideoJob]) -> dict:
    videos = []
    for j in all_jobs:
        state = VideoState(j)
        stages = {name: state.entry(name).get("status", "pending") for name in STAGE_NAMES}
        extract_e = state.entry("extract")
        videos.append({
            "id": j.id,
            "duration_sec": j.duration_sec,
            "stages": stages,
            "extract_total_states": extract_e.get("total_states"),
            "extract_extracted_this_run": extract_e.get("extracted_this_run"),
            "extract_skipped": extract_e.get("skipped"),
            "extract_errors": extract_e.get("errors"),
            "elapsed_sec": {name: state.entry(name).get("elapsed_sec") for name in STAGE_NAMES},
        })
    return {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "video_count": len(all_jobs),
        "videos": videos,
    }


def write_progress(all_jobs: list[VideoJob], tracker: ProgressTracker, current: str = "") -> None:
    """Corpus-level checkpoint, rewritten *during* a video, not only between
    videos.

    The manifest is written once per video, and the biggest video is 1,792
    states -- many hours in which a crashed or power-cut run would leave
    nothing at the corpus level to read. This file is the one place a later
    session (or a human at 3am) can look to answer "how far did it get?"
    without parsing 16 record files.
    """
    write_json(VISUAL_HOME / "extract_progress.json", {
        "updated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "current_video": current,
        "done_states": tracker.done_states,
        "total_states": tracker.total_states,
        "pct": round(100.0 * tracker.done_states / tracker.total_states, 2),
        "states_per_sec_this_run": round(tracker.rate, 4) if tracker.rate else None,
        "eta_seconds": (
            round((tracker.total_states - tracker.done_states) / tracker.rate)
            if tracker.rate > 0 else None
        ),
        "prompt_sha": PROMPT_SHA,
        "model": VLM_MODEL,
    })


def write_manifest(all_jobs: list[VideoJob]) -> None:
    write_json(VISUAL_HOME / "extract_manifest.json", build_manifest(all_jobs))


def write_corpus_report(all_jobs: list[VideoJob]) -> None:
    """Corpus-level extract_report.json aggregating every video that has one,
    plus a per-video table -- counts only, no verdicts (ADR-0021)."""
    per_video = []
    totals = {
        "total_states": 0, "ok": 0, "error": 0, "records_with_chart": 0, "total_drawn_levels": 0,
    }
    class_totals: dict[str, int] = {}
    conf_totals: dict[str, int] = {}
    verdict_totals: dict[str, int] = {}
    line_total = 0
    unreadable_total = 0

    for j in all_jobs:
        report = read_json(j.report_path)
        if not report or "ok" not in report:
            continue
        per_video.append(report)
        for key in ("total_states", "ok", "error", "records_with_chart", "total_drawn_levels"):
            totals[key] += report.get(key) or 0
        for k, v in (report.get("frame_class_counts") or {}).items():
            class_totals[k] = class_totals.get(k, 0) + v
        for k, v in (report.get("ocr_confidence_counts") or {}).items():
            conf_totals[k] = conf_totals.get(k, 0) + v
        for k, v in (report.get("crosscheck_verdict_counts") or {}).items():
            verdict_totals[k] = verdict_totals.get(k, 0) + v
        line_total += report.get("total_ocr_lines") or 0
        unreadable_total += report.get("total_unreadable_lines") or 0

    write_json(VISUAL_HOME / "extract_report.json", {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "videos_reported": len(per_video),
        "videos_total": len(all_jobs),
        **totals,
        "frame_class_counts": class_totals,
        "ocr_confidence_counts": conf_totals,
        "total_ocr_lines": line_total,
        "total_unreadable_lines": unreadable_total,
        "unreadable_line_rate": round(unreadable_total / line_total, 4) if line_total else None,
        "crosscheck_verdict_counts": verdict_totals,
        "per_video": per_video,
    })


# --------------------------------------------------------------------------- preflight

def preflight() -> bool:
    """Confirm LM Studio is up, VLM_MODEL is loaded, and one tiny real chat
    call round-trips -- a 17-hour job must not discover a connection refusal
    at hour one."""
    t0 = time.time()
    try:
        r = requests.get(f"{LMSTUDIO_URL}/models", timeout=10)
        r.raise_for_status()
        model_ids = {m["id"] for m in r.json().get("data", [])}
    except Exception as exc:
        log(f"preflight FAILED: cannot reach {LMSTUDIO_URL}/models ({exc})")
        return False
    if VLM_MODEL not in model_ids:
        log(f"preflight FAILED: model {VLM_MODEL!r} not loaded in LM Studio ({sorted(model_ids)})")
        return False
    try:
        r = requests.post(
            f"{LMSTUDIO_URL}/chat/completions",
            json={
                "model": VLM_MODEL,
                "messages": [{"role": "user", "content": "reply with OK"}],
                "max_tokens": 5, "temperature": 0,
            },
            timeout=VLM_TIMEOUT,
        )
        r.raise_for_status()
        r.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        log(f"preflight FAILED: {VLM_MODEL} did not answer a test chat request ({exc})")
        return False
    log(f"preflight ok: {VLM_MODEL} loaded and responsive ({time.time() - t0:.1f}s)")
    return True


# --------------------------------------------------------------------------------- CLI

def print_list(all_jobs: list[VideoJob]) -> None:
    for j in all_jobs:
        state = VideoState(j)
        states = read_jsonl(j.states_path)
        records = read_jsonl(j.records_path)
        n_ok = sum(1 for r in records if r.get("status") == "ok")
        marks = " ".join(f"{n}={state.entry(n).get('status', '-')}" for n in STAGE_NAMES)
        print(
            f"{j.id}  ({human(j.duration_sec)})  states={len(states)}  extracted={n_ok}\n"
            f"    {marks}"
        )


def _state_remaining(rec: dict | None) -> bool:
    """A state still has extraction work left iff it has no record yet, or
    its record is a retriable error under MAX_STATE_ATTEMPTS."""
    if rec is None:
        return True
    return rec.get("status") == "error" and rec.get("attempts", 0) < MAX_STATE_ATTEMPTS


def print_status(all_jobs: list[VideoJob]) -> None:
    """Plain-English 'where is this up to', readable months later with no
    flags to remember. Reads only disk -- safe to run while the job is live."""
    prog = read_json(VISUAL_HOME / "extract_progress.json") or {}
    total = done = 0
    rows = []
    shas: set[str] = set()
    for j in all_jobs:
        states = j.state_count
        recs = _load_existing_records(j.records_path)
        d = sum(1 for r in recs.values() if not _state_remaining(r))
        errs = sum(1 for r in recs.values() if r.get("status") == "error")
        shas.update(r.get("prompt_sha", "?") for r in recs.values() if r.get("status") == "ok")
        total += states
        done += d
        mark = "done" if d >= states and states else ("  --" if d == 0 else "part")
        rows.append(f"  {mark}  {j.id:52} {d:5d}/{states:<5d}" + (f"  {errs} err" if errs else ""))

    print(f"corpus: {done}/{total} states extracted ({100.0 * done / max(1, total):.1f}%)\n")
    print("\n".join(rows))

    if prog:
        eta = prog.get("eta_seconds")
        print(
            f"\nlast checkpoint {prog.get('updated')} on {prog.get('current_video') or '-'}"
            + (f", ETA at that rate {human(eta)}" if eta else "")
        )
    if len(shas) > 1:
        print(f"\n!! {len(shas)} different prompt versions in this corpus: {sorted(shas)}")
        print("   records were extracted under different definitions of ocr_text.")

    remaining = total - done
    if remaining:
        print(f"\n{remaining} states remaining. To start or resume -- re-runnable after a kill,")
        print("a crash or a power cut, with nothing to clean up first:")
        print("  scripts/extract.sh")
    else:
        print("\nnothing remaining — extraction is complete.")


def print_dry_run(jobs: list[VideoJob]) -> None:
    total_remaining = 0
    rate_samples: list[float] = []
    for j in jobs:
        states = read_jsonl(j.states_path)
        records = _load_existing_records(j.records_path)
        remaining = 0
        for s in states:
            if _state_remaining(records.get(s["id"])):
                remaining += 1
        total_remaining += remaining
        for rec in records.values():
            if rec.get("status") == "ok" and "elapsed_sec" in rec:
                rate_samples.append(rec["elapsed_sec"])
        print(f"{j.id}: {remaining} states remaining (of {len(states)})")

    seconds_per_state = statistics.mean(rate_samples) if rate_samples else 6.0
    label = "measured" if rate_samples else "assumed (no records extracted yet)"
    est_seconds = total_remaining * seconds_per_state
    print(f"\ntotal remaining: {total_remaining} states")
    print(f"estimated wall time: {human(est_seconds)} at {seconds_per_state:.2f} s/state ({label})")


def main() -> int:
    # declared before first use: --cool-every/--cool-for read these as their
    # argparse defaults and then write them back
    global COOL_EVERY, COOL_FOR, REST_EVERY, REST_FOR

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--only", help="substring filter on the video id")
    ap.add_argument("--group", choices=["concept", "cs", "live"], help="filter by prefix group")
    ap.add_argument("--max-states", type=int, help="cap states extracted per video (smoke tests)")
    ap.add_argument(
        "--force", choices=STAGE_NAMES, help="redo this stage and everything downstream"
    )
    ap.add_argument("--list", action="store_true", help="show videos and stage status, then exit")
    ap.add_argument(
        "--status", action="store_true",
        help="plain-English progress summary and how to resume, then exit",
    )
    ap.add_argument(
        "--remaining", action="store_true",
        help="print just the number of states still to extract, then exit (for scripts)",
    )
    ap.add_argument(
        "--print-context-length", action="store_true",
        help="print the LM Studio context length this run needs, then exit (for scripts)",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="report what would be extracted and exit without calling the model",
    )
    ap.add_argument(
        "--cool-every", type=float, default=COOL_EVERY, metavar="SEC",
        help=f"seconds of work between thermal pauses (default {COOL_EVERY:.0f})",
    )
    ap.add_argument(
        "--cool-for", type=float, default=COOL_FOR, metavar="SEC",
        help=f"seconds to idle at each thermal pause, 0 disables (default {COOL_FOR:.0f})",
    )
    ap.add_argument(
        "--rest-every", type=float, default=REST_EVERY, metavar="SEC",
        help=f"seconds of work between long rests (default {REST_EVERY:.0f})",
    )
    ap.add_argument(
        "--rest-for", type=float, default=REST_FOR, metavar="SEC",
        help=f"seconds to idle at each long rest, 0 disables (default {REST_FOR:.0f})",
    )
    args = ap.parse_args()
    COOL_EVERY, COOL_FOR = args.cool_every, args.cool_for
    REST_EVERY, REST_FOR = args.rest_every, args.rest_for

    if args.print_context_length:
        # Answered before any discovery so the supervisor can ask it on a bare
        # checkout, with no artifacts on disk and LM Studio not yet up.
        print(VLM_CONTEXT_LENGTH)
        return 0

    VISUAL_HOME.mkdir(parents=True, exist_ok=True)
    all_jobs = discover_jobs()
    if not all_jobs:
        log("no videos found under edu/derived/*/meta.json")
        return 1

    if args.remaining:
        # machine-readable, for the supervisor loop; touches no model and no state
        total = sum(
            1
            for j in all_jobs
            for st in read_jsonl(j.states_path)
            if _state_remaining(_load_existing_records(j.records_path).get(st["id"]))
        )
        print(total)
        return 0

    if args.status:
        print_status(all_jobs)
        return 0

    if args.list:
        print_list(all_jobs)
        return 0

    jobs = all_jobs
    if args.only:
        needle = args.only.lower()
        jobs = [j for j in jobs if needle in j.id.lower()]
    if args.group:
        jobs = [j for j in jobs if j.group == args.group]
    if not jobs:
        log(f"no video matches --only {args.only!r} --group {args.group!r}")
        return 1

    if args.dry_run:
        print_dry_run(jobs)
        return 0

    if not preflight():
        return 1

    if args.force:
        for j in jobs:
            VideoState(j).reset_from(args.force)

    footage = human(sum(j.duration_sec for j in jobs))
    log(f"{len(jobs)}/{len(all_jobs)} video(s) selected, {footage} of footage")
    tracker = ProgressTracker(all_jobs)
    # Say up front what is already on disk, so a resumed run is obvious from
    # its first line of log rather than inferred from the numbers later.
    remaining = tracker.total_states - tracker.done_states
    if tracker.done_states:
        log(f"resuming: {tracker.done_states}/{tracker.total_states} states already extracted, "
            f"{remaining} to go")
    else:
        log(f"starting fresh: {tracker.total_states} states to extract")
    log(f"prompt {PROMPT_SHA} | model {VLM_MODEL} | "
        f"cooling {int(COOL_FOR)}s every {int(COOL_EVERY)}s, "
        f"resting {int(REST_FOR / 60)}m every {int(REST_EVERY / 60)}m")
    write_progress(all_jobs, tracker)

    ok = failed = 0
    aborted = False
    for pos, job in enumerate(jobs, 1):
        log(f"[{pos}/{len(jobs)}] {job.id}")
        try:
            if process_video(job, tracker, pos, len(jobs), args.max_states):
                ok += 1
            else:
                failed += 1
        except ServerDown as exc:
            # Everything already extracted is on disk and fsynced; stopping
            # here is what keeps the resume point meaningful.
            log(f"ABORTING RUN: {exc}")
            aborted = True
            failed += 1
            write_manifest(all_jobs)
            write_progress(all_jobs, tracker, job.id)
            break
        write_manifest(all_jobs)
        write_progress(all_jobs, tracker, job.id)

    write_corpus_report(all_jobs)
    log("")
    log(f"finished: {ok} ok, {failed} incomplete")
    log(f"progress: {tracker.done_states}/{tracker.total_states} states")
    log(f"output: {VISUAL_HOME}")
    if aborted:
        log("the server stopped answering. Restart LM Studio, load "
            f"{VLM_MODEL}, then rerun the SAME command -- it resumes per state.")
    elif failed:
        log("rerun the same command to retry incomplete videos")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
