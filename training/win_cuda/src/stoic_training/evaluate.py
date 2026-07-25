"""Deterministic, model-free scoring for the offline research-assistant SLM.

Purpose guardrail: this evaluates an OFFLINE research assistant that
proposes cited rule candidates for human review; its output never touches
any live trading path.

Three modes:
  (a) `--predictions FILE`: score an existing predictions JSONL
      ([{"meta":..., "task":..., "prediction": str}, ...]).
  (b) default: generate predictions from a checkpoint over eval.jsonl
      (deterministic generation: do_sample=False, temperature=None, fixed
      max_new_tokens), then score them.
  (c) `--baseline`: generate predictions from the pinned, un-fine-tuned
      base model (no checkpoint) and score them the same way, writing a
      synthetic `baseline-<digest>` run so the zero point is comparable
      (design doc section 4.2).

Scoring is pure Python (stdlib `re`/`difflib`/`json`/`hashlib`) and every
function below `main()` is importable without torch, so predictions can be
scored in CI with no GPU. Only modes (b)/(c) touch a model, via
`infer.run_batch`, imported lazily inside `generate_predictions`.

Optional `--run-dir DIR`: when given, main() writes a tailable
`<run_dir>/evaluate.log` and `<run_dir>/progress.json` (see progress.py),
lands `predictions.jsonl`/`scores.json` under `<run_dir>/evaluation/`
(generation and baseline modes write predictions.jsonl there; scoring-only
mode leaves an externally supplied predictions file where it is), merges an
`evaluation` section into the run's `manifest.json`
(`manifest.update_manifest_evaluation`), and appends one line to
`<runs-root>/index.jsonl` (`runs_index.append_entry`) -- see the design doc,
section 4. With no `--run-dir`, the scores.json *location* is unchanged
from before (next to the predictions/eval file), so ad-hoc scoring keeps
working; the new digest/version metadata described below is always present.

Every prediction row and every `scores.json` `details` entry carries a
stable `example_id` (`sha256(task || video_id || hms || prompt)[:16]`, see
`example_id_for_record`), enabling paired run-over-run comparison
(`stoic_training.compare`) even though the underlying prompt text is not
re-derivable from `meta` alone once the model has generated text for it.

Metrics:
  - citation_fidelity: fraction of (non-conflict_check) predictions whose
    trailing "Citation: <video_id> <hms>" line names a record that exists
    in the source corpus, and whose body has sufficient token overlap with
    that record's narration or why (default threshold 0.3).
  - conflict_handling: fraction of conflict_check predictions that cite at
    least two distinct video_ids and contain an explicit ambiguity/conflict
    marker word.
Both are reported overall, per-task, and per-meta.category; a held-out vs
train comparison is included when both prediction sets are supplied. Every
prediction is additionally classified into a disjoint failure-mode bucket
(`classify_prediction`) -- pass/schema_violation/no_citation/
citation_not_in_corpus/weak_overlap for citation-scored tasks, and their own
pass/insufficient_citations/no_conflict_marker namespace for conflict_check
-- because run-over-run movement of, say, the hallucination bucket is more
informative than the headline pass rate (design doc section 2).

`SCORING_VERSION` is stamped into every `scores.json` and manifest
`evaluation` section together with the scoring params. Comparisons across
different `scoring_version`s are refused by `stoic_training.compare`.

Holdout seal (design doc section 5.2, mechanism in `splits.py`): scoring a
split-v2 **holdout** eval set is refused (exit 2) unless
`--unseal "<reason>"` is given, in which case the run id, ISO date, eval
set and reason are appended to the committed `splits/unseal-ledger.md`.
Detection is by content sha256 against the `role: "holdout"` entry of the
`dataset_manifest.json` sitting next to the eval file -- so renaming the
file does not bypass the seal -- with the `eval_holdout` filename as a
second, manifest-free backstop. Files that are neither stay
friction-free: no manifest, no holdout name, no refusal.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path
from typing import Any

from stoic_training import manifest as manifest_mod
from stoic_training import progress
from stoic_training import splits as splits_mod

SCORING_VERSION = "1"
# Exit code for a refusal (as opposed to 1 = IO/usage), matching compare.py.
EXIT_REFUSED = 2
DEFAULT_OVERLAP_THRESHOLD = 0.3
DEFAULT_MAX_NEW_TOKENS = 256
CONFLICT_TASK = "conflict_check"

# Failure-mode buckets for citation-scored tasks (rule_candidate, cited_qa,
# and any other non-conflict task). Order matches the precedence in
# classify_prediction's docstring; kept exactly as pinned in the WP1
# contract so downstream tooling (compare.py) can rely on the tuple order.
BUCKET_PASS = "pass"
BUCKET_NO_CITATION = "no_citation"
BUCKET_CITATION_NOT_IN_CORPUS = "citation_not_in_corpus"
BUCKET_WEAK_OVERLAP = "weak_overlap"
BUCKET_SCHEMA_VIOLATION = "schema_violation"
CITATION_BUCKETS = (
    BUCKET_PASS,
    BUCKET_SCHEMA_VIOLATION,
    BUCKET_NO_CITATION,
    BUCKET_CITATION_NOT_IN_CORPUS,
    BUCKET_WEAK_OVERLAP,
)

# conflict_check keeps its own bucket namespace.
CONFLICT_BUCKET_PASS = "pass"
CONFLICT_BUCKET_INSUFFICIENT_CITATIONS = "insufficient_citations"
CONFLICT_BUCKET_NO_MARKER = "no_conflict_marker"
CONFLICT_BUCKETS = (
    CONFLICT_BUCKET_PASS,
    CONFLICT_BUCKET_INSUFFICIENT_CITATIONS,
    CONFLICT_BUCKET_NO_MARKER,
)

# ASCII unit separator: cannot occur in task/video_id/hms/prompt text, so it
# safely disambiguates the joined fields hashed into a stable example_id.
EXAMPLE_ID_SEPARATOR = "\x1f"

_RULE_CANDIDATE_PREFIXES = (
    "Rule candidate:",
    "Setup / entry condition:",
    "Invalidation / caveat:",
)

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


def example_id(*, task: str, video_id: str, hms: str, prompt: str) -> str:
    """sha256 of explicitly framed, \x1f-separated fields, first 16 hex chars."""
    payload = EXAMPLE_ID_SEPARATOR.join(
        (f"task={task}", f"video_id={video_id}", f"hms={hms}", f"prompt={prompt}")
    )
    return sha256(payload.encode("utf-8")).hexdigest()[:16]


def prompt_from_messages(messages: Sequence[Mapping[str, Any]] | None) -> str:
    """Concatenate the content of every role=="user" message with "\n" between."""
    if not messages:
        return ""
    contents = [
        str(message.get("content", "")) for message in messages if message.get("role") == "user"
    ]
    return "\n".join(contents)


def example_id_for_record(record: Mapping[str, Any]) -> str:
    """example_id for an eval row OR a prediction row.

    task/video_id/hms default to "" when absent. `prompt` is taken directly
    from a non-empty str "prompt" key when present (predictions.jsonl rows
    carry one, see infer.run_batch); otherwise it is reconstructed from
    `messages` (eval.jsonl rows), so the same id is stable across the
    generation -> scoring round trip.
    """
    task = record.get("task") or ""
    meta = record.get("meta") or {}
    video_id = meta.get("video_id") or ""
    hms = meta.get("hms") or ""
    prompt = record.get("prompt")
    if not (isinstance(prompt, str) and prompt):
        prompt = prompt_from_messages(record.get("messages"))
    return example_id(task=task, video_id=video_id, hms=hms, prompt=prompt)


@dataclass(frozen=True, slots=True)
class PredictionScore:
    passed: bool
    reason: str
    bucket: str = BUCKET_PASS


def schema_violation(task: str, prediction_text: str) -> bool:
    """Tier-0 structural check, per task. True means the schema is broken.

    - rule_candidate requires all three labelled lines, each as its own
      line, in this order: a line starting "Rule candidate:", then
      "Setup / entry condition:", then "Invalidation / caveat:" (matched
      case-sensitively on the stripped-line prefix).
    - cited_qa and any other non-conflict task just require a non-empty
      body (citation_body(text) non-blank).
    - conflict_check has no schema gate here; see its own precedence in
      classify_prediction.
    """
    if task == CONFLICT_TASK:
        return False
    if task == "rule_candidate":
        lines = [line.strip() for line in prediction_text.strip().splitlines() if line.strip()]
        position = 0
        for prefix in _RULE_CANDIDATE_PREFIXES:
            while position < len(lines) and not lines[position].startswith(prefix):
                position += 1
            if position >= len(lines):
                return True
            position += 1
        return False
    return not citation_body(prediction_text)


def score_citation_fidelity(
    prediction_text: str,
    corpus: CorpusIndex,
    *,
    overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD,
) -> PredictionScore:
    citation = trailing_citation(prediction_text)
    if citation is None:
        return PredictionScore(False, "no trailing citation", BUCKET_NO_CITATION)
    record = corpus.get(citation)
    if record is None:
        return PredictionScore(
            False,
            f"citation not found in corpus: {citation[0]} {citation[1]}",
            BUCKET_CITATION_NOT_IN_CORPUS,
        )
    body = citation_body(prediction_text)
    overlap = max(
        token_overlap_ratio(body, record.narration),
        token_overlap_ratio(body, record.why),
    )
    if overlap < overlap_threshold:
        return PredictionScore(
            False, f"citation overlap {overlap:.3f} below threshold", BUCKET_WEAK_OVERLAP
        )
    return PredictionScore(True, "ok", BUCKET_PASS)


def score_conflict_handling(prediction_text: str) -> PredictionScore:
    citations = extract_citations(prediction_text)
    distinct_video_ids = {video_id for video_id, _ in citations}
    if len(distinct_video_ids) < 2:
        return PredictionScore(
            False, "fewer than two cited video_ids", CONFLICT_BUCKET_INSUFFICIENT_CITATIONS
        )
    tokens = set(_tokenize(prediction_text))
    if not tokens & CONFLICT_MARKERS:
        return PredictionScore(False, "no ambiguity/conflict marker", CONFLICT_BUCKET_NO_MARKER)
    return PredictionScore(True, "ok", CONFLICT_BUCKET_PASS)


def score_prediction(
    record: Mapping[str, Any],
    corpus: CorpusIndex,
    *,
    overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD,
) -> PredictionScore:
    """Backwards-compatible alias for `classify_prediction`.

    This is deliberately a delegation rather than its own (pre-WP1,
    schema-blind) implementation: two functions that both answer "did this
    prediction pass?" and disagree -- a rule_candidate with a valid citation
    but none of its labelled lines passes one and not the other -- is a trap
    for the next caller. There is exactly one definition of `passed`, and
    `classify_prediction` owns it.
    """
    return classify_prediction(record, corpus, overlap_threshold=overlap_threshold)


def classify_prediction(
    record: Mapping[str, Any],
    corpus: CorpusIndex,
    *,
    overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD,
) -> PredictionScore:
    """Classify a prediction into a disjoint failure-mode bucket.

    Precedence for citation-scored tasks (rule_candidate, cited_qa, and any
    other non-conflict task), schema first, first match wins:
    schema_violation -> no_citation -> citation_not_in_corpus -> weak_overlap
    -> pass.

    Schema-first is chosen because Tier-0 structure is the cheapest, most
    objective gate and a structurally broken output makes the body/citation
    decomposition meaningless; and the presence/shape of the trailing
    citation line is deliberately factored OUT of schema_violation into its
    own no_citation bucket so the buckets stay disjoint and the
    hallucination bucket (citation_not_in_corpus) keeps a clean signal
    (design doc section 2: "Run-over-run movement of the hallucination
    bucket is more informative than the headline rate"). This ordering is
    stable under SCORING_VERSION "1"; changing it requires bumping
    SCORING_VERSION.

    conflict_check keeps its own bucket namespace and precedence:
    insufficient_citations -> no_conflict_marker -> pass.

    `passed` is True iff bucket == "pass" (in either namespace).
    """
    task = record.get("task")
    prediction_text = record.get("prediction")
    if not isinstance(task, str) or not task:
        raise EvaluationError("prediction record missing task")
    if not isinstance(prediction_text, str):
        raise EvaluationError("prediction record missing prediction text")

    if task == CONFLICT_TASK:
        return score_conflict_handling(prediction_text)

    if schema_violation(task, prediction_text):
        return PredictionScore(False, "schema violation", BUCKET_SCHEMA_VIOLATION)

    return score_citation_fidelity(prediction_text, corpus, overlap_threshold=overlap_threshold)


def _rate(values: list[bool]) -> float | None:
    return (sum(values) / len(values)) if values else None


def _bucket_rates(counts: Mapping[str, int]) -> dict[str, float | None]:
    total = sum(counts.values())
    return {bucket: (count / total if total else None) for bucket, count in counts.items()}


def score_predictions(
    predictions: Sequence[Mapping[str, Any]],
    corpus: CorpusIndex,
    *,
    overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD,
) -> dict[str, Any]:
    """Score a batch of predictions; returns overall/per-task/per-category metrics.

    Every bucket dict always contains every key of its namespace (zeros
    included), so run-over-run deltas are total (see design doc section 4).
    """
    per_task: dict[str, list[bool]] = defaultdict(list)
    per_task_buckets: dict[str, dict[str, int]] = {}
    per_category: dict[str, list[bool]] = defaultdict(list)
    citation_results: list[bool] = []
    conflict_results: list[bool] = []
    citation_buckets: dict[str, int] = dict.fromkeys(CITATION_BUCKETS, 0)
    conflict_buckets: dict[str, int] = dict.fromkeys(CONFLICT_BUCKETS, 0)
    details: list[dict[str, Any]] = []

    for record in predictions:
        result = classify_prediction(record, corpus, overlap_threshold=overlap_threshold)
        task = record["task"]
        category = (record.get("meta") or {}).get("category", "unknown")
        is_conflict = task == CONFLICT_TASK

        if is_conflict:
            conflict_results.append(result.passed)
            conflict_buckets[result.bucket] += 1
        else:
            citation_results.append(result.passed)
            citation_buckets[result.bucket] += 1

        per_task[task].append(result.passed)
        per_category[category].append(result.passed)
        task_buckets = per_task_buckets.setdefault(
            task, dict.fromkeys(CONFLICT_BUCKETS if is_conflict else CITATION_BUCKETS, 0)
        )
        task_buckets[result.bucket] += 1

        details.append(
            {
                "example_id": example_id_for_record(record),
                "task": task,
                "category": category,
                "passed": result.passed,
                "reason": result.reason,
                "bucket": result.bucket,
            }
        )

    return {
        "count": len(predictions),
        "citation_fidelity": _rate(citation_results),
        "conflict_handling": _rate(conflict_results),
        "buckets": citation_buckets,
        "bucket_rates": _bucket_rates(citation_buckets),
        "conflict_buckets": conflict_buckets,
        "conflict_bucket_rates": _bucket_rates(conflict_buckets),
        "per_task": {
            task: {
                "count": len(values),
                "pass_rate": _rate(values),
                "buckets": per_task_buckets[task],
                "bucket_rates": _bucket_rates(per_task_buckets[task]),
            }
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
    checkpoint: str | Path | None,
    eval_jsonl: str | Path,
    *,
    base_repo_id: str | None = None,
    base_revision: str | None = None,
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
    progress_cb: Callable[[int, int], None] | None = None,
) -> list[dict[str, Any]]:
    """Generate predictions over eval_jsonl (imports torch lazily).

    checkpoint=None routes to the baseline (un-fine-tuned) path in
    infer.run_batch / infer.load_model_and_tokenizer.
    """
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


def baseline_run_id(
    *, base_repo_id: str, base_revision: str | None, eval_set_sha256: str, scoring_version: str
) -> str:
    """'baseline-' + first 16 hex chars of the sha256 of the canonical identity payload.

    Derived from the eval-set digest + scoring_version + base model
    revision (design doc section 4.2), not from a training identity
    payload, so the same base model scored against the same eval set and
    scoring rules always lands in the same baseline run dir.
    """
    payload = {
        "base_model": {"repo_id": base_repo_id, "revision": base_revision},
        "eval_set_sha256": eval_set_sha256,
        "scoring_version": scoring_version,
    }
    return "baseline-" + manifest_mod.sha256_hex(payload)[:16]


def _resolve_runs_root(args: argparse.Namespace) -> Path:
    if args.runs_root is not None:
        return Path(args.runs_root)
    if args.run_dir is not None:
        return Path(args.run_dir).resolve().parent
    from stoic_training.config import default_train_home

    return default_train_home() / "runs"


def _resolve_hypothesis(
    existing: str | None, requested: str | None
) -> tuple[str | None, str | None]:
    """Apply the keep-the-original-and-warn rule (design doc section 4.1 / C8).

    A pre-registered hypothesis is never rewritten by a later --hypothesis:
    pre-registration is worthless if it can be edited after the fact.
    Returns (final_hypothesis, warning_message_or_None).
    """
    if not requested:
        return existing, None
    if not existing:
        return requested, None
    if existing == requested:
        return existing, None
    return existing, f"hypothesis already pre-registered as {existing!r}; ignoring --hypothesis"


def _write_evaluation_manifest_and_index(
    *,
    run_dir: Path,
    runs_root: Path,
    output: Path,
    predictions_output_path: Path | None,
    eval_scores: Mapping[str, Any],
    corpus_sha256: str,
    eval_set_sha256: str,
    eval_set_source: str,
    overlap_threshold: float,
    generated_utc: str,
    baseline: bool,
    hypothesis: str | None,
    writer: progress.ProgressWriter | None,
) -> None:
    """Merge the `evaluation` section into manifest.json and append a runs-index line.

    No-ops (with a warning) when `--run-dir` points at a directory that has
    no manifest.json: that is an ad-hoc scoring dir, not a real run dir, and
    the scores/predictions have already been written by the time we get
    here. Refusing to crash matters because in generation mode those
    artifacts cost GPU-hours -- losing the run to a traceback over a missing
    manifest would be the worst possible trade.

    Imports `runs_index` lazily so this module stays importable even if that
    module were briefly absent; in practice it is always present alongside
    this one.
    """
    if not (Path(run_dir) / "manifest.json").is_file():
        warning = (
            f"no manifest.json in {run_dir}: skipping the manifest `evaluation` section "
            "and the runs-index line (scores/predictions were still written). Point "
            "--run-dir at a real run dir to record evaluation provenance."
        )
        print(warning, flush=True)
        if writer is not None:
            writer.log(warning)
        return

    if not baseline:
        current_manifest = manifest_mod.read_manifest(run_dir)
        final_hypothesis, warning = _resolve_hypothesis(
            current_manifest.get("hypothesis"), hypothesis
        )
        if warning:
            print(warning, flush=True)
            if writer is not None:
                writer.log(warning)
        if final_hypothesis != current_manifest.get("hypothesis"):
            current_manifest["hypothesis"] = final_hypothesis
            manifest_mod.write_manifest(current_manifest, run_dir)

    metrics = {
        "count": eval_scores.get("count"),
        "citation_fidelity": eval_scores.get("citation_fidelity"),
        "conflict_handling": eval_scores.get("conflict_handling"),
        "buckets": eval_scores.get("buckets"),
        "conflict_buckets": eval_scores.get("conflict_buckets"),
    }
    evaluation_section: dict[str, Any] = {
        "scoring_version": SCORING_VERSION,
        "params": {"overlap_threshold": overlap_threshold},
        "scores": {
            "path": str(Path(output).resolve()),
            "sha256": manifest_mod.sha256_file(output),
        },
        "metrics": metrics,
        "corpus_sha256": corpus_sha256,
        "eval_set_sha256": eval_set_sha256,
        "eval_set_source": eval_set_source,
        "evaluated_utc": generated_utc,
    }
    if predictions_output_path is not None:
        predictions_path = Path(predictions_output_path).resolve()
        evaluation_section["predictions"] = {
            "path": str(predictions_path),
            "sha256": manifest_mod.sha256_file(predictions_path),
        }

    manifest_mod.update_manifest_evaluation(run_dir, evaluation_section)

    from stoic_training import runs_index

    updated_manifest = manifest_mod.read_manifest(run_dir)
    config_resolved = None if baseline else updated_manifest.get("config_resolved")
    knob_diff: dict[str, Any] = {}
    if config_resolved is not None:
        previous = runs_index.previous_config_resolved(runs_root)
        knob_diff = runs_index.diff_configs(previous, config_resolved)

    entry = runs_index.build_entry(
        run_id=updated_manifest["run_id"],
        date=generated_utc,
        config_sha256=updated_manifest.get("config_sha256"),
        knob_diff=knob_diff,
        hypothesis=updated_manifest.get("hypothesis"),
        metrics=metrics,
        scoring_version=SCORING_VERSION,
        eval_set_sha256=eval_set_sha256,
        corpus_sha256=corpus_sha256,
    )
    runs_index.append_entry(runs_root, entry)


def detect_sealed_holdout(args: argparse.Namespace) -> splits_mod.HoldoutDetection | None:
    """First sealed-holdout hit among the eval-set inputs of this invocation.

    Both `--eval-jsonl` and `--predictions` are checked: the eval file is
    the usual route, but a predictions file generated over the holdout and
    then scored later is the same disclosure, and `--predictions
    .../eval_holdout.jsonl`-shaped paths must not slip through. Checking
    both costs one sha256 of a small file.
    """
    for candidate in (getattr(args, "eval_jsonl", None), getattr(args, "predictions", None)):
        detection = splits_mod.detect_holdout(candidate)
        if detection is not None:
            return detection
    return None


def _unseal_run_id(run_id: str | None, run_dir: Path | None) -> str:
    """Best available run identity for the ledger row.

    Falls back through manifest run_id -> run-dir name -> a literal
    "(no run dir)" rather than failing: a ledger row with a weak id is far
    better than an unsealing that went unrecorded because the id lookup
    raised.
    """
    if run_id:
        return run_id
    if run_dir is not None:
        try:
            return str(manifest_mod.read_manifest(run_dir).get("run_id") or run_dir.name)
        except (OSError, json.JSONDecodeError, manifest_mod.ManifestError):
            return run_dir.name
    return "(no run dir)"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score predictions, or generate then score, against the source corpus."
    )
    parser.add_argument("--predictions", type=Path, default=None, help="Existing predictions JSONL")
    parser.add_argument("--train-predictions", type=Path, default=None, help="Optional train-split predictions JSONL, for a held-out comparison")
    parser.add_argument(
        "--eval-jsonl",
        type=Path,
        default=None,
        help="eval.jsonl to generate predictions from (generation/baseline mode), or to "
        "digest alongside an external --predictions file",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help="Checkpoint dir for generation mode (omit with --baseline)",
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Score the pinned, un-fine-tuned base model (no --checkpoint); requires "
        "--eval-jsonl and --base-repo-id",
    )
    parser.add_argument(
        "--base-repo-id",
        default=None,
        help="Base model repo id (required if checkpoint is a LoRA adapter, or with --baseline)",
    )
    parser.add_argument("--base-revision", default=None)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_PATH)
    parser.add_argument("--overlap-threshold", type=float, default=DEFAULT_OVERLAP_THRESHOLD)
    parser.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="scores.json path (default: alongside predictions/run dir)",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Write a tailable evaluate.log + progress.json here (default: none, "
        "byte-for-byte today's behaviour)",
    )
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=None,
        help="Runs root for baseline run-dir placement and the runs index (default: "
        "run-dir's parent, or config.default_train_home()/'runs')",
    )
    parser.add_argument(
        "--hypothesis",
        default=None,
        help="Pre-registered prediction for this run; kept as-is (with a warning) if the "
        "run-dir manifest already has a different one",
    )
    parser.add_argument(
        "--unseal",
        default=None,
        metavar="REASON",
        help="Deliberately score a SEALED holdout eval set. Requires a non-empty reason, "
        "which is appended with the run id and date to splits/unseal-ledger.md. "
        "Budget: single-digit unsealings per split version.",
    )
    parser.add_argument(
        "--unseal-ledger",
        type=Path,
        default=splits_mod.DEFAULT_UNSEAL_LEDGER_PATH,
        help="Path of the committed unseal ledger (default: the package's splits/ dir)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    # Generation mode reaches transformers via infer.run_batch, which reads
    # HF_HOME at import time; set it here so the migrated base-model cache
    # is reused. Harmless in scoring-only mode (no model is loaded).
    from stoic_training.config import ensure_hf_home

    ensure_hf_home()
    args = parse_args(argv)

    if args.baseline:
        if args.checkpoint is not None:
            raise SystemExit("--baseline cannot be combined with --checkpoint")
        if args.eval_jsonl is None or not args.base_repo_id:
            raise SystemExit("--baseline requires --eval-jsonl and --base-repo-id")
    elif args.predictions is None and (args.checkpoint is None or args.eval_jsonl is None):
        raise SystemExit("generation mode requires --checkpoint and --eval-jsonl")

    # Seal check first: refuse BEFORE loading a corpus or (worse) a model, so
    # an accidental holdout run costs a second rather than GPU-hours.
    sealed = detect_sealed_holdout(args)
    unseal_reason = (args.unseal or "").strip()
    if sealed is not None and not unseal_reason:
        print(f"error: {splits_mod.seal_message(sealed)}", file=sys.stderr)
        return EXIT_REFUSED
    if sealed is None and unseal_reason:
        print(
            "warning: --unseal was given but no sealed holdout eval set was detected; "
            "nothing will be written to the unseal ledger.",
            flush=True,
        )

    corpus = load_corpus(args.corpus)
    corpus_sha256 = manifest_mod.sha256_file(args.corpus)
    runs_root = _resolve_runs_root(args)

    run_id: str | None = None
    if args.baseline:
        eval_set_sha256 = manifest_mod.sha256_file(args.eval_jsonl)
        eval_set_source = "eval_jsonl"
        run_id = baseline_run_id(
            base_repo_id=args.base_repo_id,
            base_revision=args.base_revision,
            eval_set_sha256=eval_set_sha256,
            scoring_version=SCORING_VERSION,
        )
        run_dir = args.run_dir if args.run_dir is not None else runs_root / run_id
    else:
        run_dir = args.run_dir
        eval_set_sha256 = None  # resolved below, once the prediction source is known
        eval_set_source = None

    writer: progress.ProgressWriter | None = None
    if run_dir is not None:
        writer = progress.ProgressWriter(
            run_dir, run_id or run_dir.name, log_name="evaluate.log", phase="evaluate"
        )
        startup_line = (
            f"run_dir={run_dir} evaluate.log={writer.log_path} "
            f"progress.json={writer.progress_path}"
        )
        print(startup_line, flush=True)
        writer.log(startup_line)

    if writer is not None:
        writer.log(f"corpus loaded: {len(corpus)} records from {args.corpus}")

    def _progress_cb(done: int, total: int) -> None:
        writer.update(step=done, total_steps=total)

    progress_cb = _progress_cb if writer is not None else None

    predictions_output_path: Path | None = None

    if args.baseline:
        if writer is not None:
            writer.log(
                f"prediction source: baseline generation, base_repo_id={args.base_repo_id} "
                f"base_revision={args.base_revision} over {args.eval_jsonl}"
            )
        code_rev = manifest_mod.git_rev(_REPO_ROOT)
        base_manifest = manifest_mod.build_baseline_manifest(
            run_id=run_id,
            base_model={"repo_id": args.base_repo_id, "revision": args.base_revision},
            eval_set_sha256=eval_set_sha256,
            corpus_sha256=corpus_sha256,
            scoring_version=SCORING_VERSION,
            code_rev=code_rev,
            hypothesis=args.hypothesis,
        )
        manifest_mod.write_manifest(base_manifest, run_dir)
        predictions = generate_predictions(
            None,
            args.eval_jsonl,
            base_repo_id=args.base_repo_id,
            base_revision=args.base_revision,
            max_new_tokens=args.max_new_tokens,
            progress_cb=progress_cb,
        )
        predictions_output_path = run_dir / "evaluation" / "predictions.jsonl"
        predictions_output_path.parent.mkdir(parents=True, exist_ok=True)
        from stoic_training import infer as infer_mod

        infer_mod.write_predictions_jsonl(predictions, predictions_output_path)
        default_output_base = args.eval_jsonl
    elif args.predictions is not None:
        if writer is not None:
            writer.log(f"prediction source: file {args.predictions}")
        predictions = load_predictions(args.predictions)
        default_output_base = args.predictions
        if args.eval_jsonl is not None:
            eval_set_sha256 = manifest_mod.sha256_file(args.eval_jsonl)
            eval_set_source = "eval_jsonl"
        else:
            eval_set_sha256 = manifest_mod.sha256_file(args.predictions)
            eval_set_source = "predictions"
        predictions_output_path = args.predictions
    else:
        eval_set_sha256 = manifest_mod.sha256_file(args.eval_jsonl)
        eval_set_source = "eval_jsonl"
        if writer is not None:
            writer.log(
                f"prediction source: generation from checkpoint {args.checkpoint} "
                f"over {args.eval_jsonl}"
            )
        predictions = generate_predictions(
            args.checkpoint,
            args.eval_jsonl,
            base_repo_id=args.base_repo_id,
            base_revision=args.base_revision,
            max_new_tokens=args.max_new_tokens,
            progress_cb=progress_cb,
        )
        default_output_base = args.eval_jsonl
        if run_dir is not None:
            predictions_output_path = run_dir / "evaluation" / "predictions.jsonl"
            predictions_output_path.parent.mkdir(parents=True, exist_ok=True)
            from stoic_training import infer as infer_mod

            infer_mod.write_predictions_jsonl(predictions, predictions_output_path)

    if writer is not None:
        writer.log("scoring started")
    eval_scores = score_predictions(predictions, corpus, overlap_threshold=args.overlap_threshold)

    generated_utc = datetime.now(UTC).isoformat()
    report: dict[str, Any] = {
        "eval": eval_scores,
        "scoring_version": SCORING_VERSION,
        "params": {"overlap_threshold": args.overlap_threshold},
        "corpus_sha256": corpus_sha256,
        "eval_set_sha256": eval_set_sha256,
        "eval_set_source": eval_set_source,
        "generated_utc": generated_utc,
    }
    if args.train_predictions is not None:
        train_predictions = load_predictions(args.train_predictions)
        train_scores = score_predictions(
            train_predictions, corpus, overlap_threshold=args.overlap_threshold
        )
        report["train"] = train_scores
        report["held_out_comparison"] = compare_splits(train_scores, eval_scores)

    if args.output is not None:
        output = args.output
    elif run_dir is not None:
        output = run_dir / "evaluation" / "scores.json"
    else:
        output = default_output_base.parent / "scores.json"

    _write_report(report, output)
    print(json.dumps(report, indent=2, sort_keys=True))

    if sealed is not None and unseal_reason:
        # Logged only once the holdout has actually been scored -- a run that
        # died before producing a score never disclosed anything, and a ledger
        # inflated by crashed attempts would make the budget meaningless.
        ledger_path = splits_mod.append_unseal_entry(
            run_id=_unseal_run_id(run_id, run_dir),
            reason=unseal_reason,
            eval_set=str(Path(sealed.path).resolve()),
            date=generated_utc,
            ledger_path=args.unseal_ledger,
        )
        line = (
            f"HOLDOUT UNSEALED: {sealed.path} -- reason {unseal_reason!r} logged to "
            f"{ledger_path} ({splits_mod.count_unseal_entries(ledger_path)} unsealing(s) "
            "recorded; budget is single-digit per split version)"
        )
        print(line, flush=True)
        if writer is not None:
            writer.log(line)

    if run_dir is not None:
        _write_evaluation_manifest_and_index(
            run_dir=run_dir,
            runs_root=runs_root,
            output=output,
            predictions_output_path=predictions_output_path,
            eval_scores=eval_scores,
            corpus_sha256=corpus_sha256,
            eval_set_sha256=eval_set_sha256,
            eval_set_source=eval_set_source,
            overlap_threshold=args.overlap_threshold,
            generated_utc=generated_utc,
            baseline=args.baseline,
            hypothesis=args.hypothesis,
            writer=writer,
        )

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
