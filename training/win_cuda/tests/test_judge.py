"""CPU-only tests for the Tier-2 advisory LLM judge (stoic_training.judge).

No network, no real model load. Section 1 reuses the exact `_StubTokenizer`/
`_StubModel` pattern from `tests/test_infer.py` to drive
`judge.judge_targets` through `infer.generate_one`: this is the "any code
path that touches transformers generation APIs gets a stub-based regression
test" requirement from the design doc (section 6), because `judge_targets`
is exactly such a path (it calls `infer.generate_one`, which has already
had one BatchEncoding-shaped regression). The rest exercises the pure-Python
guards and CLI surface (dry-run, missing-arg refusal, import hygiene) with
synthetic run dirs and a tiny synthetic corpus under `tmp_path`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

from stoic_training import evaluate as evaluate_mod  # noqa: E402
from stoic_training import judge  # noqa: E402

# --------------------------------------------------------------------------
# 1. stub-based generation regression (judge_targets -> infer.generate_one)
# --------------------------------------------------------------------------


class _StubTokenizer:
    def __init__(self, encoded):
        self._encoded = encoded
        self.pad_token_id = 0
        self.eos_token_id = 1

    def apply_chat_template(self, messages, add_generation_prompt=True, return_tensors="pt"):
        return self._encoded

    def decode(self, ids, skip_special_tokens=True):
        return "some reasoning first\nVERDICT: supported\nreason: matches the excerpt"


class _StubModel:
    """Records the kwargs it was called with and asserts input_ids is a real tensor."""

    def __init__(self):
        self.device = "cpu"
        self.received_kwargs: dict | None = None

    def generate(self, **kwargs):
        self.received_kwargs = kwargs
        input_ids = kwargs.get("input_ids")
        assert isinstance(input_ids, torch.Tensor), (
            f"model.generate must receive a real tensor via input_ids, got {type(input_ids)!r}"
        )
        extra = torch.zeros((input_ids.shape[0], 1), dtype=input_ids.dtype)
        return torch.cat([input_ids, extra], dim=-1)


def _target() -> judge.JudgeTarget:
    return judge.JudgeTarget(
        example_id="abc123",
        task="cited_qa",
        video_id="vid1",
        hms="00:00:10",
        claim="price broke out of a base",
        narration="the market built a base then broke out",
    )


def test_judge_targets_normalizes_batch_encoding_from_apply_chat_template():
    from transformers.tokenization_utils_base import BatchEncoding

    input_ids = torch.tensor([[5, 6, 7]])
    attention_mask = torch.ones_like(input_ids)
    encoded = BatchEncoding({"input_ids": input_ids, "attention_mask": attention_mask})
    tokenizer = _StubTokenizer(encoded)
    model = _StubModel()

    rows = judge.judge_targets(
        [_target()], model=model, tokenizer=tokenizer, judge_version="1-deadbeef"
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["example_id"] == "abc123"
    assert row["judge_version"] == "1-deadbeef"
    assert row["verdict"] == judge.VERDICT_SUPPORTED
    assert torch.equal(model.received_kwargs["input_ids"], input_ids)
    assert torch.equal(model.received_kwargs["attention_mask"], attention_mask)
    assert model.received_kwargs["do_sample"] is False
    assert model.received_kwargs["temperature"] is None


def test_judge_targets_accepts_bare_tensor_from_apply_chat_template():
    input_ids = torch.tensor([[5, 6, 7]])
    tokenizer = _StubTokenizer(input_ids)
    model = _StubModel()

    rows = judge.judge_targets(
        [_target()], model=model, tokenizer=tokenizer, judge_version="1-deadbeef"
    )

    assert rows[0]["verdict"] == judge.VERDICT_SUPPORTED
    assert torch.equal(model.received_kwargs["input_ids"], input_ids)
    assert "attention_mask" not in model.received_kwargs
    assert model.received_kwargs["do_sample"] is False
    assert model.received_kwargs["temperature"] is None


# --------------------------------------------------------------------------
# 2. compute_judge_version
# --------------------------------------------------------------------------


def test_compute_judge_version_deterministic():
    first = judge.compute_judge_version(repo_id="org/judge", revision="rev1")
    second = judge.compute_judge_version(repo_id="org/judge", revision="rev1")
    assert first == second
    assert first.startswith(judge.JUDGE_VERSION_SCHEME + "-")


def test_compute_judge_version_changes_with_each_input():
    base = judge.compute_judge_version(repo_id="org/judge", revision="rev1")
    assert judge.compute_judge_version(repo_id="org/other", revision="rev1") != base
    assert judge.compute_judge_version(repo_id="org/judge", revision="rev2") != base
    assert (
        judge.compute_judge_version(repo_id="org/judge", revision="rev1", max_new_tokens=99) != base
    )
    assert (
        judge.compute_judge_version(
            repo_id="org/judge", revision="rev1", prompt_template="different"
        )
        != base
    )


@pytest.mark.parametrize(("repo_id", "revision"), [("", "rev1"), ("org/judge", ""), ("", "")])
def test_compute_judge_version_refuses_when_unpinned(repo_id, revision):
    with pytest.raises(judge.JudgeRefusal):
        judge.compute_judge_version(repo_id=repo_id, revision=revision)


# --------------------------------------------------------------------------
# 3. parse_verdict
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("VERDICT: supported", judge.VERDICT_SUPPORTED),
        ("VERDICT: not_supported", judge.VERDICT_NOT_SUPPORTED),
        ("VERDICT: unclear", judge.VERDICT_UNCLEAR),
        ("verdict: SUPPORTED", judge.VERDICT_SUPPORTED),
        ("VeRdIcT: Not_Supported", judge.VERDICT_NOT_SUPPORTED),
        (
            "Some prose explaining the reasoning.\nVERDICT: unclear\nreason: ambiguous",
            judge.VERDICT_UNCLEAR,
        ),
        ("", judge.VERDICT_UNPARSEABLE),
        ("this is junk with no verdict at all", judge.VERDICT_UNPARSEABLE),
        ("supported", judge.VERDICT_UNPARSEABLE),
        ("VERDICT: maybe", judge.VERDICT_UNPARSEABLE),
    ],
)
def test_parse_verdict_table(text, expected):
    assert judge.parse_verdict(text) == expected


def test_parse_verdict_not_supported_is_not_misread_as_supported():
    result = judge.parse_verdict("VERDICT: not_supported")
    assert result == judge.VERDICT_NOT_SUPPORTED
    assert result != judge.VERDICT_SUPPORTED


# --------------------------------------------------------------------------
# 4. select_targets
# --------------------------------------------------------------------------


def _write_corpus(tmp_path):
    path = tmp_path / "corpus.jsonl"
    records = [
        {
            "video_id": "vid1",
            "hms": "00:00:10",
            "narration": "price built a base for twelve bars near the high",
            "why": "shows consolidation before a breakout",
            "category": "concept",
            "label": "base",
        }
    ]
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return path


def test_select_targets_classifies_every_prediction_exactly_once(tmp_path):
    corpus_path = _write_corpus(tmp_path)
    corpus = evaluate_mod.load_corpus(corpus_path)

    good = {
        "task": "cited_qa",
        "meta": {"video_id": "vid1", "hms": "00:00:10"},
        "prediction": "Base forms over time.\nCitation: vid1 00:00:10",
    }
    conflict = {
        "task": evaluate_mod.CONFLICT_TASK,
        "meta": {"video_id": "vid1", "hms": "00:00:10"},
        "prediction": "conflicting accounts\nCitation: vid1 00:00:10",
    }
    no_citation = {
        "task": "cited_qa",
        "meta": {},
        "prediction": "no citation line here",
    }
    not_in_corpus = {
        "task": "cited_qa",
        "meta": {"video_id": "vidX", "hms": "00:00:10"},
        "prediction": "some claim\nCitation: vidX 00:00:10",
    }
    empty_claim = {
        "task": "cited_qa",
        "meta": {"video_id": "vid1", "hms": "00:00:10"},
        "prediction": "Citation: vid1 00:00:10",
    }
    predictions = [good, conflict, no_citation, not_in_corpus, empty_claim]

    targets, skipped = judge.select_targets(predictions, corpus)

    assert len(targets) == 1
    assert targets[0].claim == "Base forms over time."
    assert targets[0].video_id == "vid1"
    assert targets[0].hms == "00:00:10"
    assert "base for twelve bars" in targets[0].narration
    assert "Why: shows consolidation before a breakout" in targets[0].narration

    reasons = [row["skipped"] for row in skipped]
    assert sorted(reasons) == sorted(
        [
            judge.SKIP_CONFLICT_TASK,
            judge.SKIP_NO_CITATION,
            judge.SKIP_CITATION_NOT_IN_CORPUS,
            judge.SKIP_EMPTY_CLAIM,
        ]
    )
    assert len(targets) + len(skipped) == len(predictions)


# --------------------------------------------------------------------------
# 5. summarize
# --------------------------------------------------------------------------


def _row(example_id: str, verdict: str) -> dict:
    return {
        "example_id": example_id,
        "task": "cited_qa",
        "video_id": "vid1",
        "hms": "00:00:10",
        "verdict": verdict,
        "judge_raw": "...",
        "judge_version": "1-x",
    }


def test_summarize_counts_rates_and_digests():
    rows = [
        _row("e1", judge.VERDICT_SUPPORTED),
        _row("e2", judge.VERDICT_SUPPORTED),
        _row("e3", judge.VERDICT_NOT_SUPPORTED),
        _row("e4", judge.VERDICT_UNCLEAR),
    ]
    skipped = [{"example_id": "e5", "task": "cited_qa", "skipped": judge.SKIP_NO_CITATION}]
    scores = {
        "corpus_sha256": "csha",
        "eval_set_sha256": "esha",
        "scoring_version": "1",
        "eval": {"count": 5},
    }

    summary = judge.summarize(
        rows,
        skipped,
        judge_version="1-x",
        run_id="run1",
        repo_id="org/judge",
        revision="rev1",
        max_new_tokens=64,
        scores=scores,
        limit=None,
    )

    assert summary["judged"] == 4
    assert summary["skipped_total"] == 1
    assert summary["predictions_total"] == 5
    assert summary["verdict_counts"][judge.VERDICT_SUPPORTED] == 2
    assert summary["verdict_counts"][judge.VERDICT_NOT_SUPPORTED] == 1
    assert summary["verdict_rates"][judge.VERDICT_SUPPORTED] == pytest.approx(0.5)
    assert summary["skip_counts"][judge.SKIP_NO_CITATION] == 1
    assert summary["corpus_sha256"] == "csha"
    assert summary["eval_set_sha256"] == "esha"
    assert summary["scoring_version"] == "1"
    assert "eval" not in summary
    assert summary["subset"] is False
    assert "limit" not in summary
    assert "never gates" in summary["advisory"] or "advisory" in summary["advisory"].lower()


def test_summarize_rate_is_none_when_judged_is_zero_and_stamps_subset():
    summary = judge.summarize(
        [],
        [{"example_id": "e1", "task": "cited_qa", "skipped": judge.SKIP_NO_CITATION}],
        judge_version="1-x",
        run_id="run1",
        repo_id="org/judge",
        revision="rev1",
        max_new_tokens=64,
        scores=None,
        limit=3,
    )
    assert summary["judged"] == 0
    assert all(rate is None for rate in summary["verdict_rates"].values())
    assert summary["subset"] is True
    assert summary["limit"] == 3


# --------------------------------------------------------------------------
# 6. assert_single_judge_version
# --------------------------------------------------------------------------


def test_assert_single_judge_version_accepts_uniform_set():
    rows = [{"judge_version": "1-x"}, {"judge_version": "1-x"}]
    assert judge.assert_single_judge_version(rows) == "1-x"


def test_assert_single_judge_version_refuses_mixed_versions():
    with pytest.raises(judge.JudgeRefusal):
        judge.assert_single_judge_version([{"judge_version": "1-x"}, {"judge_version": "1-y"}])


def test_assert_single_judge_version_refuses_empty_input():
    with pytest.raises(judge.JudgeRefusal):
        judge.assert_single_judge_version([])


# --------------------------------------------------------------------------
# 7. guard_existing_outputs
# --------------------------------------------------------------------------


def test_guard_existing_outputs_refuses_different_judge_version(tmp_path):
    out_dir = tmp_path / "judge"
    out_dir.mkdir()
    (out_dir / judge.SUMMARY_NAME).write_text(
        json.dumps({"judge_version": "1-old"}), encoding="utf-8"
    )

    with pytest.raises(judge.JudgeRefusal):
        judge.guard_existing_outputs(out_dir, "1-new", force=False)


def test_guard_existing_outputs_allows_same_judge_version(tmp_path):
    out_dir = tmp_path / "judge"
    out_dir.mkdir()
    (out_dir / judge.SUMMARY_NAME).write_text(
        json.dumps({"judge_version": "1-same"}), encoding="utf-8"
    )

    judge.guard_existing_outputs(out_dir, "1-same", force=False)  # must not raise


def test_guard_existing_outputs_force_bypasses_refusal(tmp_path):
    out_dir = tmp_path / "judge"
    out_dir.mkdir()
    (out_dir / judge.SUMMARY_NAME).write_text(
        json.dumps({"judge_version": "1-old"}), encoding="utf-8"
    )

    judge.guard_existing_outputs(out_dir, "1-new", force=True)  # must not raise


def test_guard_existing_outputs_no_existing_summary_is_a_noop(tmp_path):
    out_dir = tmp_path / "judge"
    judge.guard_existing_outputs(out_dir, "1-new", force=False)  # must not raise


# --------------------------------------------------------------------------
# 7b. write_outputs
# --------------------------------------------------------------------------


def test_write_outputs_accounts_for_every_prediction(tmp_path):
    """judgements.jsonl must hold one line per prediction -- judged rows plus
    skipped rows -- so a reader can never mistake "skipped" for "judged and
    unsupported"."""
    rows = [_row("e1", judge.VERDICT_SUPPORTED), _row("e2", judge.VERDICT_NOT_SUPPORTED)]
    skipped = [
        {"example_id": "e3", "task": "cited_qa", "skipped": judge.SKIP_NO_CITATION},
        {
            "example_id": "e4",
            "task": evaluate_mod.CONFLICT_TASK,
            "skipped": judge.SKIP_CONFLICT_TASK,
        },
    ]
    summary = judge.summarize(
        rows,
        skipped,
        judge_version="1-x",
        run_id="run1",
        repo_id="org/judge",
        revision="rev1",
        max_new_tokens=64,
        scores=None,
        limit=None,
    )

    out_dir = tmp_path / "judge"
    judgements_path, summary_path = judge.write_outputs(out_dir, rows, skipped, summary)

    lines = [
        json.loads(line)
        for line in judgements_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == summary["predictions_total"] == 4
    assert [line["example_id"] for line in lines] == ["e1", "e2", "e3", "e4"]
    # judged rows carry a verdict + judge_version; skipped rows carry neither
    assert all("verdict" in line and "judge_version" in line for line in lines[:2])
    assert all("verdict" not in line and "skipped" in line for line in lines[2:])

    on_disk = json.loads(summary_path.read_text(encoding="utf-8"))
    assert on_disk["judge_version"] == "1-x"


def test_write_outputs_does_not_touch_the_runs_scores_or_predictions(tmp_path):
    """The judge is advisory: it must never modify the Tier-0/1 artifacts it reads."""
    run_dir = _write_run_dir(tmp_path)
    scores_path = run_dir / "evaluation" / "scores.json"
    scores_path.write_text(json.dumps({"scoring_version": "1"}), encoding="utf-8")
    predictions_path = run_dir / "evaluation" / "predictions.jsonl"
    before = (scores_path.read_bytes(), predictions_path.read_bytes())

    summary = judge.summarize(
        [], [], judge_version="1-x", run_id="run1", repo_id="org/judge",
        revision="rev1", max_new_tokens=64, scores=None, limit=None,
    )
    judge.write_outputs(run_dir / "evaluation" / judge.JUDGE_DIR_NAME, [], [], summary)

    assert (scores_path.read_bytes(), predictions_path.read_bytes()) == before


# --------------------------------------------------------------------------
# 8. CLI: --dry-run and missing required arg
# --------------------------------------------------------------------------


def _write_run_dir(tmp_path):
    run_dir = tmp_path / "run1"
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(parents=True)
    predictions = [
        {
            "task": "cited_qa",
            "meta": {"video_id": "vid1", "hms": "00:00:10"},
            "prediction": "Base forms over time.\nCitation: vid1 00:00:10",
        },
        {
            "task": "cited_qa",
            "meta": {},
            "prediction": "no citation here",
        },
    ]
    with (eval_dir / "predictions.jsonl").open("w", encoding="utf-8") as handle:
        for prediction in predictions:
            handle.write(json.dumps(prediction) + "\n")
    return run_dir


def _cpu_only_env():
    env = dict(os.environ)
    env["CUDA_VISIBLE_DEVICES"] = ""
    return env


def test_cli_dry_run_selects_targets_writes_no_files(tmp_path):
    run_dir = _write_run_dir(tmp_path)
    corpus_path = _write_corpus(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "stoic_training.judge",
            "--run-dir",
            str(run_dir),
            "--judge-repo-id",
            "org/judge-model",
            "--judge-revision",
            "deadbeef",
            "--corpus",
            str(corpus_path),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        env=_cpu_only_env(),
    )

    assert result.returncode == 0, result.stderr
    assert "judge_version:" in result.stdout
    assert "would judge:   1 of 2" in result.stdout
    assert not (run_dir / "evaluation" / "judge").exists()


def test_cli_missing_judge_revision_exits_nonzero(tmp_path):
    run_dir = _write_run_dir(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "stoic_training.judge",
            "--run-dir",
            str(run_dir),
            "--judge-repo-id",
            "org/judge-model",
        ],
        capture_output=True,
        text=True,
        env=_cpu_only_env(),
    )

    assert result.returncode != 0


# --------------------------------------------------------------------------
# 9. import hygiene
# --------------------------------------------------------------------------


def test_import_hygiene_no_torch_or_transformers_leaked():
    source = (
        "import sys; import stoic_training.judge; "
        "assert 'torch' not in sys.modules and 'transformers' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-c", source], capture_output=True, text=True, env=_cpu_only_env()
    )
    assert result.returncode == 0, result.stderr
