#!/usr/bin/env python3
"""
Extract transcripts and aligned key-moment screenshots from the trading education videos.

One directory of derived artefacts per source video, mirroring the source tree under
edu/derived/. Every stage is idempotent: rerunning skips completed work, and a stage
that died mid-flight (crash, kill, power loss) is detected and redone.

Stages
  probe       meta.json                     duration / resolution via ffprobe
  audio       .scratch/audio/<slug>.wav     16 kHz mono PCM
  transcribe  transcript.json, .md          mlx-whisper large-v3-turbo (Metal)
  moments     moments.json                  local LLM picks the teaching moments
  keyframes   keyframes/*.jpg, .json        frames + the narration spoken over each
  caption     captions.json                 opt-in: local VLM describes each frame

Usage
  .venv/bin/python scripts/extract_video_knowledge.py
  .venv/bin/python scripts/extract_video_knowledge.py --list
  .venv/bin/python scripts/extract_video_knowledge.py --only vol7
  .venv/bin/python scripts/extract_video_knowledge.py --caption
  .venv/bin/python scripts/extract_video_knowledge.py --force keyframes
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import requests

# ----------------------------------------------------------------------------- config

# this file lives in edu/pipeline/, so edu/ is one level up and the repo root two
EDU_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = EDU_ROOT.parent
VIDEO_ROOT = EDU_ROOT                       # videos discovered anywhere under edu/
OUT_ROOT = EDU_ROOT / "derived"             # all derived artefacts land here
SCRATCH = REPO_ROOT / ".scratch"            # transient audio + reports

LMSTUDIO_URL = os.environ.get("LMSTUDIO_URL", "http://localhost:1234/v1")
LLM_MODEL = os.environ.get("STOIC_LLM_MODEL", "qwen3-vl-30b-a3b-instruct-mlx")
VLM_MODEL = os.environ.get("STOIC_VLM_MODEL", LLM_MODEL)
WHISPER_MODEL = os.environ.get("STOIC_WHISPER", "mlx-community/whisper-large-v3-turbo")

# Keyframe selection. Tuned to over-capture rather than under-capture.
SAMPLE_FPS = 1           # transcript/visual analysis granularity
HASH_W, HASH_H = 160, 90  # downscaled grey frame used for drift detection
DRIFT_THRESH = 2.5       # mean abs pixel delta from last kept frame
MIN_GAP = 6.0            # never two screenshots closer than this
MAX_GAP = 45.0           # never leave a stretch longer than this uncovered
NARRATION_LAG = 3.0      # grab the frame N seconds after the words, not on them
JPEG_QUALITY = 3         # ffmpeg -q:v, 2=best 31=worst

LLM_WINDOW = 900.0       # seconds of transcript per LLM request
LLM_TIMEOUT = 1800       # generous: the model is local, correctness beats speed
LLM_RETRIES = 3
LLM_MAX_TOKENS = 16000

STALL_SECONDS = 900      # a "running" stage with a heartbeat older than this is dead
MAX_ATTEMPTS = 3

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".m4v", ".webm"}


# ------------------------------------------------------------------------------ utils

def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def hhmmss(t: float) -> str:
    t = max(0.0, float(t))
    h, rem = divmod(int(t), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def fname_ts(t: float) -> str:
    return hhmmss(t).replace(":", "")


def human(seconds: float) -> str:
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


# boilerplate that appears in every source filename and carries no information
TITLE_NOISE = re.compile(
    r"(stoic trader concepts|stoic traders|·|\bconcepts\b"
    r"|\b\d{3,4}p\b|\b(?:full ?hd|hd|4k)\b)", re.IGNORECASE
)


def clean_title(stem: str) -> str:
    title = stem.replace("_", " ").replace("-", " ")
    title = TITLE_NOISE.sub(" ", title)
    return re.sub(r"\s+", " ", title).strip()


def categorize(rel: Path) -> tuple[str, str | None]:
    """Return (category, volume) derived from the source location."""
    parts = [p.lower() for p in rel.parts]
    if "case_studies" in parts:
        vol = next((p for p in parts if re.fullmatch(r"vol\d+", p)), None)
        return "case_study", vol
    if "live_trading_sessions" in parts:
        return "live_session", None
    return "concept", None


def make_video_id(rel: Path) -> str:
    category, vol = categorize(rel)
    slug = slugify(clean_title(rel.stem))
    if category == "case_study":
        return f"cs_{vol}_{slug}" if vol else f"cs_{slug}"
    if category == "live_session":
        slug = re.sub(r"^live_trading_session_", "", slug)
        return f"live_{slug}"
    return f"concept_{slug}"


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, **kw)


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
    except Exception:
        return None


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError, PermissionError) as exc:
        return isinstance(exc, PermissionError)
    return True


# ------------------------------------------------------------------------------- jobs

@dataclass
class Job:
    src: Path          # absolute path to the video
    rel: Path          # path relative to edu/
    video_id: str      # short stable id, also the output dir name
    category: str      # concept | case_study | live_session
    volume: str | None  # e.g. "vol7" for case studies, else None
    title: str         # cleaned human title

    @property
    def out(self) -> Path:
        return OUT_ROOT / self.video_id

    @property
    def name(self) -> str:
        return self.title

    @property
    def state_path(self) -> Path:
        return self.out / "state.json"

    @property
    def audio_path(self) -> Path:
        return SCRATCH / "audio" / f"{self.video_id}.wav"

    def signature(self) -> str:
        st = self.src.stat()
        return f"{st.st_size}-{int(st.st_mtime)}"


def discover_jobs() -> list[Job]:
    jobs = []
    for path in sorted(VIDEO_ROOT.rglob("*")):
        if path.suffix.lower() not in VIDEO_EXTS or not path.is_file():
            continue
        if OUT_ROOT in path.parents:
            continue
        rel = path.relative_to(VIDEO_ROOT)
        category, volume = categorize(rel)
        jobs.append(Job(
            src=path, rel=rel,
            video_id=make_video_id(rel),
            category=category, volume=volume,
            title=clean_title(path.stem),
        ))
    return jobs


# ------------------------------------------------------------------------ state engine

class State:
    """Per-video stage tracker with heartbeat-based stall recovery."""

    def __init__(self, job: Job):
        self.job = job
        self.path = job.state_path
        self.lock = threading.Lock()
        self.data = read_json(self.path) or {}
        self.data.setdefault("source", str(job.rel))
        self.data.setdefault("stages", {})
        self.data["signature"] = self.data.get("signature") or job.signature()

    def _flush(self) -> None:
        write_json(self.path, self.data)

    def source_changed(self) -> bool:
        return self.data.get("signature") != self.job.signature()

    def reset_all(self) -> None:
        with self.lock:
            self.data["stages"] = {}
            self.data["signature"] = self.job.signature()
            self._flush()

    def status(self, stage: str) -> str:
        entry = self.data["stages"].get(stage)
        if not entry:
            return "pending"
        if entry.get("status") != "running":
            return entry.get("status", "pending")
        # A running stage is only real if its owner is alive and the heartbeat is fresh.
        pid, beat = entry.get("pid", -1), entry.get("heartbeat", 0)
        if pid == os.getpid():
            return "running"
        if pid_alive(pid) and (time.time() - beat) < STALL_SECONDS:
            return "running"
        log(f"    ! recovering stalled stage '{stage}' (pid {pid} gone or heartbeat stale)")
        entry["status"] = "pending"
        self._flush()
        return "pending"

    def attempts(self, stage: str) -> int:
        return self.data["stages"].get(stage, {}).get("attempts", 0)

    def mark(self, stage: str, status: str, **extra) -> None:
        with self.lock:
            entry = self.data["stages"].setdefault(stage, {})
            entry.update(status=status, ts=time.time(), **extra)
            self._flush()

    def beat(self, stage: str) -> None:
        with self.lock:
            entry = self.data["stages"].get(stage)
            if entry and entry.get("status") == "running":
                entry["heartbeat"] = time.time()
                self._flush()


class Heartbeat:
    """Keeps a running stage's heartbeat fresh so a kill is distinguishable from a hang."""

    def __init__(self, state: State, stage: str, interval: float = 15.0):
        self.state, self.stage, self.interval = state, stage, interval
        self.stop = threading.Event()
        self.thread = None

    def __enter__(self):
        self.state.mark(
            self.stage, "running",
            pid=os.getpid(), heartbeat=time.time(),
            attempts=self.state.attempts(self.stage) + 1,
        )

        def loop():
            while not self.stop.wait(self.interval):
                self.state.beat(self.stage)

        self.thread = threading.Thread(target=loop, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=2)
        if exc_type is None:
            self.state.mark(self.stage, "done")
        else:
            self.state.mark(self.stage, "failed", error=f"{exc_type.__name__}: {exc}"[:400])
        return False


# ----------------------------------------------------------------------------- stages

def stage_probe(job: Job) -> None:
    proc = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate",
                "-show_entries", "format=duration",
                "-of", "json", str(job.src)])
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {proc.stderr.decode()[:300]}")
    info = json.loads(proc.stdout)
    stream = (info.get("streams") or [{}])[0]
    write_json(job.out / "meta.json", {
        "id": job.video_id,
        "category": job.category,
        "volume": job.volume,
        "title": job.title,
        "source": str(job.rel),
        "duration_sec": float(info["format"]["duration"]),
        "duration_hms": hhmmss(float(info["format"]["duration"])),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "fps": stream.get("r_frame_rate"),
    })


def stage_audio(job: Job) -> None:
    job.audio_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = job.audio_path.with_suffix(".wav.tmp")
    proc = run(["ffmpeg", "-v", "error", "-y", "-i", str(job.src),
                "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
                "-f", "wav", str(tmp)])
    if proc.returncode != 0:
        raise RuntimeError(f"audio extract failed: {proc.stderr.decode()[:300]}")
    os.replace(tmp, job.audio_path)


def stage_transcribe(job: Job) -> None:
    import mlx_whisper  # imported lazily: loads Metal runtime

    result = mlx_whisper.transcribe(
        str(job.audio_path),
        path_or_hf_repo=WHISPER_MODEL,
        condition_on_previous_text=False,   # avoids runaway repetition on long lectures
    )
    segments = [
        {"start": round(float(s["start"]), 2),
         "end": round(float(s["end"]), 2),
         "text": s["text"].strip()}
        for s in result["segments"] if s["text"].strip()
    ]
    write_json(job.out / "transcript.json", {
        "source": str(job.rel),
        "language": result.get("language"),
        "model": WHISPER_MODEL,
        "segments": segments,
    })

    lines = [f"# {job.name}", "", f"_Source: `{job.rel}`_", ""]
    lines += [f"**[{hhmmss(s['start'])}]** {s['text']}" for s in segments]
    write_atomic(job.out / "transcript.md", "\n\n".join(lines) + "\n")

    plain = " ".join(s["text"] for s in segments)
    write_atomic(job.out / "transcript.txt", plain + "\n")


# ---- moment selection -------------------------------------------------------------

MOMENT_PROMPT = """You are indexing a trading-education screencast so a student can study it from screenshots alone.

Below is a timestamped transcript segment. Identify every moment where the instructor directs attention to something visible on the chart that a screenshot would usefully capture: price levels, market structure, entries, stops, targets, invalidation, chart or timeframe switches, drawings and annotations, examples being walked through.

Rules:
- Err strongly on the side of INCLUDING a moment. More screenshots is better than fewer.
- Aim for roughly one moment every 20-45 seconds of transcript.
- Use the timestamp where the thing being discussed is on screen.
- Only use timestamps that appear in the transcript below.

Return ONLY a JSON object and nothing else:
{"moments":[{"t": <seconds as a number>, "label": "<short title>", "why": "<what is on screen>"}]}

TRANSCRIPT:
"""


def _extract_json(message: dict):
    """Pull the first valid JSON object out of a model reply.

    LM Studio routes structured output into reasoning_content for some reasoning
    models and leaves content empty, so both fields are searched.
    """
    for key in ("content", "reasoning_content"):
        text = (message.get(key) or "").strip()
        if not text:
            continue
        text = re.sub(r"```(?:json)?", "", text).strip()
        start = text.find("{")
        while start != -1:
            depth = 0
            in_str = False
            escaped = False
            for i in range(start, len(text)):
                ch = text[i]
                if in_str:
                    if escaped:
                        escaped = False
                    elif ch == "\\":
                        escaped = True
                    elif ch == '"':
                        in_str = False
                elif ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i + 1])
                        except json.JSONDecodeError:
                            break
            start = text.find("{", start + 1)
    return None


def llm_chat(messages: list[dict], model: str, max_tokens: int = LLM_MAX_TOKENS) -> dict:
    last = None
    for attempt in range(1, LLM_RETRIES + 1):
        try:
            resp = requests.post(
                f"{LMSTUDIO_URL}/chat/completions",
                json={"model": model, "messages": messages,
                      "temperature": 0.3, "max_tokens": max_tokens},
                timeout=LLM_TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
            if "error" in payload:
                raise RuntimeError(str(payload["error"])[:300])
            return payload["choices"][0]["message"]
        except Exception as exc:  # noqa: BLE001 - retry any transport/model error
            last = exc
            log(f"    LLM attempt {attempt}/{LLM_RETRIES} failed: {type(exc).__name__}: {str(exc)[:150]}")
            time.sleep(min(30, 5 * attempt))
    raise RuntimeError(f"LLM failed after {LLM_RETRIES} attempts: {last}")


def stage_moments(job: Job) -> None:
    transcript = read_json(job.out / "transcript.json")
    segments = transcript["segments"]
    duration = read_json(job.out / "meta.json")["duration_sec"]

    windows: list[list[dict]] = []
    current: list[dict] = []
    window_start = 0.0
    for seg in segments:
        if current and seg["start"] - window_start >= LLM_WINDOW:
            windows.append(current)
            current, window_start = [], seg["start"]
        if not current:
            window_start = seg["start"]
        current.append(seg)
    if current:
        windows.append(current)

    moments: list[dict] = []
    for idx, window in enumerate(windows, 1):
        body = "\n".join(f"[{s['start']:.1f}] {s['text']}" for s in window)
        lo, hi = window[0]["start"], window[-1]["end"]
        log(f"    moments window {idx}/{len(windows)} ({hhmmss(lo)}-{hhmmss(hi)})")
        obj = None
        for parse_try in range(1, LLM_RETRIES + 1):
            message = llm_chat([{"role": "user", "content": MOMENT_PROMPT + body}], LLM_MODEL)
            obj = _extract_json(message)
            if obj and isinstance(obj.get("moments"), list):
                break
            # cold-model load or a stray reply can yield unparseable output; retry
            log(f"    window {idx}: no JSON on parse try {parse_try}/{LLM_RETRIES}, retrying")
            obj = None
            time.sleep(5)
        if obj is None:
            log(f"    ! window {idx} returned no usable JSON; gap-fill will cover it")
            continue
        for raw in obj["moments"]:
            try:
                t = float(raw["t"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (lo - 1 <= t <= hi + 1):
                continue  # model invented a timestamp outside the window
            moments.append({
                "t": round(min(max(t, 0.0), duration), 2),
                "label": str(raw.get("label", "")).strip()[:200],
                "why": str(raw.get("why", "")).strip()[:500],
            })

    moments.sort(key=lambda m: m["t"])
    write_json(job.out / "moments.json", {
        "source": str(job.rel),
        "model": LLM_MODEL,
        "windows": len(windows),
        "count": len(moments),
        "moments": moments,
    })
    log(f"    LLM proposed {len(moments)} moments across {len(windows)} window(s)")


# ---- keyframes --------------------------------------------------------------------

def sample_grey(job: Job) -> np.ndarray:
    """Decode the whole video once at SAMPLE_FPS into small greyscale frames."""
    proc = run(["ffmpeg", "-v", "error", "-i", str(job.src),
                "-vf", f"fps={SAMPLE_FPS},scale={HASH_W}:{HASH_H},format=gray",
                "-f", "rawvideo", "-"])
    if proc.returncode != 0:
        raise RuntimeError(f"frame sampling failed: {proc.stderr.decode()[:300]}")
    buf = np.frombuffer(proc.stdout, dtype=np.uint8)
    usable = (len(buf) // (HASH_W * HASH_H)) * HASH_W * HASH_H
    return buf[:usable].reshape(-1, HASH_H, HASH_W).astype(np.float32)


def drift_seconds(frames: np.ndarray) -> list[int]:
    """Seconds where the picture has drifted meaningfully from the last kept frame."""
    if len(frames) == 0:
        return []
    kept = [0]
    anchor = frames[0]
    for i in range(1, len(frames)):
        if i - kept[-1] < MIN_GAP:
            continue
        if float(np.abs(frames[i] - anchor).mean()) > DRIFT_THRESH:
            kept.append(i)
            anchor = frames[i]
    return kept


def narration_for(segments: list[dict], start: float, end: float) -> str:
    return " ".join(
        s["text"] for s in segments
        if s["end"] > start and s["start"] < end
    ).strip()


def stage_keyframes(job: Job) -> None:
    meta = read_json(job.out / "meta.json")
    duration = meta["duration_sec"]
    segments = read_json(job.out / "transcript.json")["segments"]
    moments = (read_json(job.out / "moments.json") or {}).get("moments", [])

    frames = sample_grey(job)
    candidates: dict[int, dict] = {}

    def offer(t: float, source: str, label: str = "", why: str = "") -> None:
        sec = int(round(min(max(t, 0.0), max(0.0, duration - 1))))
        existing = candidates.get(sec)
        if existing is None:
            candidates[sec] = {"t": sec, "source": source, "label": label, "why": why}
        elif not existing["label"] and label:
            existing.update(source=source, label=label, why=why)

    # 1. what the instructor called out, offset so the visual has caught up
    for m in moments:
        offer(m["t"] + NARRATION_LAG, "llm", m.get("label", ""), m.get("why", ""))
    # 2. visual changes that happened without narration
    for sec in drift_seconds(frames):
        offer(float(sec), "drift")
    # 3. guarantee no long stretch is left uncovered
    chosen = sorted(candidates)
    filled: list[int] = []
    previous = 0.0
    for sec in chosen + [int(duration)]:
        while sec - previous > MAX_GAP:
            previous += MAX_GAP
            filled.append(int(previous))
        previous = sec
    for sec in filled:
        offer(float(sec), "gap")

    # enforce minimum spacing, keeping LLM-chosen moments in preference to fillers
    ordered = [candidates[s] for s in sorted(candidates)]
    selected: list[dict] = []
    for cand in ordered:
        if selected and cand["t"] - selected[-1]["t"] < MIN_GAP:
            if cand["source"] == "llm" and selected[-1]["source"] != "llm":
                selected[-1] = cand
            continue
        selected.append(cand)

    if not selected:
        raise RuntimeError("no keyframes selected")

    # single decode pass, pulling exactly the chosen seconds
    frames_dir = job.out / "keyframes"
    staging = job.out / ".keyframes.tmp"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    secs = [c["t"] for c in selected]
    for batch_start in range(0, len(secs), 300):
        batch = secs[batch_start:batch_start + 300]
        expr = "+".join(f"eq(n\\,{s})" for s in batch)
        proc = run(["ffmpeg", "-v", "error", "-y", "-i", str(job.src),
                    "-vf", f"fps={SAMPLE_FPS},select='{expr}'",
                    "-fps_mode", "vfr", "-q:v", str(JPEG_QUALITY),
                    str(staging / f"b{batch_start:05d}_%04d.jpg")])
        if proc.returncode != 0:
            raise RuntimeError(f"frame extract failed: {proc.stderr.decode()[:300]}")

    produced = sorted(staging.glob("*.jpg"))
    if len(produced) != len(selected):
        log(f"    ! ffmpeg produced {len(produced)} frames for {len(selected)} requests; "
            f"aligning to the shorter list")
    pairs = list(zip(selected, produced))

    entries = []
    for idx, (cand, tmp_img) in enumerate(pairs):
        nxt = pairs[idx + 1][0]["t"] if idx + 1 < len(pairs) else duration
        final_name = f"{idx:04d}_{fname_ts(cand['t'])}.jpg"
        os.replace(tmp_img, staging / final_name) if tmp_img.name != final_name else None
        entries.append({
            "index": idx,
            "t": cand["t"],
            "hms": hhmmss(cand["t"]),
            "file": f"keyframes/{final_name}",
            "source": cand["source"],
            "label": cand["label"],
            "why": cand["why"],
            # what is being said while this frame is on screen, with a little lead-in
            "narration": narration_for(segments, cand["t"] - NARRATION_LAG - 2, nxt),
        })

    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    os.replace(staging, frames_dir)

    write_json(job.out / "keyframes.json", {
        "source": str(job.rel),
        "count": len(entries),
        "by_source": {s: sum(1 for e in entries if e["source"] == s)
                      for s in ("llm", "drift", "gap")},
        "keyframes": entries,
    })
    log(f"    {len(entries)} keyframes "
        f"(llm={sum(1 for e in entries if e['source'] == 'llm')}, "
        f"drift={sum(1 for e in entries if e['source'] == 'drift')}, "
        f"gap={sum(1 for e in entries if e['source'] == 'gap')})")


# ---- captions (opt-in) ------------------------------------------------------------

CAPTION_PROMPT = """This is a frame from a trading-education screencast. Describe what a student should notice on this chart: instrument and timeframe if visible, price structure, marked levels, drawings, and anything the narration refers to.

Narration spoken over this frame:
"{narration}"

Reply with 2-4 sentences of plain prose. No preamble."""


def stage_caption(job: Job) -> None:
    data = read_json(job.out / "keyframes.json")
    entries = data["keyframes"]
    out_path = job.out / "captions.json"

    done = {c["index"]: c for c in (read_json(out_path) or {}).get("captions", [])}
    captions = list(done.values())

    for entry in entries:
        if entry["index"] in done:
            continue
        img = job.out / entry["file"]
        if not img.exists():
            continue
        b64 = base64.b64encode(img.read_bytes()).decode()
        prompt = CAPTION_PROMPT.format(narration=(entry["narration"] or "")[:1500])
        message = llm_chat([{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]}], VLM_MODEL, max_tokens=800)
        text = (message.get("content") or "").strip()
        captions.append({"index": entry["index"], "t": entry["t"],
                         "file": entry["file"], "caption": text})
        captions.sort(key=lambda c: c["index"])
        # checkpoint after every frame so captioning resumes exactly where it stopped
        write_json(out_path, {"source": str(job.rel), "model": VLM_MODEL,
                              "count": len(captions), "captions": captions})
        if len(captions) % 10 == 0:
            log(f"    captioned {len(captions)}/{len(entries)}")

    write_json(out_path, {"source": str(job.rel), "model": VLM_MODEL,
                          "count": len(captions), "captions": captions})


# ------------------------------------------------------------------------------ driver

STAGES = [
    ("probe", stage_probe),
    ("audio", stage_audio),
    ("transcribe", stage_transcribe),
    ("moments", stage_moments),
    ("keyframes", stage_keyframes),
]
CAPTION_STAGE = ("caption", stage_caption)


def write_manifest(jobs: list[Job], stage_names: list[str]) -> tuple[int, int]:
    """Aggregate every completed video into a top-level index + training dataset.

    index.json    one record per video: identity, status, counts
    dataset.jsonl one row per screenshot: image path + label + narration, the
                  multimodal samples a downstream model trains on
    """
    index = []
    rows = 0
    dataset_path = OUT_ROOT / "dataset.jsonl"
    tmp = dataset_path.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as ds:
        for job in jobs:
            meta = read_json(job.out / "meta.json")
            state = read_json(job.state_path) or {"stages": {}}
            stages = state.get("stages", {})
            km = read_json(job.out / "keyframes.json")
            mo = read_json(job.out / "moments.json")
            captions = {c["index"]: c["caption"]
                        for c in (read_json(job.out / "captions.json") or {}).get("captions", [])}
            record = {
                "id": job.video_id,
                "category": job.category,
                "volume": job.volume,
                "title": job.title,
                "source": str(job.rel),
                "duration_hms": (meta or {}).get("duration_hms"),
                "dir": job.video_id,
                "status": {n: stages.get(n, {}).get("status", "pending") for n in stage_names},
                "moment_count": (mo or {}).get("count", 0),
                "keyframe_count": (km or {}).get("count", 0),
            }
            index.append(record)
            if not km:
                continue
            for e in km["keyframes"]:
                ds.write(json.dumps({
                    "video_id": job.video_id,
                    "category": job.category,
                    "title": job.title,
                    "t": e["t"],
                    "hms": e["hms"],
                    "image": f"{job.video_id}/{e['file']}",
                    "source": e["source"],
                    "label": e["label"],
                    "why": e["why"],
                    "narration": e["narration"],
                    "caption": captions.get(e["index"], ""),
                }, ensure_ascii=False) + "\n")
                rows += 1
    os.replace(tmp, dataset_path)

    write_json(OUT_ROOT / "index.json", {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "video_count": len(index),
        "screenshot_count": rows,
        "categories": sorted({r["category"] for r in index}),
        "videos": index,
    })
    return len(index), rows


def process(job: Job, stages, force: set[str]) -> bool:
    job.out.mkdir(parents=True, exist_ok=True)
    state = State(job)

    if state.source_changed():
        log(f"    source file changed since last run; redoing all stages")
        state.reset_all()

    for name in force:
        if name in state.data["stages"]:
            state.data["stages"].pop(name)
    if force:
        state.data["signature"] = job.signature()
        write_json(state.path, state.data)

    for name, fn in stages:
        status = state.status(name)
        if status == "done":
            continue
        if status == "running":
            log(f"    {name}: already running in another process, skipping video")
            return False
        if status == "failed" and state.attempts(name) >= MAX_ATTEMPTS:
            log(f"    {name}: failed {state.attempts(name)}x, giving up on this video")
            return False

        started = time.time()
        log(f"    {name}: starting")
        try:
            with Heartbeat(state, name):
                fn(job)
        except Exception as exc:  # noqa: BLE001 - one bad video must not stop the run
            log(f"    {name}: FAILED ({type(exc).__name__}: {str(exc)[:200]})")
            return False
        log(f"    {name}: done in {human(time.time() - started)}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="substring filter on the video path")
    ap.add_argument("--caption", action="store_true",
                    help="also run the VLM captioning stage (slow)")
    ap.add_argument("--force", action="append", default=[],
                    help="stage name to redo even if already done (repeatable)")
    ap.add_argument("--list", action="store_true", help="show videos and status, then exit")
    args = ap.parse_args()

    SCRATCH.mkdir(parents=True, exist_ok=True)
    jobs = discover_jobs()
    if args.only:
        needle = args.only.lower()
        jobs = [j for j in jobs
                if needle in str(j.rel).lower() or needle in j.video_id.lower()]
    if not jobs:
        log("no videos found")
        return 1

    stages = list(STAGES) + ([CAPTION_STAGE] if args.caption else [])
    stage_names = [n for n, _ in stages]

    if args.list:
        for job in jobs:
            state = State(job)
            marks = " ".join(
                f"{n}={state.data['stages'].get(n, {}).get('status', '-')}" for n in stage_names
            )
            print(f"{job.rel}\n    {marks}")
        return 0

    # total video seconds drives the ETA
    totals = {}
    for job in jobs:
        meta = read_json(job.out / "meta.json")
        if meta:
            totals[job.rel] = meta["duration_sec"]
        else:
            proc = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(job.src)])
            try:
                totals[job.rel] = float(proc.stdout.decode().strip())
            except ValueError:
                totals[job.rel] = 0.0
    grand_total = sum(totals.values()) or 1.0

    log(f"{len(jobs)} video(s), {human(grand_total)} of footage")
    log(f"stages: {', '.join(stage_names)}")
    log(f"whisper={WHISPER_MODEL}  llm={LLM_MODEL}" + (f"  vlm={VLM_MODEL}" if args.caption else ""))

    run_start = time.time()
    completed_seconds = 0.0
    ok = failed = 0

    for i, job in enumerate(jobs, 1):
        elapsed = time.time() - run_start
        pct = completed_seconds / grand_total
        eta = (elapsed / pct - elapsed) if pct > 0.02 else 0
        log("")
        log(f"[{i}/{len(jobs)}] {job.rel}  ({human(totals[job.rel])} of video)")
        log(f"    progress {pct * 100:5.1f}%  elapsed {human(elapsed)}"
            + (f"  eta {human(eta)}" if eta else ""))

        if process(job, stages, set(args.force)):
            ok += 1
        else:
            failed += 1
        completed_seconds += totals[job.rel]
        # refresh the manifest after every video so it is usable mid-run
        write_manifest(jobs, stage_names)

    vids, shots = write_manifest(jobs, stage_names)
    log("")
    log(f"finished: {ok} ok, {failed} incomplete, in {human(time.time() - run_start)}")
    log(f"output: {OUT_ROOT}")
    log(f"manifest: index.json ({vids} videos), dataset.jsonl ({shots} screenshots)")
    if failed:
        log("rerun the same command to retry incomplete videos")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
