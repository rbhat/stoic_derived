"""Tests for run-over-run comparison: guards, buckets, paired flips, McNemar.

Pure Python, CPU-only, no GPU, no network: everything is built from
synthetic run dirs (manifest.json + evaluation/scores.json) under tmp_path,
written by hand in the exact contract shapes. No torch import anywhere.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest
from stoic_training import compare


def _details(pairs: dict[str, bool], *, task: str = "cited_qa", category: str = "concept"):
    return [
        {
            "example_id": example_id,
            "task": task,
            "category": category,
            "passed": passed,
            "reason": "ok" if passed else "no trailing citation",
            "bucket": "pass" if passed else "no_citation",
        }
        for example_id, passed in pairs.items()
    ]


def _eval_section(details: list[dict]) -> dict:
    count = len(details)
    passed_count = sum(1 for entry in details if entry["passed"])
    fidelity = (passed_count / count) if count else None
    buckets = {
        "pass": passed_count,
        "schema_violation": 0,
        "no_citation": count - passed_count,
        "citation_not_in_corpus": 0,
        "weak_overlap": 0,
    }
    bucket_rates = {name: (value / count if count else None) for name, value in buckets.items()}
    conflict_buckets = {"pass": 0, "insufficient_citations": 0, "no_conflict_marker": 0}
    conflict_bucket_rates = {name: None for name in conflict_buckets}
    return {
        "count": count,
        "citation_fidelity": fidelity,
        "conflict_handling": None,
        "buckets": buckets,
        "bucket_rates": bucket_rates,
        "conflict_buckets": conflict_buckets,
        "conflict_bucket_rates": conflict_bucket_rates,
        "per_task": {
            "cited_qa": {
                "count": count,
                "pass_rate": fidelity,
                "buckets": buckets,
                "bucket_rates": bucket_rates,
            }
        },
        "per_category": {"concept": {"count": count, "pass_rate": fidelity}},
        "details": details,
    }


def _manifest_evaluation(scores_path, *, corpus="corpus-sha", eval_set="eval-sha", version="1"):
    return {
        "scoring_version": version,
        "params": {"overlap_threshold": 0.3},
        "scores": {"path": str(scores_path), "sha256": "deadbeef"},
        "metrics": {
            "count": 1,
            "citation_fidelity": 1.0,
            "conflict_handling": None,
            "buckets": {},
            "conflict_buckets": {},
        },
        "corpus_sha256": corpus,
        "eval_set_sha256": eval_set,
        "eval_set_source": "eval_jsonl",
        "evaluated_utc": "2026-07-25T00:00:00+00:00",
    }


def _write_run(
    tmp_path,
    name: str,
    details: list[dict],
    *,
    corpus: str = "corpus-sha",
    eval_set: str = "eval-sha",
    version: str = "1",
    with_evaluation: bool = True,
):
    run_dir = tmp_path / "runs" / name
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(parents=True)
    scores_path = eval_dir / "scores.json"
    scores_path.write_text(json.dumps({"eval": _eval_section(details)}), encoding="utf-8")

    manifest: dict = {"run_id": name, "kind": "run"}
    if with_evaluation:
        manifest["evaluation"] = _manifest_evaluation(
            scores_path, corpus=corpus, eval_set=eval_set, version=version
        )
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return run_dir


# --- refusals (exit code 2) -------------------------------------------------


def test_refuses_when_evaluation_section_missing(tmp_path, capsys):
    run_a = _write_run(tmp_path, "run_a", _details({"e1": True}), with_evaluation=False)
    run_b = _write_run(tmp_path, "run_b", _details({"e1": True}))

    rc = compare.main([str(run_a), str(run_b)])

    assert rc == 2
    assert "evaluation" in capsys.readouterr().err


def test_refuses_on_corpus_sha256_mismatch(tmp_path, capsys):
    run_a = _write_run(tmp_path, "run_a", _details({"e1": True}), corpus="corpus-A")
    run_b = _write_run(tmp_path, "run_b", _details({"e1": True}), corpus="corpus-B")

    rc = compare.main([str(run_a), str(run_b)])

    err = capsys.readouterr().err
    assert rc == 2
    assert "corpus_sha256" in err
    assert "corpus-A" in err and "corpus-B" in err


def test_refuses_on_eval_set_sha256_mismatch(tmp_path, capsys):
    run_a = _write_run(tmp_path, "run_a", _details({"e1": True}), eval_set="eval-A")
    run_b = _write_run(tmp_path, "run_b", _details({"e1": True}), eval_set="eval-B")

    rc = compare.main([str(run_a), str(run_b)])

    err = capsys.readouterr().err
    assert rc == 2
    assert "eval_set_sha256" in err
    assert "eval-A" in err and "eval-B" in err


def test_refuses_on_scoring_version_mismatch(tmp_path, capsys):
    run_a = _write_run(tmp_path, "run_a", _details({"e1": True}), version="1")
    run_b = _write_run(tmp_path, "run_b", _details({"e1": True}), version="2")

    rc = compare.main([str(run_a), str(run_b)])

    err = capsys.readouterr().err
    assert rc == 2
    assert "scoring_version" in err
    assert "'1'" in err and "'2'" in err


# --- usage/IO problems (exit code 1) ---------------------------------------


def test_missing_example_id_exits_1(tmp_path, capsys):
    good_details = _details({"e1": True})
    bad_details = [
        {
            "task": "cited_qa",
            "category": "concept",
            "passed": True,
            "reason": "ok",
            "bucket": "pass",
        }
    ]
    run_a = _write_run(tmp_path, "run_a", good_details)
    run_b = _write_run(tmp_path, "run_b", bad_details)

    rc = compare.main([str(run_a), str(run_b)])

    assert rc == 1
    assert "example_id" in capsys.readouterr().err


def test_missing_scores_json_exits_1(tmp_path, capsys):
    run_a = _write_run(tmp_path, "run_a", _details({"e1": True}))
    run_b = _write_run(tmp_path, "run_b", _details({"e1": True}))
    (run_b / "evaluation" / "scores.json").unlink()

    rc = compare.main([str(run_a), str(run_b)])

    assert rc == 1
    assert "scores.json" in capsys.readouterr().err


def test_missing_run_dir_exits_1(tmp_path, capsys):
    run_a = _write_run(tmp_path, "run_a", _details({"e1": True}))

    rc = compare.main([str(run_a), str(tmp_path / "runs" / "does_not_exist")])

    assert rc == 1
    assert "manifest" in capsys.readouterr().err


# --- happy path: hand-checkable flip count and p-value ----------------------


def test_happy_path_comparison_hand_checkable_flips_and_p_value(tmp_path):
    # All five examples fail in A and pass in B: 5 fixed, 0 broke.
    ids = [f"e{i}" for i in range(1, 6)]
    details_a = _details({eid: False for eid in ids})
    details_b = _details({eid: True for eid in ids})
    run_a = _write_run(tmp_path, "run_a", details_a)
    run_b = _write_run(tmp_path, "run_b", details_b)

    result = compare.compare_runs(run_a, run_b)

    assert result["flips"]["fixed"] == sorted(ids)
    assert result["flips"]["broke"] == []
    assert result["flips"]["unchanged_pass"] == 0
    assert result["flips"]["unchanged_fail"] == 0
    # mcnemar_exact_p(5, 0) == 2 * C(5,0) / 2**5 == 2/32 == 0.0625 (pinned value).
    assert result["flips"]["mcnemar_p"] == pytest.approx(0.0625)

    assert result["headline"]["count"] == {"a": 5, "b": 5, "delta": 0}
    assert result["headline"]["citation_fidelity"] == {"a": 0.0, "b": 1.0, "delta": 1.0}
    # No conflict_check examples in this fixture: conflict_handling is None on both sides.
    assert result["headline"]["conflict_handling"] == {"a": None, "b": None, "delta": None}

    assert result["per_task"]["cited_qa"]["pass_rate_delta"] == pytest.approx(1.0)

    citation_buckets = result["buckets"]["citation_buckets"]
    assert citation_buckets["pass"]["count_a"] == 0
    assert citation_buckets["pass"]["count_b"] == 5
    assert citation_buckets["pass"]["count_delta"] == 5
    assert citation_buckets["no_citation"]["count_delta"] == -5


def test_json_output_parses(tmp_path, capsys):
    run_a = _write_run(tmp_path, "run_a", _details({"e1": False}))
    run_b = _write_run(tmp_path, "run_b", _details({"e1": True}))

    rc = compare.main([str(run_a), str(run_b), "--json"])

    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["flips"]["fixed"] == ["e1"]
    assert parsed["headline"]["citation_fidelity"]["delta"] == pytest.approx(1.0)


def test_human_readable_report_mentions_key_sections(tmp_path, capsys):
    run_a = _write_run(tmp_path, "run_a", _details({"e1": False}))
    run_b = _write_run(tmp_path, "run_b", _details({"e1": True}))

    rc = compare.main([str(run_a), str(run_b)])

    out = capsys.readouterr().out
    assert rc == 0
    assert "headline" in out
    assert "paired flips" in out
    assert "fixed ids" in out
    assert "only_in_a" in out and "only_in_b" in out


def test_scores_path_fallback_when_run_dir_moved(tmp_path):
    run_dir = tmp_path / "runs" / "run_a"
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(parents=True)
    details = _details({"e1": True})
    (eval_dir / "scores.json").write_text(
        json.dumps({"eval": _eval_section(details)}), encoding="utf-8"
    )
    manifest = {
        "run_id": "run_a",
        "evaluation": _manifest_evaluation("/nonexistent/path/scores.json"),
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    run_b = _write_run(tmp_path, "run_b", _details({"e1": True}))

    result = compare.compare_runs(run_dir, run_b)
    assert result["headline"]["count"] == {"a": 1, "b": 1, "delta": 0}


# --- paired_flips: both flip directions and only_in_a/only_in_b ------------


def test_paired_flips_both_directions_and_unpaired_ids():
    details_a = _details({"e1": True, "e2": False, "e3": True, "e4": False})
    details_a.append(
        {
            "example_id": "only_a",
            "task": "cited_qa",
            "category": "concept",
            "passed": True,
            "reason": "ok",
            "bucket": "pass",
        }
    )
    details_b = _details({"e1": True, "e2": True, "e3": False, "e4": False})
    details_b.append(
        {
            "example_id": "only_b",
            "task": "cited_qa",
            "category": "concept",
            "passed": False,
            "reason": "no trailing citation",
            "bucket": "no_citation",
        }
    )

    flips = compare.paired_flips(details_a, details_b)

    assert flips.fixed == ("e2",)
    assert flips.broke == ("e3",)
    assert flips.unchanged_pass == 1  # e1: True -> True
    assert flips.unchanged_fail == 1  # e4: False -> False
    assert flips.only_in_a == ("only_a",)
    assert flips.only_in_b == ("only_b",)


# --- mcnemar_exact_p: pinned values -----------------------------------------


@pytest.mark.parametrize(
    ("b", "c", "expected"),
    [
        (0, 0, 1.0),
        (1, 0, 1.0),
        (5, 0, 0.0625),
        (4, 1, 0.375),
        (3, 3, 1.0),
    ],
)
def test_mcnemar_exact_p_pinned_values(b, c, expected):
    assert compare.mcnemar_exact_p(b, c) == pytest.approx(expected)


# --- import hygiene ----------------------------------------------------------


def test_compare_and_runs_index_import_without_torch():
    """Both modules must import with nothing heavy pulled in behind them.

    Checked in a FRESH interpreter, not in-process: by the time this test
    runs, sibling suites (test_infer, test_gpu_smoke) have already imported
    torch, so an in-process `"torch" not in sys.modules` assertion measures
    test ordering rather than this module's import graph.
    """
    source = (
        "import sys;"
        "import stoic_training.compare;"
        "import stoic_training.runs_index;"
        "leaked = sorted(m for m in ('torch', 'transformers', 'peft', 'yaml')"
        " if m in sys.modules);"
        "print(','.join(leaked))"
    )
    result = subprocess.run(
        [sys.executable, "-c", source], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "", f"heavy imports leaked: {result.stdout.strip()}"
