"""Deterministic, model-free scoring for the offline research-assistant SLM.

Purpose guardrail: this evaluates an OFFLINE research assistant that
proposes cited rule candidates for human review; its output never touches
any live trading path.

Two modes:
  (a) `--predictions FILE`: score an existing predictions JSONL
      ([{"meta":..., "task":..., "prediction": str}, ...]).
  (b) default: generate predictions from a checkpoint over eval.jsonl
      (deterministic generation: do_sample=False, temperature=None, fixed
      max_new_tokens), then score them.

Scoring is pure Python (stdlib `re`/`difflib`/`json`) and every function
below `main()` is importable without torch, so predictions can be scored
in CI with no GPU. Only mode (b) touches a model, via `infer.run_batch`,
imported lazily inside `generate_predictions`.

Optional `--run-dir DIR`: when given, main() writes a tailable
`<run_dir>/evaluate.log` and `<run_dir>/progress.json` (see progress.py) --
corpus size, prediction source, per-record generation progress in mode (b),
and the headline metrics. With no `--run-dir`, behaviour is unchanged.

Metrics:
  - citation_fidelity: fraction of (non-conflict_check) predictions whose
    trailing "Citation: <video_id> <hms>" line names a record that exists
    in the source corpus, and whose body has sufficient token overlap with
    that record's narration or why (default threshold 0.3).
  - conflict_handling: fraction of conflict_check predictions that cite at
    least two distinct video_ids and contain an explicit ambiguity/conflict
    marker word.
Both are reported overall, per-task, and per-meta.category; a held-out vs
train comparison is included when both prediction sets are supplied.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from stoic_training import progress

DEFAULT_OVERLAP_THRESHOLD = 0.3
DEFAULT_MAX_NEW_TOKENS = 256
CONFLICT_TASK = "conflict_check"

# src/stoic_training/evaluate.py -> stoic_training -> src -> win_cuda -> training -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CORPUS_PATH = _REPO_ROOT / "edu" / "derived" / "dataset.jsonl"

CONFLICT_MARKERS = frozenset(
    {
        "conflict",
        "conflicting",
        "ambiguous",
        "ambiguity",
        "contradiction",
        "contradicts",
        "contradictory",
        "unresolved",
    }
)

_CITATION_RE = re.compile(r"Citation:\s*(\S+)\s+(\d{2}:\d{2}:\d{2})")
_TRAILING_CITATION_RE = re.compile(r"^Citation:\s*(\S+)\s+(\d{2}:\d{2}:\d{2})\s*$")
_WORD_RE = re.compile(r"[a-z0-9]+")


class EvaluationError(ValueError):
    """Raised when predictions or the source corpus cannot be scored."""


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def token_overlap_ratio(a: str, b: str) -> float:
    """Deterministic token-set overlap ratio in [0, 1]; 0.0 if either side is empty."""
    tokens_a = sorted(set(_tokenize(a)))
    tokens_b = sorted(set(_tokenize(b)))
    if not tokens_a or not tokens_b:
        return 0.0
    return SequenceMatcher(None, tokens_a, tokens_b).ratio()


@dataclass(frozen=True, slots=True)
class CorpusRecord:
    video_id: str
    hms: str
    narration: str
    why: str
    category: str
    label: str


CorpusIndex = dict[tuple[str, str], CorpusRecord]


def load_corpus(path: str | Path) -> CorpusIndex:
    """Load the source corpus (edu/derived/dataset.jsonl) keyed by (video_id, hms)."""
    index: CorpusIndex = {}
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvaluationError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise EvaluationError(f"{path}:{line_number}: record must be an object")
            video_id = payload.get("video_id")
            hms = payload.get("hms")
            if not isinstance(video_id, str) or not video_id or not isinstance(hms, str) or not hms:
                raise EvaluationError(f"{path}:{line_number}: missing video_id/hms")
            index[(video_id, hms)] = CorpusRecord(
                video_id=video_id,
                hms=hms,
                narration=payload.get("narration") or "",
                why=payload.get("why") or "",
                category=payload.get("category") or "",
                label=payload.get("label") or "",
            )
    return index


def extract_citations(text: str) -> list[tuple[str, str]]:
    return list(_CITATION_RE.findall(text))


def trailing_citation(text: str) -> tuple[str, str] | None:
    """Return the (video_id, hms) on the last non-blank line, if it is a citation line."""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return None
    match = _TRAILING_CITATION_RE.match(lines[-1])
    if not match:
        return None
    return match.group(1), match.group(2)


def citation_body(text: str) -> str:
    """The prediction text before its trailing citation line."""
    lines = [line for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return ""
    if _TRAILING_CITATION_RE.match(lines[-1].strip()):
        lines = lines[:-1]
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class PredictionScore:
    passed: bool
    reason: str


def score_citation_fidelity(
    prediction_text: str,
    corpus: CorpusIndex,
    *,
    overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD,
) -> PredictionScore:
    citation = trailing_citation(prediction_text)
    if citation is None:
        return PredictionScore(False, "no trailing citation")
    record = corpus.get(citation)
    if record is None:
        return PredictionScore(False, f"citation not found in corpus: {citation[0]} {citation[1]}")
    body = citation_body(prediction_text)
    overlap = max(
        token_overlap_ratio(body, record.narration),
        token_overlap_ratio(body, record.why),
    )
    if overlap < overlap_threshold:
        return PredictionScore(False, f"citation overlap {overlap:.3f} below threshold")
    return PredictionScore(True, "ok")


def score_conflict_handling(prediction_text: str) -> PredictionScore:
    citations = extract_citations(prediction_text)
    distinct_video_ids = {video_id for video_id, _ in citations}
    if len(distinct_video_ids) < 2:
        return PredictionScore(False, "fewer than two cited video_ids")
    tokens = set(_tokenize(prediction_text))
    if not tokens & CONFLICT_MARKERS:
        return PredictionScore(False, "no ambiguity/conflict marker")
    return PredictionScore(True, "ok")


def score_prediction(
    record: Mapping[str, Any],
    corpus: CorpusIndex,
    *,
    overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD,
) -> PredictionScore:
    task = record.get("task")
    prediction_text = record.get("prediction")
    if not isinstance(task, str) or not task:
        raise EvaluationError("prediction record missing task")
    if not isinstance(prediction_text, str):
        raise EvaluationError("prediction record missing prediction text")
    if task == CONFLICT_TASK:
        return score_conflict_handling(prediction_text)
    return score_citation_fidelity(prediction_text, corpus, overlap_threshold=overlap_threshold)


def _rate(values: list[bool]) -> float | None:
    return (sum(values) / len(values)) if values else None


def score_predictions(
    predictions: Sequence[Mapping[str, Any]],
    corpus: CorpusIndex,
    *,
    overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD,
) -> dict[str, Any]:
    """Score a batch of predictions; returns overall/per-task/per-category metrics."""
    per_task: dict[str, list[bool]] = defaultdict(list)
    per_category: dict[str, list[bool]] = defaultdict(list)
    citation_results: list[bool] = []
    conflict_results: list[bool] = []
    details: list[dict[str, Any]] = []

    for record in predictions:
        result = score_prediction(record, corpus, overlap_threshold=overlap_threshold)
        task = record["task"]
        category = (record.get("meta") or {}).get("category", "unknown")

        if task == CONFLICT_TASK:
            conflict_results.append(result.passed)
        else:
            citation_results.append(result.passed)

        per_task[task].append(result.passed)
        per_category[category].append(result.passed)
        details.append(
            {"task": task, "category": category, "passed": result.passed, "reason": result.reason}
        )

    return {
        "count": len(predictions),
        "citation_fidelity": _rate(citation_results),
        "conflict_handling": _rate(conflict_results),
        "per_task": {
            task: {"count": len(values), "pass_rate": _rate(values)}
            for task, values in sorted(per_task.items())
        },
        "per_category": {
            category: {"count": len(values), "pass_rate": _rate(values)}
            for category, values in sorted(per_category.items())
        },
        "details": details,
    }


def compare_splits(
    train_scores: Mapping[str, Any] | None, eval_scores: Mapping[str, Any] | None
) -> dict[str, Any] | None:
    """Held-out (eval) vs train citation-fidelity comparison, if both are available."""
    if train_scores is None or eval_scores is None:
        return None
    train_fidelity = train_scores.get("citation_fidelity")
    eval_fidelity = eval_scores.get("citation_fidelity")
    gap = (
        eval_fidelity - train_fidelity if train_fidelity is not None and eval_fidelity is not None
        else None
    )
    return {
        "train_citation_fidelity": train_fidelity,
        "eval_citation_fidelity": eval_fidelity,
        "citation_fidelity_gap": gap,
    }


def load_predictions(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvaluationError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise EvaluationError(f"{path}:{line_number}: prediction record must be an object")
            records.append(payload)
    return records


def _load_jsonl_records(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def generate_predictions(
    checkpoint: str | Path,
    eval_jsonl: str | Path,
    *,
    base_repo_id: str | None = None,
    base_revision: str | None = None,
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
    progress_cb: Callable[[int, int], None] | None = None,
) -> list[dict[str, Any]]:
    """Generate predictions from a checkpoint over eval_jsonl (imports torch lazily)."""
    from stoic_training import infer  # heavy import deferred to call time

    records = _load_jsonl_records(eval_jsonl)
    return infer.run_batch(
        checkpoint,
        records,
        base_repo_id=base_repo_id,
        base_revision=base_revision,
        max_new_tokens=max_new_tokens,
        progress_cb=progress_cb,
    )


def _write_report(report: Mapping[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score predictions, or generate then score, against the source corpus."
    )
    parser.add_argument("--predictions", type=Path, default=None, help="Existing predictions JSONL")
    parser.add_argument("--train-predictions", type=Path, default=None, help="Optional train-split predictions JSONL, for a held-out comparison")
    parser.add_argument("--eval-jsonl", type=Path, default=None, help="eval.jsonl to generate predictions from (generation mode)")
    parser.add_argument("--checkpoint", type=Path, default=None, help="Checkpoint dir for generation mode")
    parser.add_argument("--base-repo-id", default=None, help="Base model repo id (required if checkpoint is a LoRA adapter)")
    parser.add_argument("--base-revision", default=None)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_PATH)
    parser.add_argument("--overlap-threshold", type=float, default=DEFAULT_OVERLAP_THRESHOLD)
    parser.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
    parser.add_argument("--output", type=Path, default=None, help="scores.json path (default: alongside predictions/run dir)")
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Write a tailable evaluate.log + progress.json here (default: none, "
        "byte-for-byte today's behaviour)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    # Generation mode reaches transformers via infer.run_batch, which reads
    # HF_HOME at import time; set it here so the migrated base-model cache
    # is reused. Harmless in scoring-only mode (no model is loaded).
    from stoic_training.config import ensure_hf_home

    ensure_hf_home()
    args = parse_args(argv)

    writer: progress.ProgressWriter | None = None
    if args.run_dir is not None:
        writer = progress.ProgressWriter(
            args.run_dir, args.run_dir.name, log_name="evaluate.log", phase="evaluate"
        )
        startup_line = (
            f"run_dir={args.run_dir} evaluate.log={writer.log_path} "
            f"progress.json={writer.progress_path}"
        )
        print(startup_line, flush=True)
        writer.log(startup_line)

    corpus = load_corpus(args.corpus)
    if writer is not None:
        writer.log(f"corpus loaded: {len(corpus)} records from {args.corpus}")

    if args.predictions is not None:
        if writer is not None:
            writer.log(f"prediction source: file {args.predictions}")
        predictions = load_predictions(args.predictions)
        default_output_base = args.predictions
    else:
        if args.checkpoint is None or args.eval_jsonl is None:
            raise SystemExit("generation mode requires --checkpoint and --eval-jsonl")
        if writer is not None:
            writer.log(
                f"prediction source: generation from checkpoint {args.checkpoint} "
                f"over {args.eval_jsonl}"
            )
            progress_writer = writer

            def _progress_cb(done: int, total: int) -> None:
                progress_writer.update(step=done, total_steps=total)

            predictions = generate_predictions(
                args.checkpoint,
                args.eval_jsonl,
                base_repo_id=args.base_repo_id,
                base_revision=args.base_revision,
                max_new_tokens=args.max_new_tokens,
                progress_cb=_progress_cb,
            )
        else:
            predictions = generate_predictions(
                args.checkpoint,
                args.eval_jsonl,
                base_repo_id=args.base_repo_id,
                base_revision=args.base_revision,
                max_new_tokens=args.max_new_tokens,
            )
        default_output_base = args.eval_jsonl

    if writer is not None:
        writer.log("scoring started")
    eval_scores = score_predictions(predictions, corpus, overlap_threshold=args.overlap_threshold)

    report: dict[str, Any] = {"eval": eval_scores}
    if args.train_predictions is not None:
        train_predictions = load_predictions(args.train_predictions)
        train_scores = score_predictions(
            train_predictions, corpus, overlap_threshold=args.overlap_threshold
        )
        report["train"] = train_scores
        report["held_out_comparison"] = compare_splits(train_scores, eval_scores)

    output = args.output or default_output_base.parent / "scores.json"
    _write_report(report, output)
    print(json.dumps(report, indent=2, sort_keys=True))

    if writer is not None:
        headline = (
            f"citation_fidelity={eval_scores.get('citation_fidelity')} "
            f"conflict_handling={eval_scores.get('conflict_handling')} "
            f"count={eval_scores.get('count')}"
        )
        writer.log(headline)
        writer.log(f"report written to {output}")
        writer.finish("evaluation complete")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
