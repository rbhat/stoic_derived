"""Tests for calibrate.py, plus the evaluate.py unseal guard (design doc 5.2).

CPU-only, no torch import anywhere in this suite, no mocks. Sampling/ingest
round trips are built from a synthetic corpus + hand-written predictions
scored by the real evaluate.main() into a tmp_path run dir; the confusion
matrix and rate-formula tests build sheet rows by hand as plain dicts so the
expected numbers can be hand-computed alongside the assertion. The unseal
guard is exercised purely through evaluate.main()'s exit codes and ledger
side effects against a real v2 dataset built with build_dataset + splits --
no model, no generation.
"""

from __future__ import annotations

import json
import shutil

import pytest
from stoic_training import build_dataset, calibrate, evaluate, splits

# --------------------------------------------------------------------------
# allocate_sample
# --------------------------------------------------------------------------


def test_allocate_sample_honours_roughly_50_50_pass_fail():
    strata = {"pass": 100, "weak_overlap": 50, "no_citation": 50}
    allocation = calibrate.allocate_sample(strata, 20)
    assert sum(allocation.values()) == 20
    assert allocation["pass"] == 10
    fail_total = allocation.get("weak_overlap", 0) + allocation.get("no_citation", 0)
    assert fail_total == 10


def test_allocate_sample_spreads_fail_half_across_buckets_capped_by_availability():
    strata = {"pass": 100, "weak_overlap": 2, "no_citation": 1}
    allocation = calibrate.allocate_sample(strata, 20)
    assert sum(allocation.values()) == 20
    assert allocation.get("weak_overlap", 0) <= 2
    assert allocation.get("no_citation", 0) <= 1


def test_allocate_sample_empty_for_non_positive_total_or_empty_strata():
    assert calibrate.allocate_sample({"pass": 10}, 0) == {}
    assert calibrate.allocate_sample({"pass": 10}, -5) == {}
    assert calibrate.allocate_sample({}, 20) == {}


def test_allocate_sample_total_exceeding_availability_returns_everything():
    strata = {"pass": 3, "weak_overlap": 2}
    allocation = calibrate.allocate_sample(strata, 100)
    assert allocation == {"pass": 3, "weak_overlap": 2}


# --------------------------------------------------------------------------
# select_examples
# --------------------------------------------------------------------------


def _synthetic_details(n_pass=10, n_weak=6, n_no_citation=6):
    details = []
    for i in range(n_pass):
        details.append(
            {
                "example_id": f"pass-{i:02d}",
                "passed": True,
                "bucket": "pass",
                "task": "cited_qa",
                "category": "concept",
            }
        )
    for i in range(n_weak):
        details.append(
            {
                "example_id": f"weak-{i:02d}",
                "passed": False,
                "bucket": "weak_overlap",
                "task": "cited_qa",
                "category": "concept",
            }
        )
    for i in range(n_no_citation):
        details.append(
            {
                "example_id": f"noc-{i:02d}",
                "passed": False,
                "bucket": "no_citation",
                "task": "cited_qa",
                "category": "concept",
            }
        )
    return details


def test_select_examples_deterministic_for_fixed_seed():
    details = _synthetic_details()
    first = calibrate.select_examples(details, size=6, seed=42)
    second = calibrate.select_examples(details, size=6, seed=42)
    assert [d["example_id"] for d in first] == [d["example_id"] for d in second]


def test_select_examples_changes_for_different_seed():
    details = _synthetic_details()
    seed_a = calibrate.select_examples(details, size=6, seed=42)
    seed_b = calibrate.select_examples(details, size=6, seed=99)
    assert [d["example_id"] for d in seed_a] != [d["example_id"] for d in seed_b]


def test_select_examples_never_duplicates_and_respects_size():
    details = _synthetic_details()
    selected = calibrate.select_examples(details, size=6, seed=7)
    ids = [d["example_id"] for d in selected]
    assert len(ids) == len(set(ids))
    assert len(selected) == 6


# --------------------------------------------------------------------------
# sample -> ingest round trip on a synthetic run dir
# --------------------------------------------------------------------------


def _calibration_corpus_records():
    return [
        {
            "video_id": "c1",
            "hms": "00:00:00",
            "category": "concept",
            "label": "risk sizing",
            "narration": "Instructor explains position sizing using ATR and stop distance.",
            "why": "Position sizing controls risk per trade using ATR and stop distance.",
        },
        {
            "video_id": "c1",
            "hms": "00:00:30",
            "category": "concept",
            "label": "entry timing",
            "narration": "Wait for the retest of structure before committing to an entry.",
            "why": "The retest confirms structure before risk is committed to the trade.",
        },
        {
            "video_id": "c2",
            "hms": "00:00:00",
            "category": "concept",
            "label": "market structure",
            "narration": "Higher highs and higher lows define a clean uptrend context here.",
            "why": "An uptrend context favors long setups only in this framework.",
        },
        {
            "video_id": "cs1",
            "hms": "00:00:00",
            "category": "case_study",
            "label": "risk sizing",
            "narration": "Use half position size on gold due to elevated volatility spikes.",
            "why": "Gold's volatility spikes justify a reduced position size here.",
        },
    ]


def _write_calibration_corpus(tmp_path):
    path = tmp_path / "corpus.jsonl"
    records = _calibration_corpus_records()
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path, records


def _calibration_prediction_text(kind, record):
    if kind == "pass":
        return f"{record['why']}\nCitation: {record['video_id']} {record['hms']}"
    if kind == "hallucinated":
        return f"{record['why']}\nCitation: ghost_video 09:09:09"
    if kind == "no_citation":
        return "Some answer that never cites anything at all."
    if kind == "weak_overlap":
        return (
            "Totally unrelated zebra migration content about nothing relevant here.\n"
            f"Citation: {record['video_id']} {record['hms']}"
        )
    raise ValueError(kind)


def _build_sampled_sheet(tmp_path, *, size=8, seed=7, name=None):
    corpus_path, records = _write_calibration_corpus(tmp_path)
    run_dir = tmp_path / "runs" / "run1"
    (run_dir / "evaluation").mkdir(parents=True)

    kinds = ["pass", "hallucinated", "no_citation", "weak_overlap"]
    predictions = []
    for i in range(8):
        record = records[i % len(records)]
        kind = kinds[i % len(kinds)]
        predictions.append(
            {
                "task": "cited_qa",
                "meta": {
                    "video_id": record["video_id"],
                    "hms": record["hms"],
                    "category": record["category"],
                },
                "prompt": f"prompt #{i} about {record['label']}",
                "prediction": _calibration_prediction_text(kind, record),
            }
        )
    predictions_path = run_dir / "evaluation" / "predictions.jsonl"
    predictions_path.write_text(
        "\n".join(json.dumps(p) for p in predictions) + "\n", encoding="utf-8"
    )

    rc = evaluate.main(
        [
            "--predictions", str(predictions_path),
            "--corpus", str(corpus_path),
            "--run-dir", str(run_dir),
        ]
    )
    assert rc == 0

    args = [
        "sample",
        "--run-dir", str(run_dir),
        "--size", str(size),
        "--seed", str(seed),
        "--corpus", str(corpus_path),
    ]
    if name:
        args += ["--name", name]
    rc = calibrate.main(args)
    assert rc == 0

    stem = name or f"sheet-{evaluate.SCORING_VERSION}"
    sheet_path = run_dir / "evaluation" / "calibration" / f"{stem}.jsonl"
    md_path = run_dir / "evaluation" / "calibration" / f"{stem}.md"
    rows = [json.loads(line) for line in sheet_path.read_text().splitlines() if line.strip()]
    return {
        "corpus_path": corpus_path,
        "run_dir": run_dir,
        "sheet_path": sheet_path,
        "md_path": md_path,
        "meta": rows[0],
        "examples": rows[1:],
    }


def test_sample_round_trip_writes_sheet_with_expected_shape(tmp_path):
    ctx = _build_sampled_sheet(tmp_path)
    assert ctx["sheet_path"].is_file()
    assert ctx["md_path"].is_file()
    assert ctx["meta"]["record_type"] == "meta"
    assert ctx["meta"]["scoring_version"] == evaluate.SCORING_VERSION

    hallucinated_seen = False
    for row in ctx["examples"]:
        assert row["human_label"] == ""
        assert isinstance(row["prediction"], str) and row["prediction"]
        assert "cited" in row
        for citation in row["cited"]:
            if citation["in_corpus"]:
                assert citation["narration"]
                assert citation["why"]
            else:
                assert citation["narration"] is None
                assert citation["why"] is None
                hallucinated_seen = True
    assert hallucinated_seen, "expected at least one hallucinated (not-in-corpus) citation"


def test_sample_sheet_does_not_contain_eval_set_gold_answers(tmp_path):
    ctx = _build_sampled_sheet(tmp_path)
    gold_answer = "The wildly specific unique gold assistant answer about kumquats and lorem ipsum."
    eval_path = ctx["run_dir"] / "some_eval.jsonl"
    eval_row = {
        "task": "cited_qa",
        "meta": {"video_id": "c1", "hms": "00:00:00", "category": "concept"},
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": gold_answer},
        ],
    }
    eval_path.write_text(json.dumps(eval_row) + "\n", encoding="utf-8")

    sheet_text = ctx["sheet_path"].read_text(encoding="utf-8")
    assert gold_answer not in sheet_text


# --------------------------------------------------------------------------
# compute_agreement
# --------------------------------------------------------------------------


def test_compute_agreement_matches_hand_computed_confusion_matrix():
    examples = [
        {"example_id": "e1", "tier1_pass": True, "human_label": "supported"},
        {"example_id": "e2", "tier1_pass": True, "human_label": "supported"},
        {"example_id": "e3", "tier1_pass": True, "human_label": "not_supported"},
        {"example_id": "e4", "tier1_pass": False, "human_label": "supported"},
        {"example_id": "e5", "tier1_pass": False, "human_label": "not_supported"},
        {"example_id": "e6", "tier1_pass": False, "human_label": "unsure"},
    ]

    agreement = calibrate.compute_agreement(examples)
    counts = agreement["counts"]

    assert counts["tp"] == 2
    assert counts["fp"] == 1
    assert counts["fn"] == 1
    assert counts["tn"] == 1
    assert counts["unsure"] == 1
    assert agreement["precision"] == pytest.approx(2 / 3)
    assert agreement["recall"] == pytest.approx(2 / 3)
    assert agreement["false_fail_rate"] == pytest.approx(1 / 3)
    assert agreement["false_pass_rate"] == pytest.approx(1 / 2)
    # agreement = (tp + tn) / (tp + fp + fn + tn); the "unsure" row is excluded
    # from `scored` entirely (design doc: folding it either way would invent a
    # judgement the labeler declined to make), so the denominator here is 5,
    # not the full row count of 6: (2 + 1) / (2 + 1 + 1 + 1) = 3/5.
    assert agreement["agreement"] == pytest.approx(3 / 5)


def test_compute_agreement_none_for_empty_denominator_rates():
    examples = [
        {"example_id": "e1", "tier1_pass": False, "human_label": "not_supported"},
        {"example_id": "e2", "tier1_pass": False, "human_label": "not_supported"},
    ]

    agreement = calibrate.compute_agreement(examples)

    assert agreement["precision"] is None
    assert agreement["recall"] is None
    assert agreement["false_fail_rate"] is None
    # false_pass_rate's denominator (fp + tn) is non-empty here (both tn), so
    # a genuine 0.0 rate is reported rather than None.
    assert agreement["false_pass_rate"] == pytest.approx(0.0)


def test_compute_agreement_counts_unlabeled_rows_without_raising():
    examples = [
        {"example_id": "e1", "tier1_pass": True, "human_label": "supported"},
        {"example_id": "e2", "tier1_pass": True, "human_label": ""},
        {"example_id": "e3", "tier1_pass": False, "human_label": None},
    ]

    agreement = calibrate.compute_agreement(examples)

    assert agreement["counts"]["unlabeled"] == 2
    assert agreement["counts"]["tp"] == 1


def test_compute_agreement_raises_calibration_error_on_invalid_label():
    examples = [{"example_id": "e1", "tier1_pass": True, "human_label": "maybe"}]

    with pytest.raises(calibrate.CalibrationError):
        calibrate.compute_agreement(examples)


# --------------------------------------------------------------------------
# ingest / read_sheet
# --------------------------------------------------------------------------


def _meta_row(**overrides):
    meta = {
        "record_type": calibrate.RECORD_TYPE_META,
        "run_id": "test-run",
        "scoring_version": "1",
        "seed": 7,
        "requested_size": 6,
        "sample_size": 6,
        "generated_utc": "2026-07-25T00:00:00+00:00",
        "predictions_path": "/tmp/predictions.jsonl",
        "scores_path": "/tmp/scores.json",
        "corpus_sha256": "a" * 64,
        "eval_set_sha256": "b" * 64,
    }
    meta.update(overrides)
    return meta


def _example_row(example_id, tier1_pass, human_label="", bucket="pass", **overrides):
    row = {
        "record_type": calibrate.RECORD_TYPE_EXAMPLE,
        "example_id": example_id,
        "task": "cited_qa",
        "category": "concept",
        "bucket": bucket,
        "tier1_pass": tier1_pass,
        "tier1_reason": "ok",
        "prediction": "some prediction text",
        "cited": [],
        "human_label": human_label,
        "human_note": "",
    }
    row.update(overrides)
    return row


def _write_sheet(tmp_path, name="sheet.jsonl", meta_overrides=None, example_rows=None):
    meta = _meta_row(**(meta_overrides or {}))
    rows = (
        example_rows
        if example_rows is not None
        else [
            _example_row("e1", True, human_label="supported"),
            _example_row("e2", False, human_label="not_supported"),
        ]
    )
    path = tmp_path / name
    lines = [json.dumps(meta), *[json.dumps(r) for r in rows]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_ingest_writes_expected_record_fields(tmp_path):
    sheet_path = _write_sheet(tmp_path)
    caldir = tmp_path / "calibration"

    rc = calibrate.main(["ingest", "--sheet", str(sheet_path), "--calibration-dir", str(caldir)])
    assert rc == 0

    out_path = caldir / "1.json"
    record = json.loads(out_path.read_text())
    assert record["run_id"] == "test-run"
    assert "date" in record
    assert record["sheet"]["sha256"] == calibrate.sha256_file(sheet_path)
    assert record["sheet"]["sample_size"] == 6
    assert record["agreement"]["counts"]["tp"] == 1
    assert record["agreement"]["counts"]["tn"] == 1


def test_ingest_refuses_overwrite_without_force_then_succeeds_with_force(tmp_path):
    sheet_path = _write_sheet(tmp_path)
    caldir = tmp_path / "calibration"
    rc_first = calibrate.main(
        ["ingest", "--sheet", str(sheet_path), "--calibration-dir", str(caldir)]
    )
    assert rc_first == 0

    rc_dup = calibrate.main(
        ["ingest", "--sheet", str(sheet_path), "--calibration-dir", str(caldir)]
    )
    assert rc_dup == 1

    rc_force = calibrate.main(
        ["ingest", "--sheet", str(sheet_path), "--calibration-dir", str(caldir), "--force"]
    )
    assert rc_force == 0


def test_read_sheet_raises_on_empty_file(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")

    with pytest.raises(calibrate.CalibrationError):
        calibrate.read_sheet(path)


def test_read_sheet_raises_when_first_line_is_not_meta_record(tmp_path):
    path = tmp_path / "bad.jsonl"
    row = _example_row("e1", True, human_label="supported")
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(calibrate.CalibrationError):
        calibrate.read_sheet(path)


def test_read_sheet_raises_when_no_example_rows(tmp_path):
    path = tmp_path / "meta_only.jsonl"
    path.write_text(json.dumps(_meta_row()) + "\n", encoding="utf-8")

    with pytest.raises(calibrate.CalibrationError):
        calibrate.read_sheet(path)


# --------------------------------------------------------------------------
# unseal guard (evaluate.main exit codes + ledger side effects; no model)
# --------------------------------------------------------------------------


def _tiny_corpus_records():
    records = []
    for video_id, category in (
        ("c1", "concept"),
        ("c2", "concept"),
        ("cs1", "case_study"),
        ("cs2", "case_study"),
        ("l1", "live_session"),
        ("l2", "live_session"),
    ):
        for t in (0, 30):
            records.append(
                {
                    "video_id": video_id,
                    "category": category,
                    "title": video_id,
                    "t": t,
                    "hms": f"00:{t // 60:02d}:{t % 60:02d}",
                    "image": "",
                    "source": "llm",
                    "label": f"label {video_id} {t}",
                    "why": f"why text for {video_id} at {t} explaining the setup",
                    "narration": f"narration {video_id} at {t} about price action structure",
                    "caption": "",
                }
            )
    return records


def _build_v2_dataset_for_unseal(tmp_path):
    corpus_path = tmp_path / "corpus.jsonl"
    raw = ("\n".join(json.dumps(r) for r in _tiny_corpus_records()) + "\n").encode("utf-8")
    corpus_path.write_bytes(raw)

    split_v1_path = tmp_path / "split-v1.json"
    v1_out = tmp_path / "v1_out"
    rc = build_dataset.main(
        ["--corpus", str(corpus_path), "--out", str(v1_out), "--split", str(split_v1_path)]
    )
    assert rc == 0
    v1 = json.loads(split_v1_path.read_text())

    split_v2_path = tmp_path / "split-v2.json"
    payload = splits.build_split_v2_payload(parent=v1, parent_file="split-v1.json")
    split_v2_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    v2_out = tmp_path / "v2_out"
    rc = build_dataset.main(
        ["--corpus", str(corpus_path), "--out", str(v2_out), "--split", str(split_v2_path)]
    )
    assert rc == 0
    return corpus_path, v2_out


def _minimal_predictions_path(tmp_path, name="predictions.jsonl"):
    path = tmp_path / name
    row = {
        "task": "cited_qa",
        "meta": {"video_id": "c1", "hms": "00:00:00", "category": "concept"},
        "prediction": "some prediction text.\nCitation: c1 00:00:00",
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    return path


def test_unseal_guard_refuses_scoring_holdout_without_unseal(tmp_path):
    corpus_path, v2_out = _build_v2_dataset_for_unseal(tmp_path)
    predictions_path = _minimal_predictions_path(tmp_path)
    ledger_path = tmp_path / "unseal-ledger.md"

    rc = evaluate.main(
        [
            "--predictions", str(predictions_path),
            "--eval-jsonl", str(v2_out / "eval_holdout.jsonl"),
            "--corpus", str(corpus_path),
            "--output", str(tmp_path / "scores.json"),
            "--unseal-ledger", str(ledger_path),
        ]
    )

    assert rc == evaluate.EXIT_REFUSED == 2
    assert not ledger_path.exists()


def test_unseal_guard_rename_does_not_bypass_seal_content_based(tmp_path):
    corpus_path, v2_out = _build_v2_dataset_for_unseal(tmp_path)
    predictions_path = _minimal_predictions_path(tmp_path)
    ledger_path = tmp_path / "unseal-ledger.md"

    renamed = v2_out / "sneaky_copy.jsonl"
    shutil.copy(v2_out / "eval_holdout.jsonl", renamed)

    rc = evaluate.main(
        [
            "--predictions", str(predictions_path),
            "--eval-jsonl", str(renamed),
            "--corpus", str(corpus_path),
            "--output", str(tmp_path / "scores2.json"),
            "--unseal-ledger", str(ledger_path),
        ]
    )

    assert rc == 2
    assert not ledger_path.exists()


def test_unseal_guard_filename_backstop_fires_with_no_manifest(tmp_path):
    corpus_path, v2_out = _build_v2_dataset_for_unseal(tmp_path)
    predictions_path = _minimal_predictions_path(tmp_path)
    ledger_path = tmp_path / "unseal-ledger.md"

    away = tmp_path / "away"
    away.mkdir()
    copied = away / "eval_holdout.jsonl"
    shutil.copy(v2_out / "eval_holdout.jsonl", copied)
    # Deliberately no dataset_manifest.json in `away`.

    rc = evaluate.main(
        [
            "--predictions", str(predictions_path),
            "--eval-jsonl", str(copied),
            "--corpus", str(corpus_path),
            "--output", str(tmp_path / "scores3.json"),
            "--unseal-ledger", str(ledger_path),
        ]
    )

    assert rc == 2
    assert not ledger_path.exists()


def test_unseal_guard_dev_eval_set_scores_freely_with_no_ledger(tmp_path):
    corpus_path, v2_out = _build_v2_dataset_for_unseal(tmp_path)
    predictions_path = _minimal_predictions_path(tmp_path)
    ledger_path = tmp_path / "unseal-ledger.md"

    rc = evaluate.main(
        [
            "--predictions", str(predictions_path),
            "--eval-jsonl", str(v2_out / "eval_dev.jsonl"),
            "--corpus", str(corpus_path),
            "--output", str(tmp_path / "dev_scores.json"),
            "--unseal-ledger", str(ledger_path),
        ]
    )

    assert rc == 0
    assert not ledger_path.exists()


def test_unseal_flag_proceeds_and_ledger_appends_across_unsealings(tmp_path):
    corpus_path, v2_out = _build_v2_dataset_for_unseal(tmp_path)
    predictions_path = _minimal_predictions_path(tmp_path)
    ledger_path = tmp_path / "unseal-ledger.md"
    base_argv = [
        "--predictions", str(predictions_path),
        "--eval-jsonl", str(v2_out / "eval_holdout.jsonl"),
        "--corpus", str(corpus_path),
        "--output", str(tmp_path / "hold_scores.json"),
        "--unseal-ledger", str(ledger_path),
    ]

    rc = evaluate.main([*base_argv, "--unseal", "promoting release candidate rc1"])
    assert rc == 0
    assert ledger_path.is_file()
    text = ledger_path.read_text(encoding="utf-8")
    assert "promoting release candidate rc1" in text
    assert str((v2_out / "eval_holdout.jsonl").resolve()) in text
    assert splits.count_unseal_entries(ledger_path) == 1

    rc2 = evaluate.main([*base_argv, "--unseal", "second look"])
    assert rc2 == 0
    assert splits.count_unseal_entries(ledger_path) == 2


def test_unseal_flag_with_non_holdout_eval_set_writes_no_ledger_row(tmp_path):
    corpus_path, v2_out = _build_v2_dataset_for_unseal(tmp_path)
    predictions_path = _minimal_predictions_path(tmp_path)
    ledger_path = tmp_path / "unseal-ledger.md"

    rc = evaluate.main(
        [
            "--predictions", str(predictions_path),
            "--eval-jsonl", str(v2_out / "eval_dev.jsonl"),
            "--corpus", str(corpus_path),
            "--output", str(tmp_path / "dev_scores2.json"),
            "--unseal-ledger", str(ledger_path),
            "--unseal", "not needed, nothing is sealed",
        ]
    )

    assert rc == 0
    assert not ledger_path.exists()
