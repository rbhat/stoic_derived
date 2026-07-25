"""Tests for deterministic, model-free prediction scoring.

Pure Python: no torch import anywhere in this suite (evaluate.py only
imports torch lazily inside generate_predictions, which these tests never
call). No network, no GPU, no real corpus -- a small synthetic corpus is
written to tmp_path.
"""

from __future__ import annotations

import json

from stoic_training import evaluate, manifest


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


# --- C2: stable example_id -------------------------------------------------


def test_example_id_is_deterministic():
    first = evaluate.example_id(task="cited_qa", video_id="v1", hms="00:00:01", prompt="hello")
    second = evaluate.example_id(task="cited_qa", video_id="v1", hms="00:00:01", prompt="hello")
    assert first == second
    assert len(first) == 16


def test_example_id_sensitive_to_each_field():
    base = {"task": "cited_qa", "video_id": "v1", "hms": "00:00:01", "prompt": "hello"}
    baseline = evaluate.example_id(**base)
    for field in ("task", "video_id", "hms", "prompt"):
        changed = dict(base)
        changed[field] = base[field] + "_x"
        assert evaluate.example_id(**changed) != baseline, field


def test_example_id_framing_prevents_field_boundary_collision():
    # Explicit "field=" framing plus the \x1f separator (which cannot occur
    # in these fields) means shifting a character across a field boundary
    # must not collide: "task=ab"+"video_id=c" != "task=a"+"video_id=bc".
    shifted_into_task = evaluate.example_id(task="ab", video_id="c", hms="", prompt="")
    shifted_into_video_id = evaluate.example_id(task="a", video_id="bc", hms="", prompt="")
    assert shifted_into_task != shifted_into_video_id


def test_prompt_from_messages_concatenates_user_turns_only():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "second"},
    ]
    assert evaluate.prompt_from_messages(messages) == "first\nsecond"


def test_prompt_from_messages_empty():
    assert evaluate.prompt_from_messages(None) == ""
    assert evaluate.prompt_from_messages([]) == ""


def test_example_id_for_record_uses_prompt_key_when_present():
    record = {"task": "cited_qa", "meta": {"video_id": "v1", "hms": "00:00:01"}, "prompt": "hi"}
    expected = evaluate.example_id(task="cited_qa", video_id="v1", hms="00:00:01", prompt="hi")
    assert evaluate.example_id_for_record(record) == expected


def test_example_id_for_record_falls_back_to_messages():
    record = {
        "task": "cited_qa",
        "meta": {"video_id": "v1", "hms": "00:00:01"},
        "messages": [{"role": "user", "content": "hi"}],
    }
    expected = evaluate.example_id(task="cited_qa", video_id="v1", hms="00:00:01", prompt="hi")
    assert evaluate.example_id_for_record(record) == expected


def test_example_id_for_record_missing_fields_become_empty_string():
    record = {"prediction": "x"}
    expected = evaluate.example_id(task="", video_id="", hms="", prompt="")
    assert evaluate.example_id_for_record(record) == expected


# --- C4: bucket classification ----------------------------------------------

_RULE_CANDIDATE_PASS_BODY = (
    "Rule candidate: Size positions using ATR and stop distance to control risk per trade.\n"
    "Setup / entry condition: ATR and stop distance known.\n"
    "Invalidation / caveat: ATR unknown."
)
_RULE_CANDIDATE_WEAK_BODY = (
    "Rule candidate: Completely unrelated statement about pizza toppings.\n"
    "Setup / entry condition: Order a large pizza.\n"
    "Invalidation / caveat: Cold pizza invalidates this rule."
)


def _corpus(tmp_path):
    return evaluate.load_corpus(write_corpus(tmp_path, synthetic_corpus_records()))


def test_classify_prediction_rule_candidate_pass(tmp_path):
    corpus = _corpus(tmp_path)
    text = _RULE_CANDIDATE_PASS_BODY + "\nCitation: c1_intro 00:00:00"
    result = evaluate.classify_prediction({"task": "rule_candidate", "prediction": text}, corpus)
    assert result.bucket == evaluate.BUCKET_PASS
    assert result.passed


def test_classify_prediction_rule_candidate_schema_violation_missing_line(tmp_path):
    corpus = _corpus(tmp_path)
    text = (
        "Rule candidate: Size positions using ATR and stop distance.\n"
        "Invalidation / caveat: ATR unknown.\n"
        "Citation: c1_intro 00:00:00"
    )
    result = evaluate.classify_prediction({"task": "rule_candidate", "prediction": text}, corpus)
    assert result.bucket == evaluate.BUCKET_SCHEMA_VIOLATION
    assert not result.passed


def test_classify_prediction_rule_candidate_no_citation(tmp_path):
    corpus = _corpus(tmp_path)
    result = evaluate.classify_prediction(
        {"task": "rule_candidate", "prediction": _RULE_CANDIDATE_PASS_BODY}, corpus
    )
    assert result.bucket == evaluate.BUCKET_NO_CITATION


def test_classify_prediction_rule_candidate_citation_not_in_corpus(tmp_path):
    corpus = _corpus(tmp_path)
    text = _RULE_CANDIDATE_PASS_BODY + "\nCitation: unknown_video 00:00:00"
    result = evaluate.classify_prediction({"task": "rule_candidate", "prediction": text}, corpus)
    assert result.bucket == evaluate.BUCKET_CITATION_NOT_IN_CORPUS


def test_classify_prediction_rule_candidate_weak_overlap(tmp_path):
    corpus = _corpus(tmp_path)
    text = _RULE_CANDIDATE_WEAK_BODY + "\nCitation: c1_intro 00:00:00"
    result = evaluate.classify_prediction({"task": "rule_candidate", "prediction": text}, corpus)
    assert result.bucket == evaluate.BUCKET_WEAK_OVERLAP


def test_classify_prediction_schema_first_precedence_over_hallucination(tmp_path):
    """A rule_candidate that is BOTH schema-broken and cites a nonexistent
    video must land in schema_violation, not citation_not_in_corpus: schema
    is the cheapest, most objective gate and is checked first (see
    classify_prediction's docstring)."""
    corpus = _corpus(tmp_path)
    text = "Rule candidate: Size positions using ATR.\nCitation: unknown_video 00:00:00"
    result = evaluate.classify_prediction({"task": "rule_candidate", "prediction": text}, corpus)
    assert result.bucket == evaluate.BUCKET_SCHEMA_VIOLATION


def test_classify_prediction_cited_qa_pass(tmp_path):
    corpus = _corpus(tmp_path)
    text = (
        "Size positions using ATR and stop distance to control risk per trade.\n"
        "Citation: c1_intro 00:00:00"
    )
    result = evaluate.classify_prediction({"task": "cited_qa", "prediction": text}, corpus)
    assert result.bucket == evaluate.BUCKET_PASS


def test_classify_prediction_cited_qa_schema_violation_empty_body(tmp_path):
    corpus = _corpus(tmp_path)
    text = "Citation: c1_intro 00:00:00"
    result = evaluate.classify_prediction({"task": "cited_qa", "prediction": text}, corpus)
    assert result.bucket == evaluate.BUCKET_SCHEMA_VIOLATION


def test_classify_prediction_cited_qa_no_citation(tmp_path):
    corpus = _corpus(tmp_path)
    text = "Size positions using ATR and stop distance to control risk per trade."
    result = evaluate.classify_prediction({"task": "cited_qa", "prediction": text}, corpus)
    assert result.bucket == evaluate.BUCKET_NO_CITATION


def test_classify_prediction_cited_qa_citation_not_in_corpus(tmp_path):
    corpus = _corpus(tmp_path)
    text = (
        "Size positions using ATR and stop distance to control risk per trade.\n"
        "Citation: unknown_video 00:00:00"
    )
    result = evaluate.classify_prediction({"task": "cited_qa", "prediction": text}, corpus)
    assert result.bucket == evaluate.BUCKET_CITATION_NOT_IN_CORPUS


def test_classify_prediction_cited_qa_weak_overlap(tmp_path):
    corpus = _corpus(tmp_path)
    text = "Completely unrelated statement about pizza toppings.\nCitation: c1_intro 00:00:00"
    result = evaluate.classify_prediction({"task": "cited_qa", "prediction": text}, corpus)
    assert result.bucket == evaluate.BUCKET_WEAK_OVERLAP


def test_classify_prediction_conflict_pass():
    text = (
        "c1_intro (00:00:00) says use full size, while cs1_gold (00:00:12) says "
        "use half size on gold. This is a conflict between the two sources; flagging "
        "as ambiguous for human review.\n"
        "Citation: c1_intro 00:00:00\nCitation: cs1_gold 00:00:12"
    )
    result = evaluate.classify_prediction({"task": "conflict_check", "prediction": text}, {})
    assert result.bucket == evaluate.CONFLICT_BUCKET_PASS
    assert result.passed


def test_classify_prediction_conflict_insufficient_citations():
    text = (
        "Position sizing depends on volatility.\nCitation: c1_intro 00:00:00\n"
        "This seems ambiguous."
    )
    result = evaluate.classify_prediction({"task": "conflict_check", "prediction": text}, {})
    assert result.bucket == evaluate.CONFLICT_BUCKET_INSUFFICIENT_CITATIONS


def test_classify_prediction_conflict_no_marker():
    text = (
        "c1_intro says full size, cs1_gold says half size on gold.\n"
        "Citation: c1_intro 00:00:00\nCitation: cs1_gold 00:00:12"
    )
    result = evaluate.classify_prediction({"task": "conflict_check", "prediction": text}, {})
    assert result.bucket == evaluate.CONFLICT_BUCKET_NO_MARKER


# --- C5: score_predictions bucket dicts / example_id ------------------------


def test_score_predictions_bucket_dicts_are_complete_and_details_have_example_id(tmp_path):
    corpus = _corpus(tmp_path)
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
            "task": "conflict_check",
            "meta": {"video_id": "c1_intro", "category": "concept"},
            "prediction": (
                "c1_intro says full size, cs1_gold says half size.\nCitation: c1_intro 00:00:00"
            ),
        },
    ]
    scores = evaluate.score_predictions(predictions, corpus)

    assert set(scores["buckets"]) == set(evaluate.CITATION_BUCKETS)
    assert set(scores["bucket_rates"]) == set(evaluate.CITATION_BUCKETS)
    assert set(scores["conflict_buckets"]) == set(evaluate.CONFLICT_BUCKETS)
    assert set(scores["conflict_bucket_rates"]) == set(evaluate.CONFLICT_BUCKETS)
    assert scores["buckets"][evaluate.BUCKET_PASS] == 1
    assert scores["buckets"][evaluate.BUCKET_SCHEMA_VIOLATION] == 0  # zeros included
    assert scores["conflict_buckets"][evaluate.CONFLICT_BUCKET_INSUFFICIENT_CITATIONS] == 1

    cited_qa_task = scores["per_task"]["cited_qa"]
    assert set(cited_qa_task["buckets"]) == set(evaluate.CITATION_BUCKETS)
    assert set(cited_qa_task["bucket_rates"]) == set(evaluate.CITATION_BUCKETS)
    conflict_task = scores["per_task"]["conflict_check"]
    assert set(conflict_task["buckets"]) == set(evaluate.CONFLICT_BUCKETS)

    for entry in scores["details"]:
        assert len(entry["example_id"]) == 16
        assert entry["bucket"] in evaluate.CITATION_BUCKETS + evaluate.CONFLICT_BUCKETS


def test_score_predictions_bucket_rates_null_when_group_empty():
    scores = evaluate.score_predictions([], {})
    assert all(rate is None for rate in scores["bucket_rates"].values())
    assert all(rate is None for rate in scores["conflict_bucket_rates"].values())
    assert scores["citation_fidelity"] is None
    assert scores["conflict_handling"] is None


# --- C5/C6: scores.json versioning + digest metadata ------------------------


def test_main_scores_json_contains_versioning_and_digest_metadata(tmp_path):
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
            "--predictions", str(predictions_path),
            "--corpus", str(corpus_path),
            "--output", str(output_path),
        ]
    )
    assert rc == 0
    report = json.loads(output_path.read_text())

    assert report["scoring_version"] == evaluate.SCORING_VERSION
    assert report["params"] == {"overlap_threshold": evaluate.DEFAULT_OVERLAP_THRESHOLD}
    assert report["corpus_sha256"] == manifest.sha256_file(corpus_path)
    assert report["eval_set_source"] == "predictions"
    assert report["eval_set_sha256"] == manifest.sha256_file(predictions_path)
    assert isinstance(report["generated_utc"], str) and report["generated_utc"]
    assert report["eval"]["details"][0]["example_id"]

    # An externally-generated predictions file stays comparable when a
    # matching --eval-jsonl is also given: the eval.jsonl digest wins (C6).
    eval_jsonl_path = tmp_path / "eval.jsonl"
    eval_jsonl_path.write_text('{"task": "cited_qa"}\n', encoding="utf-8")
    rc2 = evaluate.main(
        [
            "--predictions", str(predictions_path),
            "--eval-jsonl", str(eval_jsonl_path),
            "--corpus", str(corpus_path),
            "--output", str(output_path),
        ]
    )
    assert rc2 == 0
    report2 = json.loads(output_path.read_text())
    assert report2["eval_set_source"] == "eval_jsonl"
    assert report2["eval_set_sha256"] == manifest.sha256_file(eval_jsonl_path)


# --- C10: baseline_run_id ----------------------------------------------------


def test_baseline_run_id_deterministic_and_prefixed():
    kwargs = {
        "base_repo_id": "Qwen/Qwen3-8B",
        "base_revision": "deadbeef",
        "eval_set_sha256": "a" * 64,
        "scoring_version": "1",
    }
    first = evaluate.baseline_run_id(**kwargs)
    second = evaluate.baseline_run_id(**kwargs)
    assert first == second
    assert first.startswith("baseline-")
    assert len(first) == len("baseline-") + 16


def test_baseline_run_id_sensitive_to_revision_eval_digest_and_scoring_version():
    base_kwargs = {
        "base_repo_id": "Qwen/Qwen3-8B",
        "base_revision": "deadbeef",
        "eval_set_sha256": "a" * 64,
        "scoring_version": "1",
    }
    baseline = evaluate.baseline_run_id(**base_kwargs)

    assert evaluate.baseline_run_id(**{**base_kwargs, "base_revision": "cafefeed"}) != baseline
    assert evaluate.baseline_run_id(**{**base_kwargs, "eval_set_sha256": "b" * 64}) != baseline
    assert evaluate.baseline_run_id(**{**base_kwargs, "scoring_version": "2"}) != baseline


def test_baseline_run_id_separates_runs_whose_predictions_can_differ():
    """Two baselines that differ only in generation config or prompt variant must
    not land in the same run dir and overwrite each other's artifacts -- the
    collision that the naive and format-instructed baselines would otherwise hit.
    See docs/superpowers/specs/2026-07-25-baseline-redo-decision.md section 5.
    """
    base_kwargs = {
        "base_repo_id": "Qwen/Qwen3-8B",
        "base_revision": "deadbeef",
        "eval_set_sha256": "a" * 64,
        "scoring_version": "1",
    }
    baseline = evaluate.baseline_run_id(**base_kwargs)

    assert evaluate.baseline_run_id(**{**base_kwargs, "max_new_tokens": 2048}) != baseline
    assert evaluate.baseline_run_id(**{**base_kwargs, "enable_thinking": True}) != baseline
    assert (
        evaluate.baseline_run_id(**{**base_kwargs, "prompt_variant": "format_instructed"})
        != baseline
    )


def test_baseline_run_id_defaults_to_thinking_off_and_the_stock_prompt():
    """Pins the defaults into the id, so the flags cannot be quietly re-defaulted
    without every baseline id changing and making the switch visible."""
    explicit = evaluate.baseline_run_id(
        base_repo_id="Qwen/Qwen3-8B",
        base_revision="deadbeef",
        eval_set_sha256="a" * 64,
        scoring_version="1",
        max_new_tokens=evaluate.DEFAULT_MAX_NEW_TOKENS,
        enable_thinking=False,
        prompt_variant="stock",
    )
    implicit = evaluate.baseline_run_id(
        base_repo_id="Qwen/Qwen3-8B",
        base_revision="deadbeef",
        eval_set_sha256="a" * 64,
        scoring_version="1",
    )
    assert explicit == implicit
