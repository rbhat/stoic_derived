"""Human calibration audit of the Tier-1 scoring proxy.

Purpose guardrail: this measures how well a deterministic proxy agrees with
a human about an OFFLINE research assistant's citations. No number produced
here gates anything live -- the only live gate is a human-approved, signed
SP0 release (VISION.md, design doc section 7).

Why (design doc section 2): Tier 1 scores claim-vs-narration support by
token overlap at a fixed threshold. That proxy is *biased* -- it fails some
genuinely-supported paraphrases and passes some coincidental overlaps. The
bias is tolerable only because it is stable across runs AND quantified.
This module is the quantifier: it turns "the metric is subjective" into
"the metric has a measured 12% false-fail rate", a known error bar we
accept and re-check whenever `scoring_version` changes.

Two subcommands:

  sample   Draw a seeded, deterministic, pass/fail-stratified sample from a
           run's `evaluation/{predictions.jsonl,scores.json}` -- spread
           across failure buckets within the fail stratum -- and write a
           labeling sheet: `<name>.jsonl` (machine round-trip) plus a
           `<name>.md` companion to actually work through. Each row carries
           the prediction, the (video_id, hms) it cited, and THAT record's
           narration/why from the corpus, so the labeler can judge support
           without hunting through the corpus. Nothing else from the eval
           set is included -- in particular not the gold answer, which
           would anchor the judgement it is supposed to be independent of.

  ingest   Read the filled sheet, treat human "supported" as ground truth,
           and write the calibration record to
           `evaluation/calibration/<scoring_version>.json` -- committed
           lineage of the metric, keyed by scoring_version.

Stdlib only. Imports `evaluate` for the shared citation parsing/corpus
index, which is itself importable without torch.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from stoic_training import evaluate as evaluate_mod

DEFAULT_SAMPLE_SIZE = 50
DEFAULT_SEED = 20260725

LABEL_SUPPORTED = "supported"
LABEL_NOT_SUPPORTED = "not_supported"
LABEL_UNSURE = "unsure"
ALLOWED_LABELS = (LABEL_SUPPORTED, LABEL_NOT_SUPPORTED, LABEL_UNSURE)

RECORD_TYPE_META = "meta"
RECORD_TYPE_EXAMPLE = "example"

# src/stoic_training/calibrate.py -> stoic_training -> src -> win_cuda
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CALIBRATION_DIR = PACKAGE_ROOT / "evaluation" / "calibration"

SHEET_INSTRUCTIONS = (
    'Label each example "supported" / "not_supported" / "unsure" by judging ONLY '
    "whether the cited course record actually supports the prediction's claim. "
    "Ignore wording, style, and whether the automated scorer agreed."
)


class CalibrationError(RuntimeError):
    """Raised when a run dir, sheet, or calibration record cannot be processed."""


def sha256_file(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CalibrationError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise CalibrationError(f"{path}:{line_number}: record must be an object")
            rows.append(payload)
    return rows


# --------------------------------------------------------------------------
# sampling
# --------------------------------------------------------------------------


def allocate_sample(
    strata: Mapping[str, int], total: int, *, pass_share: float = 0.5
) -> dict[str, int]:
    """Allocate `total` sample slots across strata, capped by availability.

    Stratification rule (design doc section 2 asks for "stratified
    pass/fail", refined here): half the sample goes to `pass`, half is
    spread as evenly as possible across the failure buckets that actually
    occurred. Even spreading matters because the buckets are wildly
    unbalanced in practice -- a proportional sample of a run at 20% pass
    would be almost entirely `weak_overlap`, and we would learn nothing
    about whether `citation_not_in_corpus` (the hallucination bucket) is
    correctly identified.

    Shortfalls redistribute: a stratum with fewer examples than its
    allocation gives its remainder back, and the loop repeats until either
    `total` slots are placed or every stratum is exhausted. Ties are broken
    by stratum name so the result is deterministic.
    """
    available = {name: count for name, count in strata.items() if count > 0}
    if not available or total <= 0:
        return {}

    allocation = dict.fromkeys(available, 0)
    pass_names = [name for name in available if name == evaluate_mod.BUCKET_PASS]
    fail_names = sorted(name for name in available if name != evaluate_mod.BUCKET_PASS)

    groups: list[tuple[list[str], int]] = []
    if pass_names and fail_names:
        pass_slots = min(round(total * pass_share), total)
        groups = [(pass_names, pass_slots), (fail_names, total - pass_slots)]
    else:
        groups = [(pass_names or fail_names, total)]

    placed = 0
    for names, slots in groups:
        placed += _fill_group(allocation, available, names, slots)

    # Redistribute anything the groups could not place (a stratum ran out).
    leftover = total - placed
    if leftover > 0:
        _fill_group(allocation, available, sorted(available), leftover)
    return {name: count for name, count in allocation.items() if count > 0}


def _fill_group(
    allocation: dict[str, int],
    available: Mapping[str, int],
    names: Sequence[str],
    slots: int,
) -> int:
    """Round-robin `slots` across `names`, never exceeding availability."""
    if not names or slots <= 0:
        return 0
    placed = 0
    while placed < slots:
        progressed = False
        for name in names:
            if placed >= slots:
                break
            if allocation[name] < available[name]:
                allocation[name] += 1
                placed += 1
                progressed = True
        if not progressed:
            break
    return placed


def _stratum_of(detail: Mapping[str, Any]) -> str:
    """A detail row's stratum: "pass", else its failure bucket."""
    if detail.get("passed"):
        return evaluate_mod.BUCKET_PASS
    bucket = detail.get("bucket")
    return bucket if isinstance(bucket, str) and bucket else "unknown"


def select_examples(
    details: Sequence[Mapping[str, Any]],
    *,
    size: int = DEFAULT_SAMPLE_SIZE,
    seed: int = DEFAULT_SEED,
) -> list[dict[str, Any]]:
    """Seeded, deterministic, stratified selection of scored examples.

    Determinism comes from sorting each stratum by `example_id` before the
    seeded shuffle: `scores.json` row order reflects generation order, and a
    sample that moved when the eval file was re-ordered would not be a
    reproducible audit.
    """
    by_stratum: dict[str, list[Mapping[str, Any]]] = {}
    for detail in details:
        by_stratum.setdefault(_stratum_of(detail), []).append(detail)

    allocation = allocate_sample({name: len(rows) for name, rows in by_stratum.items()}, size)

    chosen: list[dict[str, Any]] = []
    for stratum in sorted(allocation):
        rows = sorted(by_stratum[stratum], key=lambda row: str(row.get("example_id", "")))
        rng = random.Random(f"{seed}:{stratum}")
        rng.shuffle(rows)
        chosen.extend(dict(row) for row in rows[: allocation[stratum]])
    chosen.sort(key=lambda row: (_stratum_of(row), str(row.get("example_id", ""))))
    return chosen


def _cited_records(
    prediction_text: str, task: str, corpus: Mapping[tuple[str, str], Any]
) -> list[dict[str, Any]]:
    """The corpus records a prediction cites, in citation order.

    citation-scored tasks are judged on their TRAILING citation (the one
    `evaluate.score_citation_fidelity` scores), so that is what the sheet
    shows; conflict_check is judged on citing two distinct videos, so all
    of its citations are shown.
    """
    if task == evaluate_mod.CONFLICT_TASK:
        citations = evaluate_mod.extract_citations(prediction_text)
    else:
        trailing = evaluate_mod.trailing_citation(prediction_text)
        citations = [trailing] if trailing else []

    cited: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for citation in citations:
        if citation in seen:
            continue
        seen.add(citation)
        record = corpus.get(citation)
        cited.append(
            {
                "video_id": citation[0],
                "hms": citation[1],
                "in_corpus": record is not None,
                "narration": record.narration if record is not None else None,
                "why": record.why if record is not None else None,
            }
        )
    return cited


def build_sheet_rows(
    selected: Sequence[Mapping[str, Any]],
    predictions_by_id: Mapping[str, Mapping[str, Any]],
    corpus: Mapping[tuple[str, str], Any],
) -> list[dict[str, Any]]:
    """One labeling row per selected example. `human_label` is left empty."""
    rows: list[dict[str, Any]] = []
    for detail in selected:
        example_id = str(detail.get("example_id", ""))
        prediction = predictions_by_id.get(example_id)
        if prediction is None:
            raise CalibrationError(
                f"example_id {example_id} is in scores.json but not in "
                "predictions.jsonl -- the two artifacts are from different runs"
            )
        task = str(detail.get("task") or prediction.get("task") or "")
        text = str(prediction.get("prediction") or "")
        rows.append(
            {
                "record_type": RECORD_TYPE_EXAMPLE,
                "example_id": example_id,
                "task": task,
                "category": detail.get("category"),
                "bucket": detail.get("bucket"),
                "tier1_pass": bool(detail.get("passed")),
                "tier1_reason": detail.get("reason"),
                "prediction": text,
                "cited": _cited_records(text, task, corpus),
                "human_label": "",
                "human_note": "",
            }
        )
    return rows


@dataclass(frozen=True, slots=True)
class SheetMeta:
    """Provenance of a labeling sheet; the first line of the sheet JSONL."""

    run_id: str
    scoring_version: str
    seed: int
    requested_size: int
    sample_size: int
    generated_utc: str
    predictions_path: str
    scores_path: str
    corpus_sha256: str | None
    eval_set_sha256: str | None

    def to_row(self) -> dict[str, Any]:
        return {
            "record_type": RECORD_TYPE_META,
            "run_id": self.run_id,
            "scoring_version": self.scoring_version,
            "seed": self.seed,
            "requested_size": self.requested_size,
            "sample_size": self.sample_size,
            "generated_utc": self.generated_utc,
            "predictions_path": self.predictions_path,
            "scores_path": self.scores_path,
            "corpus_sha256": self.corpus_sha256,
            "eval_set_sha256": self.eval_set_sha256,
            "allowed_labels": list(ALLOWED_LABELS),
            "instructions": SHEET_INSTRUCTIONS,
        }


def write_sheet(path: Path, meta: SheetMeta, rows: Sequence[Mapping[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(meta.to_row(), ensure_ascii=False, sort_keys=True) + "\n")
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")
    return path


def _md_quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.strip().splitlines()) or ">"


def render_sheet_markdown(meta: SheetMeta, rows: Sequence[Mapping[str, Any]]) -> str:
    """Human-readable companion to the JSONL sheet.

    Labels are written back into the JSONL, not here: one machine-readable
    source of truth avoids a sheet whose two halves disagree. This file is
    the reading surface.
    """
    lines: list[str] = [
        f"# Tier-1 calibration sheet -- scoring_version {meta.scoring_version}",
        "",
        f"Run `{meta.run_id}` | {meta.sample_size} examples | seed {meta.seed} | "
        f"generated {meta.generated_utc}",
        "",
        SHEET_INSTRUCTIONS,
        "",
        "Write your verdict into the `human_label` field of the matching "
        "`example_id` line in the sheet JSONL next to this file "
        f"(allowed: {', '.join(ALLOWED_LABELS)}), then run "
        "`python -m stoic_training.calibrate ingest --sheet <that file>`.",
        "",
        "Judge only whether the cited record supports the claim. The scorer's own "
        "verdict is shown so you can see where it disagrees with you -- it is not "
        "a hint about the right answer.",
        "",
    ]
    for index, row in enumerate(rows, start=1):
        verdict = "PASS" if row.get("tier1_pass") else "FAIL"
        lines += [
            f"## {index}. `{row.get('example_id')}` -- {row.get('task')} "
            f"[tier1 {verdict}: {row.get('bucket')}]",
            "",
            "**Prediction**",
            "",
            _md_quote(str(row.get("prediction") or "")),
            "",
        ]
        cited = row.get("cited") or []
        if not cited:
            lines += ["**Cited record:** none -- the prediction cites nothing.", ""]
        for citation in cited:
            header = f"**Cited record:** `{citation.get('video_id')} {citation.get('hms')}`"
            if not citation.get("in_corpus"):
                lines += [f"{header} -- NOT IN CORPUS (nothing to compare against).", ""]
                continue
            lines += [header, "", "*narration*", ""]
            lines += [_md_quote(str(citation.get("narration") or ""))]
            lines += ["", "*why*", "", _md_quote(str(citation.get("why") or "")), ""]
        lines += [f"`human_label:` ______  ({' / '.join(ALLOWED_LABELS)})", "", "---", ""]
    return "\n".join(lines) + "\n"


def load_run_artifacts(run_dir: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read `<run_dir>/evaluation/{scores.json,predictions.jsonl}`."""
    run_dir = Path(run_dir)
    scores_path = run_dir / "evaluation" / "scores.json"
    predictions_path = run_dir / "evaluation" / "predictions.jsonl"
    for path in (scores_path, predictions_path):
        if not path.is_file():
            raise CalibrationError(
                f"missing {path}. `calibrate sample` needs a run dir whose evaluation "
                "artifacts were written by the current evaluate.py (--run-dir mode)."
            )
    try:
        scores = json.loads(scores_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CalibrationError(f"invalid JSON in {scores_path}: {exc}") from exc
    if not isinstance(scores, dict):
        raise CalibrationError(f"{scores_path} must contain a JSON object")
    return scores, _read_jsonl(predictions_path)


def cmd_sample(args: argparse.Namespace) -> int:
    scores, predictions = load_run_artifacts(args.run_dir)
    scoring_version = str(scores.get("scoring_version") or evaluate_mod.SCORING_VERSION)
    details = (scores.get("eval") or {}).get("details") or []
    if not details:
        raise CalibrationError(
            f"{Path(args.run_dir) / 'evaluation' / 'scores.json'} has no eval.details "
            "rows to sample from"
        )

    corpus = evaluate_mod.load_corpus(args.corpus)
    predictions_by_id = {
        evaluate_mod.example_id_for_record(row): row for row in predictions
    }

    selected = select_examples(details, size=args.size, seed=args.seed)
    rows = build_sheet_rows(selected, predictions_by_id, corpus)

    default_out_dir = Path(args.run_dir) / "evaluation" / "calibration"
    out_dir = Path(args.out_dir) if args.out_dir else default_out_dir
    stem = args.name or f"sheet-{scoring_version}"
    meta = SheetMeta(
        run_id=str(scores.get("run_id") or Path(args.run_dir).resolve().name),
        scoring_version=scoring_version,
        seed=args.seed,
        requested_size=args.size,
        sample_size=len(rows),
        generated_utc=datetime.now(UTC).isoformat(),
        predictions_path=str((Path(args.run_dir) / "evaluation" / "predictions.jsonl").resolve()),
        scores_path=str((Path(args.run_dir) / "evaluation" / "scores.json").resolve()),
        corpus_sha256=scores.get("corpus_sha256"),
        eval_set_sha256=scores.get("eval_set_sha256"),
    )
    sheet_path = write_sheet(out_dir / f"{stem}.jsonl", meta, rows)
    md_path = out_dir / f"{stem}.md"
    md_path.write_text(render_sheet_markdown(meta, rows), encoding="utf-8")

    strata: dict[str, int] = {}
    for row in rows:
        stratum = evaluate_mod.BUCKET_PASS if row["tier1_pass"] else str(row["bucket"])
        strata[stratum] = strata.get(stratum, 0) + 1
    print(f"sampled {len(rows)} of {args.size} requested from {len(details)} scored examples")
    for stratum in sorted(strata):
        print(f"  {stratum:<28}{strata[stratum]:>5}")
    print(f"sheet:    {sheet_path}")
    print(f"markdown: {md_path}")
    print(f'next: label human_label ({"/".join(ALLOWED_LABELS)}) in the sheet, then')
    print(f"      python -m stoic_training.calibrate ingest --sheet {sheet_path}")
    return 0


# --------------------------------------------------------------------------
# ingest
# --------------------------------------------------------------------------


def read_sheet(path: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = _read_jsonl(path)
    if not rows:
        raise CalibrationError(f"{path} is empty")
    meta = rows[0]
    if meta.get("record_type") != RECORD_TYPE_META:
        raise CalibrationError(f"{path}: first line must be the record_type=meta header")
    examples = [row for row in rows[1:] if row.get("record_type") == RECORD_TYPE_EXAMPLE]
    if not examples:
        raise CalibrationError(f"{path}: no record_type=example rows")
    return meta, examples


def _rate(numerator: int, denominator: int) -> float | None:
    return (numerator / denominator) if denominator else None


def compute_agreement(examples: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Tier-1 agreement against the human labels.

    Human "supported" is ground truth positive; the Tier-1 *pass* verdict is
    the prediction under test. "unsure" rows are excluded from every rate and
    reported separately -- folding them in either direction would invent a
    judgement the labeler explicitly declined to make.

        precision       = TP / (TP + FP)   of what Tier-1 passed, how much
                                            the human agrees is supported
        recall          = TP / (TP + FN)   of what is genuinely supported,
                                            how much Tier-1 passed
        false_fail_rate = FN / (TP + FN)   = 1 - recall; the headline error
                                            bar of design doc section 2
        false_pass_rate = FP / (FP + TN)   of what is genuinely unsupported,
                                            how much Tier-1 let through
        agreement       = (TP + TN) / labeled

    Rates are None (not 0.0) when their denominator is empty: "no supported
    examples were sampled" and "zero false-fail rate" are different facts.
    """
    counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    unsure = 0
    unlabeled = 0
    invalid: list[str] = []
    per_bucket: dict[str, dict[str, int]] = {}

    for row in examples:
        label = str(row.get("human_label") or "").strip().lower()
        bucket = str(row.get("bucket") or "unknown")
        bucket_counts = per_bucket.setdefault(
            bucket,
            {"total": 0, "tier1_pass": 0, **dict.fromkeys(ALLOWED_LABELS, 0), "unlabeled": 0},
        )
        bucket_counts["total"] += 1
        tier1_pass = bool(row.get("tier1_pass"))
        if tier1_pass:
            bucket_counts["tier1_pass"] += 1

        if not label:
            unlabeled += 1
            bucket_counts["unlabeled"] += 1
            continue
        if label not in ALLOWED_LABELS:
            invalid.append(f"{row.get('example_id')}={label!r}")
            continue
        bucket_counts[label] += 1
        if label == LABEL_UNSURE:
            unsure += 1
            continue
        supported = label == LABEL_SUPPORTED
        if tier1_pass and supported:
            counts["tp"] += 1
        elif tier1_pass and not supported:
            counts["fp"] += 1
        elif not tier1_pass and supported:
            counts["fn"] += 1
        else:
            counts["tn"] += 1

    if invalid:
        raise CalibrationError(
            "invalid human_label values (allowed: "
            f"{', '.join(ALLOWED_LABELS)}): {', '.join(sorted(invalid))}"
        )

    tp, fp, fn, tn = counts["tp"], counts["fp"], counts["fn"], counts["tn"]
    scored = tp + fp + fn + tn
    return {
        "counts": {**counts, "unsure": unsure, "unlabeled": unlabeled, "scored": scored},
        "precision": _rate(tp, tp + fp),
        "recall": _rate(tp, tp + fn),
        "false_fail_rate": _rate(fn, tp + fn),
        "false_pass_rate": _rate(fp, fp + tn),
        "agreement": _rate(tp + tn, scored),
        "per_bucket": {bucket: per_bucket[bucket] for bucket in sorted(per_bucket)},
    }


def build_calibration_record(
    *,
    meta: Mapping[str, Any],
    sheet_path: Path,
    agreement: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    return {
        "scoring_version": str(meta.get("scoring_version") or ""),
        "run_id": meta.get("run_id"),
        "date": (now or datetime.now(UTC)).isoformat(),
        "sheet": {
            "path": str(sheet_path.resolve()),
            "sha256": sha256_file(sheet_path),
            "seed": meta.get("seed"),
            "sample_size": meta.get("sample_size"),
            "generated_utc": meta.get("generated_utc"),
        },
        "corpus_sha256": meta.get("corpus_sha256"),
        "eval_set_sha256": meta.get("eval_set_sha256"),
        "agreement": dict(agreement),
    }


def cmd_ingest(args: argparse.Namespace) -> int:
    sheet_path = Path(args.sheet)
    meta, examples = read_sheet(sheet_path)
    agreement = compute_agreement(examples)
    scoring_version = str(meta.get("scoring_version") or "")
    if not scoring_version:
        raise CalibrationError(f"{sheet_path}: meta row has no scoring_version")

    out_path = (
        Path(args.out)
        if args.out
        else Path(args.calibration_dir) / f"{scoring_version}.json"
    )
    if out_path.exists() and not args.force:
        raise CalibrationError(
            f"{out_path} already exists. A calibration record is the committed error "
            "bar for scoring_version "
            f"{scoring_version}; silently replacing it would erase the lineage it "
            "exists to keep. Re-run with --force to overwrite deliberately, or bump "
            "SCORING_VERSION if the metric itself changed."
        )

    record = build_calibration_record(meta=meta, sheet_path=sheet_path, agreement=agreement)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    counts = agreement["counts"]
    print(
        f"labeled {counts['scored']} (unsure {counts['unsure']}, "
        f"unlabeled {counts['unlabeled']})"
    )
    for key in ("precision", "recall", "false_fail_rate", "false_pass_rate", "agreement"):
        value = agreement[key]
        print(f"  {key:<18}{'n/a' if value is None else f'{value:.3f}'}")
    print(f"calibration record: {out_path}")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Human calibration audit of the Tier-1 scoring proxy."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sample = sub.add_parser("sample", help="Draw a stratified labeling sheet from a run dir")
    sample.add_argument("--run-dir", type=Path, required=True)
    sample.add_argument("--size", type=int, default=DEFAULT_SAMPLE_SIZE)
    sample.add_argument("--seed", type=int, default=DEFAULT_SEED)
    sample.add_argument("--corpus", type=Path, default=evaluate_mod.DEFAULT_CORPUS_PATH)
    sample.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Default: <run-dir>/evaluation/calibration/",
    )
    sample.add_argument(
        "--name", default=None, help="Sheet stem (default: sheet-<scoring_version>)"
    )
    sample.set_defaults(func=cmd_sample)

    ingest = sub.add_parser("ingest", help="Score a filled sheet into a calibration record")
    ingest.add_argument("--sheet", type=Path, required=True)
    ingest.add_argument(
        "--calibration-dir",
        type=Path,
        default=DEFAULT_CALIBRATION_DIR,
        help="Committed calibration dir (default: training/win_cuda/evaluation/calibration)",
    )
    ingest.add_argument("--out", type=Path, default=None, help="Explicit record path")
    ingest.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing calibration record for this scoring_version",
    )
    ingest.set_defaults(func=cmd_ingest)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return int(args.func(args))
    except (CalibrationError, evaluate_mod.EvaluationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
