"""Transcribe the corpus and pull aligned keyframes from it — Phase 1 of stoic_derived.

One directory of derived artefacts per source video, under edu/derived/<video_id>/. Every
stage is idempotent and resumable at the unit-of-work level (segment, frame): a rerun skips
completed work, and a stage that died mid-flight (crash, kill, power loss) is detected via a
stale heartbeat and redone. This is the simplified successor to the retired edu/pipeline/ — no
LLM "moments" stage, no VLM captioning, no OCR: transcribe + deterministic keyframes only.

Stages
  probe       meta.json                        duration / resolution, via ffprobe
  audio       .scratch/audio/<id>.wav           16 kHz mono PCM, via ffmpeg
  transcribe  transcript.{json,md,txt}          faster-whisper large-v3-turbo (CPU, int8)
  keyframes   keyframes/*.jpg, keyframes.json   pixel-drift + gap-fill, no model

Keyframes are picked by piping the video through ffmpeg at 1 fps, greyscale, 160x90, and
keeping a frame whenever it has drifted from the last kept frame by more than DRIFT_THRESH,
never closer than MIN_GAP apart, with a gap-filler forced in whenever MAX_GAP would otherwise
pass uncovered. These are continuous screencasts with no scene cuts, so classic scene-detection
(scenedetect) finds nothing — this is a deliberate departure from it, not an oversight. Each
kept frame is captured NARRATION_LAG seconds after its cue, so the chart has caught up to the
words describing it.

Usage
  .venv/bin/python scripts/build_corpus.py                 process everything not already done
  .venv/bin/python scripts/build_corpus.py --list           status table, does no work
  .venv/bin/python scripts/build_corpus.py --only marker      filter by path or id substring
  .venv/bin/python scripts/build_corpus.py --force keyframes  redo that stage (repeatable)

A plain run (no --only) only ever touches videos with pending work: a video whose every stage
is already "done" AND whose declared output files are present on disk is left alone, so the
five already-transcribed videos are never rewritten. --force only clears stages on videos
already in scope for the run; naming a stage does not by itself pull a finished video back in
scope — pair --force with --only to redo a stage on a specific finished video on purpose.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# --------------------------------------------------------------------------------- paths

REPO_ROOT = Path(__file__).resolve().parents[1]
EDU_ROOT = REPO_ROOT / "edu"
OUT_ROOT = EDU_ROOT / "derived"
SCRATCH = REPO_ROOT / ".scratch"
AUDIO_DIR = SCRATCH / "audio"
WHISPER_CACHE = REPO_ROOT / ".artifacts" / "models" / "faster-whisper"

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".m4v", ".webm"}
WHISPER_MODEL = "large-v3-turbo"

# Keyframe selection. Tuned to over-capture rather than under-capture.
SAMPLE_FPS = 1            # transcript/visual analysis granularity
HASH_W, HASH_H = 160, 90  # downscaled grey frame used for drift detection
DRIFT_THRESH = 2.5        # mean abs pixel delta from the last KEPT frame
MIN_GAP = 6.0             # never two screenshots closer than this
MAX_GAP = 45.0            # never leave a stretch longer than this uncovered
NARRATION_LAG = 3.0       # grab the frame N seconds after the words, not on them
JPEG_QUALITY = 3          # ffmpeg -q:v, 2=best 31=worst

STALL_SECONDS = 900        # a "running" stage with a heartbeat older than this is dead
MAX_ATTEMPTS = 3
HEARTBEAT_INTERVAL = 15.0

# Boilerplate the channel glues onto every filename; stripped when deriving id/title.
BOILERPLATE_PHRASES = {"stoic traders", "stoic trader concepts"}
RESOLUTION_RE = re.compile(r"\b\d{3,4}p\b|\b(?:full ?hd|hd|4k)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------------- utils


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


def clean_title(stem: str) -> str:
    """Recover the human title from a source filename.

    Channels append a trailing " - Series/Site Name" (dash-delimited) and/or " · Stoic
    Traders" (middle-dot-delimited) suffix. Only the LAST dash-delimited part is dropped (so
    "Scalping Example - Live Trading Session - Stoic Edge System" keeps "Live Trading
    Session", which is real title, and only sheds the trailing site name); only a trailing
    dot-delimited part that is exactly known boilerplate is dropped (so "Stoic Traders Marker
    Study", which has no "·" at all, keeps its leading "Stoic Traders" — that's the title, not
    boilerplate).
    """
    parts = stem.split(" - ")
    title = " - ".join(parts[:-1]) if len(parts) > 1 else stem

    dot_parts = title.split(" · ")
    if len(dot_parts) > 1 and dot_parts[-1].strip().lower() in BOILERPLATE_PHRASES:
        title = " · ".join(dot_parts[:-1])

    # Filename-style separators: collapse "-" to space only when the stem used it as the
    # ONLY word separator (no real spaces present) -- otherwise spaces already do the
    # separating and a bare hyphen is meaningful punctuation (e.g. "1-2-3").
    title = title.replace("_", " ") if " " in title else title.replace("_", " ").replace("-", " ")

    title = RESOLUTION_RE.sub("", title)
    return re.sub(r"\s+", " ", title).strip()


def slugify(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", text.lower())
    return text.strip("_")


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_json(path: Path, obj) -> None:
    write_atomic_text(path, json.dumps(obj, indent=2, ensure_ascii=False))


def read_jsonl(path: Path) -> list[dict]:
    """Read a checkpoint jsonl, tolerating a final line truncated by a kill mid-write."""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    rows = []
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if i != len(lines) - 1:
                raise
            log(f"    ! dropping truncated last line of {path.name}")
    return rows


def read_wav_mono16(path: Path) -> tuple[np.ndarray, int]:
    """Read a 16-bit PCM mono wav into a float32 array normalized to [-1, 1]."""
    with wave.open(str(path), "rb") as wf:
        if wf.getsampwidth() != 2 or wf.getnchannels() != 1:
            raise ValueError(f"{path}: expected mono 16-bit PCM wav")
        rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return samples, rate


def narration_for(segments: list[dict], start: float, end: float) -> str:
    return " ".join(s["text"] for s in segments if s["end"] > start and s["start"] < end).strip()


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just not ours
    except OSError:
        return False
    return True


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True)


# ----------------------------------------------------------------------------------- jobs


@dataclass(frozen=True)
class Job:
    src: Path       # absolute path to the source video
    rel: Path       # path relative to edu/
    video_id: str
    category: str
    volume: str | None
    title: str

    @property
    def out(self) -> Path:
        return OUT_ROOT / self.video_id

    @property
    def state_path(self) -> Path:
        return self.out / "state.json"

    @property
    def audio_path(self) -> Path:
        return AUDIO_DIR / f"{self.video_id}.wav"

    def signature(self) -> str:
        st = self.src.stat()
        return f"{st.st_size}-{int(st.st_mtime)}"


def discover_jobs() -> list[Job]:
    jobs = []
    for path in sorted(EDU_ROOT.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in VIDEO_EXTS:
            continue
        if OUT_ROOT in path.parents:
            continue
        rel = path.relative_to(EDU_ROOT)
        title = clean_title(path.stem)
        jobs.append(
            Job(
                src=path,
                rel=rel,
                video_id=f"concept_{slugify(title)}",
                category="concept",
                volume=None,
                title=title,
            )
        )
    return jobs


# --------------------------------------------------------------------------- state engine


class State:
    """Per-video stage tracker with heartbeat-based stall recovery."""

    def __init__(self, job: Job):
        self.job = job
        self.path = job.state_path
        self.lock = threading.Lock()
        self.data = read_json(self.path) or {}
        self.data.setdefault("source", job.rel.as_posix())
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

    def clear_stage(self, name: str) -> None:
        with self.lock:
            self.data["stages"].pop(name, None)
            self._flush()

    def peek_status(self, name: str) -> str:
        """Resolve a stage's status without persisting stall recovery -- safe for --list."""
        entry = self.data["stages"].get(name)
        if not entry:
            return "pending"
        if entry.get("status") != "running":
            return entry.get("status", "pending")
        pid, beat = entry.get("pid", -1), entry.get("heartbeat", 0)
        if pid == os.getpid():
            return "running"
        if pid_alive(pid) and (time.time() - beat) < STALL_SECONDS:
            return "running"
        return "pending"

    def status(self, name: str) -> str:
        """Resolve a stage's status, persisting stall recovery when it fires."""
        resolved = self.peek_status(name)
        entry = self.data["stages"].get(name)
        if entry and entry.get("status") == "running" and resolved == "pending":
            log(f"    ! stalled '{name}' (pid {entry.get('pid')} dead or heartbeat stale); redoing")
            with self.lock:
                entry["status"] = "pending"
                self._flush()
        return resolved

    def attempts(self, name: str) -> int:
        return self.data["stages"].get(name, {}).get("attempts", 0)

    def mark(self, name: str, status: str, **extra) -> None:
        with self.lock:
            entry = self.data["stages"].setdefault(name, {})
            entry.update(status=status, ts=time.time(), **extra)
            self._flush()

    def beat(self, name: str) -> None:
        with self.lock:
            entry = self.data["stages"].get(name)
            if entry and entry.get("status") == "running":
                entry["heartbeat"] = time.time()
                self._flush()


class Heartbeat:
    """Keeps a running stage's heartbeat fresh so a kill is distinguishable from a hang."""

    def __init__(self, state: State, name: str, interval: float = HEARTBEAT_INTERVAL):
        self.state, self.name, self.interval = state, name, interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> Heartbeat:
        self.state.mark(
            self.name,
            "running",
            pid=os.getpid(),
            heartbeat=time.time(),
            attempts=self.state.attempts(self.name) + 1,
        )

        def loop() -> None:
            while not self._stop.wait(self.interval):
                self.state.beat(self.name)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if exc_type is None:
            self.state.mark(self.name, "done")
        else:
            self.state.mark(self.name, "failed", error=f"{exc_type.__name__}: {exc}"[:400])
        return False


def outputs_present(job: Job, name: str, state: State) -> bool:
    """Gate on disk state, not just the status flag: a 'done' stage whose declared outputs
    were deleted must be re-entered.

    The one exception is "audio": its wav is scratch by design (`.scratch/`, gitignored, does
    not travel between machines -- see CLAUDE.md), disposable the moment transcribe has
    consumed it. Once transcribe is done, a missing wav is expected housekeeping, not
    staleness, so it must not re-trigger audio extraction (and, on the five pre-existing
    videos, a spurious rewrite of their state.json).
    """
    if name == "probe":
        return (job.out / "meta.json").exists()
    if name == "audio":
        if state.peek_status("transcribe") == "done" and outputs_present(job, "transcribe", state):
            return True
        return job.audio_path.exists()
    if name == "transcribe":
        return all(
            (job.out / n).exists() for n in ("transcript.json", "transcript.md", "transcript.txt")
        )
    if name == "keyframes":
        data = read_json(job.out / "keyframes.json")
        if not data:
            return False
        return all((job.out / e["file"]).exists() for e in data.get("keyframes", []))
    raise ValueError(f"unknown stage {name!r}")


# ---------------------------------------------------------------------------------- stages


def stage_probe(job: Job) -> None:
    proc = run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate",
            "-show_entries", "format=duration",
            "-of", "json", str(job.src),
        ]
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {proc.stderr.decode(errors='replace')[:300]}")
    info = json.loads(proc.stdout)
    stream = (info.get("streams") or [{}])[0]
    duration = float(info["format"]["duration"])
    write_json(
        job.out / "meta.json",
        {
            "id": job.video_id,
            "category": job.category,
            "volume": job.volume,
            "title": job.title,
            "source": job.rel.as_posix(),
            "duration_sec": duration,
            "duration_hms": hhmmss(duration),
            "width": stream.get("width"),
            "height": stream.get("height"),
            "fps": stream.get("r_frame_rate"),
        },
    )


def stage_audio(job: Job) -> None:
    job.audio_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = job.audio_path.with_suffix(job.audio_path.suffix + ".tmp")
    proc = run(
        [
            "ffmpeg", "-v", "error", "-y", "-i", str(job.src),
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
            "-f", "wav", str(tmp),
        ]
    )
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"audio extract failed: {proc.stderr.decode(errors='replace')[:300]}")
    os.replace(tmp, job.audio_path)


_MODEL = None


def get_model():
    """Load the whisper model once per run (not once per video), lazily on first use."""
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel

        WHISPER_CACHE.mkdir(parents=True, exist_ok=True)
        log(f"    loading whisper model {WHISPER_MODEL!r} (cpu, int8) ...")
        started = time.time()
        _MODEL = WhisperModel(
            WHISPER_MODEL, device="cpu", compute_type="int8", download_root=str(WHISPER_CACHE)
        )
        log(f"    model loaded in {human(time.time() - started)}")
    return _MODEL


def stage_transcribe(job: Job) -> None:
    meta = read_json(job.out / "meta.json")
    duration = meta["duration_sec"]

    partial_path = job.out / "transcript.partial.jsonl"
    done_segments = read_jsonl(partial_path)
    resume_at = done_segments[-1]["end"] if done_segments else 0.0
    if done_segments:
        log(
            f"    transcribe: resuming from partial "
            f"({len(done_segments)} segments, resume_at={hhmmss(resume_at)})"
        )

    samples, rate = read_wav_mono16(job.audio_path)
    audio_slice = samples[round(resume_at * rate) :]

    new_segments: list[dict] = []
    if audio_slice.size > 0:
        model = get_model()
        seg_iter, _info = model.transcribe(
            audio_slice,
            language="en",
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        stage_started = last_log = time.time()
        with open(partial_path, "a", encoding="utf-8") as fh:
            for seg in seg_iter:
                text = seg.text.strip()
                if not text:
                    continue
                rec = {
                    "start": round(float(seg.start) + resume_at, 2),
                    "end": round(float(seg.end) + resume_at, 2),
                    "text": text,
                }
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                new_segments.append(rec)

                now = time.time()
                if now - last_log > 10:
                    processed = rec["end"] - resume_at  # this run's work only
                    elapsed = now - stage_started
                    rate_sps = processed / elapsed if elapsed > 0 else 0.0
                    eta = (duration - rec["end"]) / rate_sps if rate_sps > 0 else 0.0
                    log(
                        f"    transcribe: {len(done_segments) + len(new_segments)} segments, "
                        f"at {hhmmss(rec['end'])}/{hhmmss(duration)}  elapsed {human(elapsed)}  "
                        f"eta {human(eta)}"
                    )
                    last_log = now

    all_segments = done_segments + new_segments
    write_json(
        job.out / "transcript.json",
        {
            "source": job.rel.as_posix(),
            "language": "en",
            "model": WHISPER_MODEL,
            "segments": all_segments,
        },
    )

    lines = [f"# {job.title}", "", f"_Source: `{job.rel.as_posix()}`_", ""]
    lines += [f"**[{hhmmss(s['start'])}]** {s['text']}" for s in all_segments]
    write_atomic_text(job.out / "transcript.md", "\n\n".join(lines) + "\n")

    plain = " ".join(s["text"] for s in all_segments)
    write_atomic_text(job.out / "transcript.txt", plain + "\n")

    partial_path.unlink(missing_ok=True)
    log(f"    transcribe: {len(all_segments)} segments total")


# ---- keyframes --------------------------------------------------------------------------


def sample_grey(job: Job) -> np.ndarray:
    """Decode the whole video once at SAMPLE_FPS into small greyscale frames."""
    proc = run(
        [
            "ffmpeg", "-v", "error", "-i", str(job.src),
            "-vf", f"fps={SAMPLE_FPS},scale={HASH_W}:{HASH_H},format=gray",
            "-f", "rawvideo", "-",
        ]
    )
    if proc.returncode != 0:
        raise RuntimeError(f"frame sampling failed: {proc.stderr.decode(errors='replace')[:300]}")
    buf = np.frombuffer(proc.stdout, dtype=np.uint8)
    usable = (len(buf) // (HASH_W * HASH_H)) * HASH_W * HASH_H
    return buf[:usable].reshape(-1, HASH_H, HASH_W).astype(np.float32)


def select_keyframe_seconds(frames: np.ndarray, duration: float) -> list[tuple[float, str]]:
    """Deterministic (t, source) pairs on the 1fps detection grid: pixel-drift picks, plus
    gap-fill so no MAX_GAP-wide stretch is left uncovered. `source` is "drift" or "gap"."""
    if len(frames) == 0:
        return [(0.0, "drift")]

    kept = [0]
    anchor = frames[0]
    for i in range(1, len(frames)):
        if i - kept[-1] < MIN_GAP:
            continue
        if float(np.abs(frames[i] - anchor).mean()) > DRIFT_THRESH:
            kept.append(i)
            anchor = frames[i]

    candidates: dict[int, str] = dict.fromkeys(kept, "drift")

    chosen = sorted(candidates)
    filled: list[int] = []
    cursor = 0.0
    for sec in [*chosen, int(duration)]:
        while sec - cursor > MAX_GAP:
            cursor += MAX_GAP
            filled.append(int(cursor))
        cursor = sec
    for sec in filled:
        candidates.setdefault(sec, "gap")

    ceiling = max(0.0, duration - 1)
    selected: list[tuple[float, str]] = []
    for sec in sorted(candidates):
        t = float(min(sec, ceiling))
        if selected and t - selected[-1][0] < MIN_GAP:
            continue
        selected.append((t, candidates[sec]))
    return selected


def extract_frame(src: Path, t: float, out_path: Path) -> None:
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    proc = run(
        [
            "ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(src),
            "-frames:v", "1", "-q:v", str(JPEG_QUALITY), "-f", "image2", str(tmp),
        ]
    )
    if proc.returncode != 0 or not tmp.exists():
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"frame extract at {t:.2f}s failed: {proc.stderr.decode(errors='replace')[:300]}"
        )
    os.replace(tmp, out_path)


def stage_keyframes(job: Job) -> None:
    meta = read_json(job.out / "meta.json")
    duration = meta["duration_sec"]
    segments = read_json(job.out / "transcript.json")["segments"]

    frames = sample_grey(job)
    selected = select_keyframe_seconds(frames, duration)
    if not selected:
        raise RuntimeError("no keyframes selected")

    frames_dir = job.out / "keyframes"
    frames_dir.mkdir(parents=True, exist_ok=True)

    capture_ceiling = max(0.0, duration - 0.5)
    entries = []
    extracted = skipped = 0
    stage_started = time.time()
    for idx, (t, source) in enumerate(selected):
        filename = f"{idx:04d}_{fname_ts(t)}.jpg"
        out_path = frames_dir / filename
        capture_t = min(t + NARRATION_LAG, capture_ceiling)

        if out_path.exists():
            skipped += 1
        else:
            extract_frame(job.src, capture_t, out_path)
            extracted += 1
            if extracted % 10 == 0:
                elapsed = time.time() - stage_started
                rate = extracted / elapsed if elapsed > 0 else 0.0
                eta = (len(selected) - idx - 1) / rate if rate > 0 else 0.0
                log(
                    f"    keyframes: {idx + 1}/{len(selected)} "
                    f"({extracted} extracted, {skipped} already present)  "
                    f"elapsed {human(elapsed)}  eta {human(eta)}"
                )

        next_t = selected[idx + 1][0] if idx + 1 < len(selected) else duration
        entries.append(
            {
                "index": idx,
                "t": round(capture_t),
                "hms": hhmmss(capture_t),
                "file": f"keyframes/{filename}",
                "source": source,
                "label": "",
                "why": "",
                "narration": narration_for(segments, t - NARRATION_LAG - 2, next_t),
            }
        )

    write_json(
        job.out / "keyframes.json",
        {
            "source": job.rel.as_posix(),
            "count": len(entries),
            "by_source": {
                s: sum(1 for e in entries if e["source"] == s) for s in ("drift", "gap")
            },
            "keyframes": entries,
        },
    )
    log(
        f"    keyframes: {len(entries)} total "
        f"(drift={sum(1 for e in entries if e['source'] == 'drift')}, "
        f"gap={sum(1 for e in entries if e['source'] == 'gap')}, {skipped} already present)"
    )


STAGES: list[tuple[str, Callable[[Job], None]]] = [
    ("probe", stage_probe),
    ("audio", stage_audio),
    ("transcribe", stage_transcribe),
    ("keyframes", stage_keyframes),
]
STAGE_NAMES = [name for name, _ in STAGES]


# --------------------------------------------------------------------------------- driver


def job_fully_done(job: Job) -> bool:
    state = State(job)
    return all(
        state.status(name) == "done" and outputs_present(job, name, state) for name in STAGE_NAMES
    )


def process(job: Job, all_jobs: list[Job], force: set[str]) -> bool:
    """Run every pending stage for one video. Returns True iff the video ends fully done."""
    job.out.mkdir(parents=True, exist_ok=True)
    state = State(job)

    if state.source_changed():
        log("    source file changed since last run; redoing all stages")
        state.reset_all()

    for name in force:
        state.clear_stage(name)

    for name, fn in STAGES:
        status = state.status(name)
        if status == "done" and not outputs_present(job, name, state):
            log(f"    {name}: marked done but outputs are missing; re-entering")
            status = "pending"
        if status == "done":
            log(f"    {name}: already done, skipping")
            continue
        if status == "running":
            log(f"    {name}: already running in another process; skipping video")
            return False
        if status == "failed" and state.attempts(name) >= MAX_ATTEMPTS:
            log(f"    {name}: failed {state.attempts(name)}x; giving up on this video")
            return False

        started = time.time()
        log(f"    {name}: starting")
        try:
            with Heartbeat(state, name):
                fn(job)
        except Exception as exc:
            log(f"    {name}: FAILED ({type(exc).__name__}: {str(exc)[:200]})")
            write_manifest(all_jobs)
            return False
        log(f"    {name}: done in {human(time.time() - started)}")
        write_manifest(all_jobs)

    return True


def manifest_record(job: Job) -> dict:
    meta = read_json(job.out / "meta.json")
    state_data = read_json(job.state_path) or {"stages": {}}
    raw_stages = state_data["stages"]
    stages = {name: raw_stages.get(name, {}).get("status", "pending") for name in STAGE_NAMES}
    transcript = read_json(job.out / "transcript.json")
    keyframes = read_json(job.out / "keyframes.json")

    if all(s == "done" for s in stages.values()):
        overall = "done"
    elif any(s == "failed" for s in stages.values()):
        overall = "failed"
    elif any(s != "pending" for s in stages.values()):
        overall = "in_progress"
    else:
        overall = "pending"

    return {
        "id": job.video_id,
        "source": job.rel.as_posix(),
        "title": job.title,
        "duration_sec": (meta or {}).get("duration_sec"),
        "status": overall,
        "stages": stages,
        "transcript_segments": len((transcript or {}).get("segments", [])),
        "keyframes": (keyframes or {}).get("count", 0),
    }


def write_manifest(all_jobs: list[Job]) -> None:
    write_json(
        OUT_ROOT / "manifest.json",
        {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "pipeline": "build_corpus",
            "videos": [manifest_record(j) for j in sorted(all_jobs, key=lambda j: j.video_id)],
        },
    )


def estimate_duration(job: Job) -> float:
    meta = read_json(job.out / "meta.json")
    if meta and "duration_sec" in meta:
        return float(meta["duration_sec"])
    proc = run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", str(job.src),
        ]
    )
    try:
        return float(proc.stdout.decode().strip())
    except ValueError:
        return 0.0


def print_status_table(jobs: list[Job]) -> None:
    width = max((len(j.video_id) for j in jobs), default=8)
    header = f"{'video_id':<{width}}  " + "  ".join(f"{n:<10}" for n in STAGE_NAMES)
    print(header)
    print("-" * len(header))
    for job in jobs:
        state = State(job)
        marks = "  ".join(f"{state.peek_status(n):<10}" for n in STAGE_NAMES)
        print(f"{job.video_id:<{width}}  {marks}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--only", help="substring filter on the source path or video id")
    ap.add_argument(
        "--force",
        action="append",
        default=[],
        choices=STAGE_NAMES,
        help="stage to redo even if marked done (repeatable)",
    )
    ap.add_argument("--list", action="store_true", help="show status table and exit; does no work")
    args = ap.parse_args()

    SCRATCH.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    all_jobs = discover_jobs()
    if not all_jobs:
        log("no videos found under edu/")
        return 1

    jobs = all_jobs
    if args.only:
        needle = args.only.lower()
        jobs = [
            j
            for j in all_jobs
            if needle in j.rel.as_posix().lower() or needle in j.video_id.lower()
        ]
        if not jobs:
            log(f"no videos match --only {args.only!r}")
            return 1

    if args.list:
        print_status_table(jobs)
        return 0

    force = set(args.force)
    # --only is an explicit target list, done or not; otherwise only videos with pending work
    # are touched, so a bare run (or a bare --force) never rewrites an already-done video.
    pending_jobs = jobs if args.only else [j for j in jobs if not job_fully_done(j)]

    if not pending_jobs:
        log(f"{len(jobs)} video(s) matched, all already done")
        write_manifest(all_jobs)
        return 0

    totals = {j.video_id: estimate_duration(j) for j in pending_jobs}
    grand_total = sum(totals.values()) or 1.0
    log(
        f"{len(pending_jobs)}/{len(jobs)} video(s) with pending work, "
        f"{human(grand_total)} of footage"
    )
    log(f"stages: {', '.join(STAGE_NAMES)}  whisper={WHISPER_MODEL}")

    run_start = time.time()
    completed_seconds = 0.0  # this run's completed work only
    ok = failed = 0

    for i, job in enumerate(pending_jobs, 1):
        elapsed = time.time() - run_start
        pct = completed_seconds / grand_total
        eta = (elapsed / pct - elapsed) if pct > 0.02 else 0.0
        log("")
        log(f"[{i}/{len(pending_jobs)}] {job.rel.as_posix()}  ({human(totals[job.video_id])})")
        eta_part = f"  eta {human(eta)}" if eta else ""
        log(f"    progress {pct * 100:5.1f}%  elapsed {human(elapsed)}" + eta_part)

        if process(job, all_jobs, force):
            ok += 1
        else:
            failed += 1
        completed_seconds += totals[job.video_id]

    write_manifest(all_jobs)
    log("")
    log(f"finished: {ok} ok, {failed} incomplete, in {human(time.time() - run_start)}")
    log(f"output: {OUT_ROOT}")
    if failed:
        log("rerun the same command to retry incomplete videos")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
