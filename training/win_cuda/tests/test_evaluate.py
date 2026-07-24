"""Tests for deterministic, model-free prediction scoring.

Pure Python: no torch import anywhere in this suite (evaluate.py only
imports torch lazily inside generate_predictions, which these tests never
call). No network, no GPU, no real corpus -- a small synthetic corpus is
written to tmp_path.
"""

from __future__ import annotations

import json

from stoic_training import evaluate


def write_corpus(tmp_path, records):
    path = tmp_path / "dataset.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return path


def synthetic_corpus_records():
    return [
        {
            "video_id": "c1_intro",
            "hms": "00:00:00",
            "narration": "Instructor explains position sizing by ATR and stop distance.",
            "why": "Position sizing controls risk per trade using ATR.",
            "category": "concept",
            "label": "risk sizing",
            "t": 0,
        },
        {
            "video_id": "cs1_gold",
            "hms": "00:00:12",
            "narration": "Use half size on gold due to volatility and wider stops.",
            "why": "Gold volatility means a smaller position keeps risk constant.",
            "category": "case_study",
            "label": "risk sizing",
            "t": 12,
        },
        {
            "video_id": "live1_nq",
            "hms": "00:00:08",
            "narration": "Stops go beyond the swing point, not at round numbers.",
            "why": "Round numbers cluster stop hunts; the swing point is structural.",
            "category": "live_session",
            "label": "stop placement",
            "t": 8,
        },
    ]


def test_score_citation_fidelity_passes_with_good_overlap(tmp_path):
    corpus_path = write_corpus(tmp_path, synthetic_corpus_records())
    corpus = evaluate.load_corpus(corpus_path)

    prediction = (
        "Size positions using ATR and stop distance to control risk per trade.\n"
        "Citation: c1_intro 00:00:00"
    )
    result = evaluate.score_citation_fidelity(prediction, corpus)
    assert result.passed, result.reason


def test_score_citation_fidelity_fails_on_nonexistent_citation(tmp_path):
    corpus_path = write_corpus(tmp_path, synthetic_corpus_records())
    corpus = evaluate.load_corpus(corpus_path)

    prediction = (
        "Size positions using ATR and stop distance to control risk per trade.\n"
        "Citation: unknown_video 00:00:00"
    )
    result = evaluate.score_citation_fidelity(prediction, corpus)
    assert not result.passed
    assert "not found" in result.reason


def test_score_citation_fidelity_fails_on_low_overlap(tmp_path):
    corpus_path = write_corpus(tmp_path, synthetic_corpus_records())
    corpus = evaluate.load_corpus(corpus_path)

    prediction = "Completely unrelated statement about pizza toppings.\nCitation: c1_intro 00:00:00"
    result = evaluate.score_citation_fidelity(prediction, corpus)
    assert not result.passed
    assert "overlap" in result.reason


def test_score_citation_fidelity_fails_without_trailing_citation(tmp_path):
    corpus_path = write_corpus(tmp_path, synthetic_corpus_records())
    corpus = evaluate.load_corpus(corpus_path)

    prediction = "Size positions using ATR and stop distance to control risk per trade."
    result = evaluate.score_citation_fidelity(prediction, corpus)
    assert not result.passed
    assert "no trailing citation" in result.reason


def test_score_conflict_handling_passes_with_both_ids_and_marker():
    prediction = (
        "c1_intro (00:00:00) says use full size, while cs1_gold (00:00:12) says "
        "use half size on gold. This is a conflict between the two sources; flagging "
        "as ambiguous for human review.\n"
        "Citation: c1_intro 00:00:00\n"
        "Citation: cs1_gold 00:00:12"
    )
    result = evaluate.score_conflict_handling(prediction)
    assert result.passed, result.reason


def test_score_conflict_handling_fails_with_one_id_only():
    prediction = (
        "Position sizing depends on volatility.\nCitation: c1_intro 00:00:00\n"
        "This seems ambiguous."
    )
    result = evaluate.score_conflict_handling(prediction)
    assert not result.passed
    assert "two cited video_ids" in result.reason


def test_score_conflict_handling_fails_without_marker_word():
    prediction = (
        "c1_intro says full size, cs1_gold says half size on gold.\n"
        "Citation: c1_intro 00:00:00\nCitation: cs1_gold 00:00:12"
    )
    result = evaluate.score_conflict_handling(prediction)
    assert not result.passed
    assert "marker" in result.reason


def test_score_predictions_reports_per_task_and_per_category(tmp_path):
    corpus_path = write_corpus(tmp_path, synthetic_corpus_records())
    corpus = evaluate.load_corpus(corpus_path)

    predictions = [
        {
            "task": "cited_qa",
            "meta": {"video_id": "c1_intro", "hms": "00:00:00", "category": "concept"},
            "prediction": (
                "Size positions using ATR and stop distance to control risk per trade.\n"
                "Citation: c1_intro 00:00:00"
            ),
        },
        {
            "task": "rule_candidate",
            "meta": {"video_id": "live1_nq", "hms": "00:00:08", "category": "live_session"},
            "prediction": "Unrelated pizza content.\nCitation: live1_nq 00:00:08",
        },
        {
            "task": "conflict_check",
            "meta": {"video_id": "c1_intro", "video_id_b": "cs1_gold", "category": "concept"},
            "prediction": (
                "These two sources conflict on position sizing.\n"
                "Citation: c1_intro 00:00:00\nCitation: cs1_gold 00:00:12"
            ),
        },
    ]

    scores = evaluate.score_predictions(predictions, corpus)

    assert scores["count"] == 3
    assert scores["per_task"]["cited_qa"]["pass_rate"] == 1.0
    assert scores["per_task"]["rule_candidate"]["pass_rate"] == 0.0
    assert scores["per_task"]["conflict_check"]["pass_rate"] == 1.0
    assert scores["citation_fidelity"] == 0.5  # 1 of 2 non-conflict predictions passed
    assert scores["conflict_handling"] == 1.0
    assert scores["per_category"]["concept"]["count"] == 2
    assert scores["per_category"]["live_session"]["pass_rate"] == 0.0


def test_compare_splits_reports_gap(tmp_path):
    corpus_path = write_corpus(tmp_path, synthetic_corpus_records())
    corpus = evaluate.load_corpus(corpus_path)

    good = {
        "task": "cited_qa",
        "meta": {"category": "concept"},
        "prediction": (
            "Size positions using ATR and stop distance to control risk per trade.\n"
            "Citation: c1_intro 00:00:00"
        ),
    }
    bad = {
        "task": "cited_qa",
        "meta": {"category": "concept"},
        "prediction": "Unrelated.\nCitation: unknown_video 00:00:00",
    }

    train_scores = evaluate.score_predictions([good, good], corpus)
    eval_scores = evaluate.score_predictions([good, bad], corpus)

    comparison = evaluate.compare_splits(train_scores, eval_scores)
    assert comparison["train_citation_fidelity"] == 1.0
    assert comparison["eval_citation_fidelity"] == 0.5
    assert comparison["citation_fidelity_gap"] == -0.5


def test_compare_splits_returns_none_when_missing_a_split():
    assert evaluate.compare_splits(None, {"citation_fidelity": 1.0}) is None
    assert evaluate.compare_splits({"citation_fidelity": 1.0}, None) is None


def test_token_overlap_ratio_empty_strings_are_zero():
    assert evaluate.token_overlap_ratio("", "something") == 0.0
    assert evaluate.token_overlap_ratio("something", "") == 0.0


def test_main_scores_predictions_file_end_to_end(tmp_path):
    corpus_path = write_corpus(tmp_path, synthetic_corpus_records())
    predictions_path = tmp_path / "predictions.jsonl"
    predictions = [
        {
            "task": "cited_qa",
            "meta": {"video_id": "c1_intro", "hms": "00:00:00", "category": "concept"},
            "prediction": (
                "Size positions using ATR and stop distance to control risk per trade.\n"
                "Citation: c1_intro 00:00:00"
            ),
        }
    ]
    with predictions_path.open("w", encoding="utf-8") as handle:
        for record in predictions:
            handle.write(json.dumps(record) + "\n")

    output_path = tmp_path / "scores.json"
    rc = evaluate.main(
        [
            "--predictions",
            str(predictions_path),
            "--corpus",
            str(corpus_path),
            "--output",
            str(output_path),
        ]
    )
    assert rc == 0
    report = json.loads(output_path.read_text())
    assert report["eval"]["citation_fidelity"] == 1.0
