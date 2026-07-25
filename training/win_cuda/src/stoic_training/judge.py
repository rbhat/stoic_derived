"""Tier-2 advisory LLM judge for the offline research-assistant SLM.

Purpose guardrail: this evaluates an OFFLINE research assistant that
proposes cited rule candidates for human review; its output never touches
any live trading path.

Design doc (`docs/superpowers/specs/2026-07-24-eval-comparison-design.md`)
section 2 defines this as Tier 2: "local pinned LLM judge (temp 0, pinned
prompt+model+revision) scoring semantic support; advisory only; never
gates, never compared across judge versions." Tier 0/1 stay purely
deterministic in `evaluate.py`; this module never changes, wraps, or feeds
into that scoring. **`compare.py` stays untouched and this module is never
imported by it** -- section 7's non-goal is explicit ("No LLM judge as a
blocking metric"), and the reason is structural, not just policy: a display
section inside `compare.py` is one refactor away from becoming a decision
input. Judge output lives in its own `<run_dir>/evaluation/judge/` tree and
is read (if at all) by a human, never by another program that gates on it.

A "judge_version" is a pinning receipt: it hashes together the judge model
repo_id, revision, the pinned prompt template, and the deterministic
decoding params, so two judge runs are comparable to each other only when
every one of those matches. Judgements from different judge_versions must
never be aggregated or co-mingled (`assert_single_judge_version`,
`guard_existing_outputs`) -- an "advisory" number that silently drifted
because the prompt or the judge model changed underneath it would be worse
than no number at all.

Heavy imports (torch/transformers) are deferred into functions, mirroring
`infer.py`, so importing this module stays cheap, needs no GPU, and pulls
in nothing beyond stdlib + `stoic_training.evaluate`. Per design doc
section 6 ("any code path that touches transformers generation APIs gets a
stub-based regression test" -- the lesson from the `apply_chat_template`
BatchEncoding crash of 2026-07-25), `judge_targets` is exercised in
`tests/test_judge.py` against a stub model/tokenizer that reproduces that
exact hazard, because it calls `infer.generate_one` the same way `infer.py`
itself does.

CLI: `python -m stoic_training.judge --run-dir DIR --judge-repo-id ID
--judge-revision SHA [--corpus PATH] [--max-new-tokens N] [--limit N]
[--out-dir DIR] [--force] [--dry-run]`. Reads an existing run's
`evaluation/predictions.jsonl` (and `evaluation/scores.json`, if present,
for digest metadata only) and writes `evaluation/judge/{judgements.jsonl,
summary.json}`. Exit 0 ok, 1 usage/IO (`JudgeError`/
`evaluate.EvaluationError`), 2 a guard refusal (`JudgeRefusal`).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from stoic_training import evaluate as evaluate_mod

JUDGE_VERSION_SCHEME = "1"
# ASCII unit separator, matching evaluate.EXAMPLE_ID_SEPARATOR: cannot occur
# in any of the framed fields below, so it safely disambiguates them.
_JUDGE_VERSION_SEPARATOR = "\x1f"

DEFAULT_JUDGE_MAX_NEW_TOKENS = 64

VERDICT_SUPPORTED = "supported"
VERDICT_NOT_SUPPORTED = "not_supported"
VERDICT_UNCLEAR = "unclear"
VERDICT_UNPARSEABLE = "unparseable"
VERDICTS = (VERDICT_SUPPORTED, VERDICT_NOT_SUPPORTED, VERDICT_UNCLEAR, VERDICT_UNPARSEABLE)

SKIP_CONFLICT_TASK = "conflict_task"
SKIP_NO_CITATION = "no_citation"
SKIP_CITATION_NOT_IN_CORPUS = "citation_not_in_corpus"
SKIP_EMPTY_CLAIM = "empty_claim"

JUDGE_DIR_NAME = "judge"
JUDGEMENTS_NAME = "judgements.jsonl"
SUMMARY_NAME = "summary.json"

EXIT_REFUSED = 2


class JudgeError(RuntimeError):
    """Raised on usage/IO problems (missing files, malformed JSON). Exit 1."""


class JudgeRefusal(RuntimeError):
    """Raised when a guard is violated (unpinned judge, mixed judge_versions,
    mismatched existing output). Exit 2."""


# Changing this string changes `judge_version` (compute_judge_version hashes
# its sha256) -- that is the point. The prompt is the pinned half of "pinned
# prompt+model+revision" (design doc section 2); editing it deliberately
# starts a new, non-comparable judge lineage, exactly like bumping
# evaluate.SCORING_VERSION starts a new Tier-1 lineage.
JUDGE_PROMPT_TEMPLATE = (
    "You are auditing a claim made by an offline research assistant against "
    "a single excerpt from an educational trading course. Judge ONLY "
    "whether the excerpt semantically supports the claim -- ignore style, "
    "wording, and grammar differences between the claim and the excerpt.\n"
    "\n"
    "Course excerpt ({video_id} {hms}):\n"
    "{narration}\n"
    "\n"
    "Claim to check:\n"
    "{claim}\n"
    "\n"
    "Reply with exactly one line, choosing exactly one of:\n"
    "VERDICT: supported\n"
    "VERDICT: not_supported\n"
    "VERDICT: unclear\n"
    "You may add one short reason line after the VERDICT line. Nothing "
    "else.\n"
)

_VERDICT_LINE_RE = re.compile(r"verdict\s*:\s*(.+)", re.IGNORECASE)
_VERDICT_TOKENS = {
    VERDICT_SUPPORTED: VERDICT_SUPPORTED,
    VERDICT_NOT_SUPPORTED: VERDICT_NOT_SUPPORTED,
    VERDICT_UNCLEAR: VERDICT_UNCLEAR,
}


def prompt_template_sha256(template: str = JUDGE_PROMPT_TEMPLATE) -> str:
    return sha256(template.encode("utf-8")).hexdigest()


def compute_judge_version(
    *,
    repo_id: str,
    revision: str,
    max_new_tokens: int = DEFAULT_JUDGE_MAX_NEW_TOKENS,
    prompt_template: str = JUDGE_PROMPT_TEMPLATE,
) -> str:
    """sha256 of explicitly framed, \\x1f-separated fields (mirrors
    `evaluate.example_id`'s framing style), as `f"{scheme}-{digest[:16]}"`.

    Raises `JudgeRefusal` when repo_id or revision is empty: an unpinned
    judge produces numbers that cannot be reproduced, and pinning
    model+revision+prompt is the entire tier-2 contract (design doc
    section 2).
    """
    if not repo_id or not revision:
        raise JudgeRefusal(
            "judge repo_id and revision must both be non-empty. An unpinned judge "
            "produces numbers nobody can reproduce -- pinning model+revision+prompt "
            "is the entire tier-2 contract (design doc section 2)."
        )
    payload = _JUDGE_VERSION_SEPARATOR.join(
        (
            f"scheme={JUDGE_VERSION_SCHEME}",
            f"repo_id={repo_id}",
            f"revision={revision}",
            f"prompt_sha256={prompt_template_sha256(prompt_template)}",
            "do_sample=False",
            "temperature=0",
            f"max_new_tokens={max_new_tokens}",
        )
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()
    return f"{JUDGE_VERSION_SCHEME}-{digest[:16]}"


def build_judge_messages(
    *, claim: str, narration: str, video_id: str, hms: str
) -> list[dict[str, str]]:
    """A single pinned user message; no system message, kept minimal and pinned."""
    content = JUDGE_PROMPT_TEMPLATE.format(
        claim=claim, narration=narration, video_id=video_id, hms=hms
    )
    return [{"role": "user", "content": content}]


def parse_verdict(text: str) -> str:
    """Case-insensitive search for the first `VERDICT:` line.

    Strict on purpose: a bare "supported" with no `VERDICT:` prefix is
    `unparseable`, not `supported` -- the model is required to use the
    pinned reply format, not merely to sound affirmative. The token after
    `VERDICT:` is compared as a whole word, so `not_supported` can never be
    mis-read as `supported` via a substring match.
    """
    for line in text.splitlines():
        match = _VERDICT_LINE_RE.search(line.strip())
        if not match:
            continue
        remainder = match.group(1).strip()
        if not remainder:
            return VERDICT_UNPARSEABLE
        token = remainder.split()[0].strip().rstrip(".,;:").lower()
        return _VERDICT_TOKENS.get(token, VERDICT_UNPARSEABLE)
    return VERDICT_UNPARSEABLE


@dataclass(frozen=True, slots=True)
class JudgeTarget:
    example_id: str
    task: str
    video_id: str
    hms: str
    claim: str
    narration: str


def select_targets(
    predictions: Sequence[Mapping[str, Any]], corpus: evaluate_mod.CorpusIndex
) -> tuple[list[JudgeTarget], list[dict[str, Any]]]:
    """Split predictions into judgeable targets and skipped rows.

    Skip precedence (first match wins), each recorded with its own reason:
    `conflict_check` rows first (a conflict answer cites two records; there
    is no single narration to judge against), then no trailing citation,
    then a citation absent from the corpus, then an empty claim body. Every
    input prediction lands in exactly one of the two returned lists.
    """
    targets: list[JudgeTarget] = []
    skipped: list[dict[str, Any]] = []

    for prediction in predictions:
        example_id = evaluate_mod.example_id_for_record(prediction)
        task = prediction.get("task") or ""

        if task == evaluate_mod.CONFLICT_TASK:
            skipped.append({"example_id": example_id, "task": task, "skipped": SKIP_CONFLICT_TASK})
            continue

        prediction_text = prediction.get("prediction") or ""
        citation = evaluate_mod.trailing_citation(prediction_text)
        if citation is None:
            skipped.append({"example_id": example_id, "task": task, "skipped": SKIP_NO_CITATION})
            continue

        record = corpus.get(citation)
        if record is None:
            skipped.append(
                {"example_id": example_id, "task": task, "skipped": SKIP_CITATION_NOT_IN_CORPUS}
            )
            continue

        claim = evaluate_mod.citation_body(prediction_text)
        if not claim.strip():
            skipped.append({"example_id": example_id, "task": task, "skipped": SKIP_EMPTY_CLAIM})
            continue

        video_id, hms = citation
        narration = record.narration
        if record.why:
            narration = f"{narration}\n\nWhy: {record.why}"

        targets.append(
            JudgeTarget(
                example_id=example_id,
                task=task,
                video_id=video_id,
                hms=hms,
                claim=claim,
                narration=narration,
            )
        )

    return targets, skipped


def judge_targets(
    targets: Sequence[JudgeTarget],
    *,
    model: Any,
    tokenizer: Any,
    judge_version: str,
    max_new_tokens: int = DEFAULT_JUDGE_MAX_NEW_TOKENS,
    progress_cb: Callable[[int, int], None] | None = None,
) -> list[dict[str, Any]]:
    """Judge each target with an ALREADY-LOADED model/tokenizer (stub-testable).

    Calls `stoic_training.infer.generate_one` (deferred import) per target,
    the same deterministic (do_sample=False, temperature=None) path
    `infer.py` uses for prediction generation. Output order matches input
    order; sorting is the caller's job.
    """
    from stoic_training.infer import generate_one

    total = len(targets)
    rows: list[dict[str, Any]] = []
    for completed, target in enumerate(targets, start=1):
        messages = build_judge_messages(
            claim=target.claim, narration=target.narration, video_id=target.video_id, hms=target.hms
        )
        raw = generate_one(model, tokenizer, messages, max_new_tokens=max_new_tokens)
        rows.append(
            {
                "example_id": target.example_id,
                "task": target.task,
                "video_id": target.video_id,
                "hms": target.hms,
                "verdict": parse_verdict(raw),
                "judge_raw": raw,
                "judge_version": judge_version,
            }
        )
        if progress_cb is not None:
            progress_cb(completed, total)
    return rows


def load_judge_model(repo_id: str, revision: str):
    """Load the pinned judge model 4-bit. Mirrors
    `infer.load_base_model_and_tokenizer`."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from stoic_training.infer import build_quantization_config

    quant_config = build_quantization_config()
    model = AutoModelForCausalLM.from_pretrained(
        repo_id,
        revision=revision,
        quantization_config=quant_config,
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
    )
    tokenizer = AutoTokenizer.from_pretrained(repo_id, revision=revision)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model.eval()
    return model, tokenizer


def assert_single_judge_version(rows: Iterable[Mapping[str, Any]]) -> str:
    """Refuse (JudgeRefusal) unless every row carries the same, present
    `judge_version` -- the "no cross-judge-version aggregation" guard.

    Empty input also refuses: there is no single judge_version to assert
    when there are no rows to assert it about.
    """
    row_list = list(rows)
    if not row_list:
        raise JudgeRefusal(
            "no judgement rows given: there is no judge_version to assert, and an "
            "aggregation over zero judged rows cannot be attributed to any judge."
        )
    versions = {row.get("judge_version") for row in row_list}
    if len(versions) != 1 or None in versions:
        raise JudgeRefusal(
            "judgement rows carry more than one judge_version "
            f"({sorted(str(v) for v in versions)!r}); judge outputs from different "
            "judge_versions are not comparable and must never be aggregated together "
            "(design doc section 2)."
        )
    return next(iter(versions))


def summarize(
    rows: Sequence[Mapping[str, Any]],
    skipped: Sequence[Mapping[str, Any]],
    *,
    judge_version: str,
    run_id: str,
    repo_id: str,
    revision: str,
    max_new_tokens: int,
    scores: Mapping[str, Any] | None,
    limit: int | None,
) -> dict[str, Any]:
    """Advisory summary. Never gates; never comparable across judge_versions."""
    verdict_counts: dict[str, int] = dict.fromkeys(VERDICTS, 0)
    for row in rows:
        verdict = row.get("verdict")
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1

    judged = len(rows)
    verdict_rates = {
        verdict: (count / judged if judged else None) for verdict, count in verdict_counts.items()
    }

    skip_counts: dict[str, int] = {}
    for row in skipped:
        reason = str(row.get("skipped") or "unknown")
        skip_counts[reason] = skip_counts.get(reason, 0) + 1
    skipped_total = len(skipped)

    summary: dict[str, Any] = {
        "judge_version": judge_version,
        "judge_model": {"repo_id": repo_id, "revision": revision},
        "prompt_sha256": prompt_template_sha256(),
        "decoding": {"do_sample": False, "temperature": None, "max_new_tokens": max_new_tokens},
        "verdict_counts": verdict_counts,
        "verdict_rates": verdict_rates,
        "skip_counts": skip_counts,
        "judged": judged,
        "skipped_total": skipped_total,
        "predictions_total": judged + skipped_total,
        "run_id": run_id,
        "generated_utc": datetime.now(UTC).isoformat(),
        "subset": limit is not None,
        "advisory": (
            "Tier-2 judge output is advisory only: it never gates a run, and it must "
            "never be compared or aggregated across judge_versions (design doc "
            "section 2 / section 7 -- 'No LLM judge as a blocking metric')."
        ),
    }
    if limit is not None:
        summary["limit"] = limit
    if scores:
        for key in ("corpus_sha256", "eval_set_sha256", "scoring_version"):
            if key in scores:
                summary[key] = scores[key]
    return summary


def read_existing_summary(out_dir: str | Path) -> dict[str, Any] | None:
    path = Path(out_dir) / SUMMARY_NAME
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise JudgeError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise JudgeError(f"{path}: must contain a JSON object")
    return payload


def guard_existing_outputs(out_dir: str | Path, judge_version: str, *, force: bool) -> None:
    """Refuse to overwrite a `summary.json` from a DIFFERENT judge_version.

    Same judge_version is allowed silently (a rerun is deterministic, so it
    reproduces the same numbers). `force` bypasses the refusal to
    deliberately discard a different-version output.
    """
    existing = read_existing_summary(out_dir)
    if existing is None:
        return
    existing_version = existing.get("judge_version")
    if existing_version == judge_version or force:
        return
    raise JudgeRefusal(
        f"{Path(out_dir) / SUMMARY_NAME} already holds judge_version {existing_version!r}, "
        f"but this run is judge_version {judge_version!r}. Judge outputs from different "
        "judge_versions are not comparable and must not be co-mingled in the same "
        "out-dir. Point --out-dir at a fresh directory for a side-by-side comparison, "
        "or pass --force only to deliberately discard the existing output."
    )


def write_outputs(
    out_dir: str | Path,
    rows: Sequence[Mapping[str, Any]],
    skipped: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
) -> tuple[Path, Path]:
    """Write `judgements.jsonl` (judged rows, then skipped rows -- so the file
    accounts for every prediction) and `summary.json`."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    judgements_path = out_dir / JUDGEMENTS_NAME
    with judgements_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
        for row in skipped:
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")

    summary_path = out_dir / SUMMARY_NAME
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return judgements_path, summary_path


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
                raise JudgeError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise JudgeError(f"{path}:{line_number}: record must be an object")
            rows.append(payload)
    return rows


def load_run_predictions(run_dir: str | Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Read `<run_dir>/evaluation/{predictions.jsonl,scores.json}`.

    `predictions.jsonl` is required (JudgeError if missing); `scores.json`
    is optional digest metadata only and is None when absent.
    """
    run_dir = Path(run_dir)
    predictions_path = run_dir / "evaluation" / "predictions.jsonl"
    if not predictions_path.is_file():
        raise JudgeError(
            f"missing {predictions_path}. stoic_training.judge needs a run dir whose "
            "evaluation artifacts were written by evaluate.py (--run-dir mode)."
        )
    predictions = _read_jsonl(predictions_path)

    scores_path = run_dir / "evaluation" / "scores.json"
    scores: dict[str, Any] | None = None
    if scores_path.is_file():
        try:
            scores = json.loads(scores_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise JudgeError(f"{scores_path}: invalid JSON: {exc}") from exc
        if not isinstance(scores, dict):
            raise JudgeError(f"{scores_path}: must contain a JSON object")
    return scores, predictions


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tier-2 advisory LLM judge: pinned prompt+model+revision, scoring "
        "semantic claim-vs-narration support. Advisory only -- never gates, never "
        "compared across judge_versions."
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--judge-repo-id",
        required=True,
        help="HF repo id of the judge model (pinning is non-optional)",
    )
    parser.add_argument(
        "--judge-revision",
        required=True,
        help="HF revision/sha of the judge model (pinning is non-optional)",
    )
    parser.add_argument("--corpus", type=Path, default=evaluate_mod.DEFAULT_CORPUS_PATH)
    parser.add_argument("--max-new-tokens", type=int, default=DEFAULT_JUDGE_MAX_NEW_TOKENS)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Judge only the first N targets (stamped subset in the summary)",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=None, help="Default: <run-dir>/evaluation/judge/"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing summary.json from a different judge_version",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Select targets and compute judge_version; load no model, write no files",
    )
    return parser.parse_args(argv)


_ADVISORY_BANNER = (
    "ADVISORY: Tier-2 judge output never gates a run and must never be compared "
    "across judge_versions."
)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        judge_version = compute_judge_version(
            repo_id=args.judge_repo_id,
            revision=args.judge_revision,
            max_new_tokens=args.max_new_tokens,
        )
        out_dir = (
            args.out_dir
            if args.out_dir is not None
            else args.run_dir / "evaluation" / JUDGE_DIR_NAME
        )

        scores, predictions = load_run_predictions(args.run_dir)
        corpus = evaluate_mod.load_corpus(args.corpus)
        targets, skipped = select_targets(predictions, corpus)

        if args.limit is not None:
            targets = targets[: args.limit]

        skip_counts: dict[str, int] = {}
        for row in skipped:
            reason = str(row.get("skipped") or "unknown")
            skip_counts[reason] = skip_counts.get(reason, 0) + 1

        if args.dry_run:
            print(f"judge_version: {judge_version}")
            print(f"prompt_sha256: {prompt_template_sha256()}")
            print(f"would judge:   {len(targets)} of {len(predictions)} predictions")
            print(f"skipped:       {len(skipped)}")
            for reason in sorted(skip_counts):
                print(f"  {reason:<28}{skip_counts[reason]:>5}")
            print(f"out_dir:       {out_dir}")
            print(_ADVISORY_BANNER + " (dry run: no model loaded, no files written.)")
            return 0

        guard_existing_outputs(out_dir, judge_version, force=args.force)

        # Before the deferred transformers import, which reads HF_HOME at
        # import time; keeps judge inference on the migrated base-model
        # cache. Not called in --dry-run, which loads no model.
        from stoic_training.config import ensure_hf_home

        ensure_hf_home()

        model, tokenizer = load_judge_model(args.judge_repo_id, args.judge_revision)
        rows = judge_targets(
            targets,
            model=model,
            tokenizer=tokenizer,
            judge_version=judge_version,
            max_new_tokens=args.max_new_tokens,
        )

        summary = summarize(
            rows,
            skipped,
            judge_version=judge_version,
            run_id=Path(args.run_dir).resolve().name,
            repo_id=args.judge_repo_id,
            revision=args.judge_revision,
            max_new_tokens=args.max_new_tokens,
            scores=scores,
            limit=args.limit,
        )
        judgements_path, summary_path = write_outputs(out_dir, rows, skipped, summary)

        print(f"judge_version: {judge_version}")
        print(f"judged:        {summary['judged']} / {summary['predictions_total']}")
        for verdict in VERDICTS:
            rate = summary["verdict_rates"].get(verdict)
            rate_str = "n/a" if rate is None else f"{rate:.3f}"
            print(f"  {verdict:<16}{summary['verdict_counts'].get(verdict, 0):>5}  ({rate_str})")
        print(f"judgements:    {judgements_path}")
        print(f"summary:       {summary_path}")
        print(_ADVISORY_BANNER)
        return 0
    except JudgeRefusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except (JudgeError, evaluate_mod.EvaluationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
