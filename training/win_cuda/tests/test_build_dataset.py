"""Tests for the deterministic SFT dataset builder.

Uses a small synthetic corpus written to tmp_path -- never touches the real
edu/derived/dataset.jsonl -- so this suite passes on any machine, CPU-only,
no network.
"""

from __future__ import annotations

import json
import re

from stoic_training import build_dataset


def _rec(video_id, category, t, label="", why="", narration=None):
    hms = f"00:{t // 60:02d}:{t % 60:02d}"
    return {
        "video_id": video_id,
        "category": category,
        "title": video_id.replace("_", " ").title(),
        "t": t,
        "hms": hms,
        "image": f"{video_id}/keyframes/{t:04d}.jpg",
        "source": "llm" if (label and why) else "drift",
        "label": label,
        "why": why,
        "narration": narration if narration is not None else f"narration for {video_id} at {t}",
        "caption": "",
    }


def synthetic_records():
    records = []
    # concept category: 2 videos
    records += [
        _rec("c1_intro", "concept", 0, "risk sizing", "Instructor explains position sizing by ATR."),
        _rec("c1_intro", "concept", 10),
        _rec("c1_intro", "concept", 20, "entry timing", "Wait for the retest before entering."),
    ]
    records += [
        _rec("c2_structure", "concept", 0),
        _rec("c2_structure", "concept", 15, "market structure", "Higher highs and higher lows define an uptrend."),
    ]
    # case_study category: 2 videos
    records += [
        _rec("cs1_gold", "case_study", 0, "risk sizing", "Use half size on gold due to volatility."),
        _rec("cs1_gold", "case_study", 12),
    ]
    records += [
        _rec("cs2_nq", "case_study", 0, "consolidation leads to expansion", "Tight range often precedes a breakout."),
        _rec("cs2_nq", "case_study", 30),
    ]
    # live_session category: 2 videos
    records += [
        _rec("live1_nq", "live_session", 0, "stop placement", "Stops go beyond the swing point, not at round numbers."),
        _rec("live1_nq", "live_session", 8),
    ]
    records += [
        _rec("live2_cl", "live_session", 0),
        _rec("live2_cl", "live_session", 5, "stop placement", "Place stops outside recent liquidity, using ATR as a buffer."),
    ]
    return records


def write_corpus(tmp_path, records):
    path = tmp_path / "dataset.jsonl"
    lines = [json.dumps(r, ensure_ascii=False) for r in records]
    raw = ("\n".join(lines) + "\n").encode("utf-8")
    path.write_bytes(raw)
    digest = build_dataset.sha256_bytes(raw)
    return path, digest


def run_builder(corpus_path, out_dir, split_path):
    rc = build_dataset.main(
        [
            "--corpus",
            str(corpus_path),
            "--out",
            str(out_dir),
            "--split",
            str(split_path),
        ]
    )
    return rc


def read_jsonl(path):
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_split_is_by_video_no_overlap(tmp_path):
    records = synthetic_records()
    corpus_path, _ = write_corpus(tmp_path, records)
    split_path = tmp_path / "split-v1.json"
    out_dir = tmp_path / "out"

    rc = run_builder(corpus_path, out_dir, split_path)
    assert rc == 0

    split = json.loads(split_path.read_text())
    train = set(split["train_videos"])
    eval_ = set(split["eval_videos"])
    assert train.isdisjoint(eval_)
    assert train | eval_ == {r["video_id"] for r in records}
    # all 6 synthetic videos accounted for
    assert len(train) + len(eval_) == 6


def test_split_immutability_on_corpus_change(tmp_path):
    records = synthetic_records()
    corpus_path, digest = write_corpus(tmp_path, records)
    split_path = tmp_path / "split-v1.json"
    out_dir = tmp_path / "out"

    # freeze a split file against a bogus digest
    split_path.write_text(
        json.dumps(
            {
                "version": "v1",
                "seed": build_dataset.SPLIT_SEED,
                "corpus_sha256": "0" * 64,
                "train_videos": ["c1_intro"],
                "eval_videos": ["c2_structure"],
            }
        )
    )

    rc = run_builder(corpus_path, out_dir, split_path)
    assert rc != 0
    # no dataset output should have been written
    assert not (out_dir / "train.jsonl").exists()


def test_determinism_byte_identical_across_runs(tmp_path):
    records = synthetic_records()
    corpus_path, _ = write_corpus(tmp_path, records)
    split_path = tmp_path / "split-v1.json"
    out_dir_1 = tmp_path / "out1"
    out_dir_2 = tmp_path / "out2"

    rc1 = run_builder(corpus_path, out_dir_1, split_path)
    rc2 = run_builder(corpus_path, out_dir_2, split_path)
    assert rc1 == 0 and rc2 == 0

    for name in ("train.jsonl", "eval.jsonl"):
        b1 = (out_dir_1 / name).read_bytes()
        b2 = (out_dir_2 / name).read_bytes()
        assert b1 == b2, f"{name} differs across runs"


def test_rule_candidate_and_cited_qa_only_for_labelled_records(tmp_path):
    records = synthetic_records()
    corpus_path, _ = write_corpus(tmp_path, records)
    split_path = tmp_path / "split-v1.json"
    out_dir = tmp_path / "out"

    rc = run_builder(corpus_path, out_dir, split_path)
    assert rc == 0

    all_examples = read_jsonl(out_dir / "train.jsonl") + read_jsonl(out_dir / "eval.jsonl")
    labelled_video_hms = {
        (r["video_id"], r["hms"]) for r in records if r["label"] and r["why"]
    }

    citation_re = re.compile(r"Citation: (\S+) (\d{2}:\d{2}:\d{2})$")

    for ex in all_examples:
        if ex["task"] not in ("rule_candidate", "cited_qa"):
            continue
        key = (ex["meta"]["video_id"], ex["meta"]["hms"])
        assert key in labelled_video_hms

        assistant_msg = ex["messages"][-1]["content"]
        assert assistant_msg.endswith("\n" + f"Citation: {key[0]} {key[1]}") or assistant_msg.endswith(
            f"Citation: {key[0]} {key[1]}"
        )
        m = citation_re.search(assistant_msg)
        assert m is not None, f"no trailing citation in: {assistant_msg!r}"
        assert m.group(1) == key[0]
        assert m.group(2) == key[1]

    # every labelled record produced exactly one rule_candidate and one cited_qa
    produced_rc = {
        (ex["meta"]["video_id"], ex["meta"]["hms"])
        for ex in all_examples
        if ex["task"] == "rule_candidate"
    }
    produced_qa = {
        (ex["meta"]["video_id"], ex["meta"]["hms"])
        for ex in all_examples
        if ex["task"] == "cited_qa"
    }
    assert produced_rc == labelled_video_hms
    assert produced_qa == labelled_video_hms


def test_conflict_examples_cite_both_source_videos(tmp_path):
    records = synthetic_records()
    corpus_path, digest = write_corpus(tmp_path, records)
    out_dir = tmp_path / "out"

    # Pin the split so the two "risk sizing" videos (c1_intro, cs1_gold),
    # which carry the same label with differing why text, land in the same
    # split -- otherwise conflict pairing across train/eval is intentionally
    # skipped to avoid leakage.
    split_path = tmp_path / "split-v1.json"
    split_path.write_text(
        json.dumps(
            {
                "version": "v1",
                "seed": build_dataset.SPLIT_SEED,
                "corpus_sha256": digest,
                "train_videos": ["c1_intro", "cs1_gold", "c2_structure", "cs2_nq"],
                "eval_videos": ["live1_nq", "live2_cl"],
            }
        )
    )

    rc = run_builder(corpus_path, out_dir, split_path)
    assert rc == 0

    train_examples = read_jsonl(out_dir / "train.jsonl")
    conflicts = [ex for ex in train_examples if ex["task"] == "conflict_check"]
    assert len(conflicts) >= 1

    conflict = conflicts[0]
    assistant_msg = conflict["messages"][-1]["content"]
    assert "c1_intro" in assistant_msg
    assert "cs1_gold" in assistant_msg
    assert "00:00:00" in assistant_msg
    assert conflict["meta"]["video_id"] in ("c1_intro", "cs1_gold")
    assert conflict["meta"]["video_id_b"] in ("c1_intro", "cs1_gold")
    assert conflict["meta"]["video_id"] != conflict["meta"]["video_id_b"]


def test_no_fabricated_conflicts_when_none_exist(tmp_path):
    # Corpus with no repeated labels across videos at all.
    records = [
        _rec("v1", "concept", 0, "unique label one", "why one"),
        _rec("v2", "case_study", 0, "unique label two", "why two"),
    ]
    corpus_path, _ = write_corpus(tmp_path, records)
    split_path = tmp_path / "split-v1.json"
    out_dir = tmp_path / "out"

    rc = run_builder(corpus_path, out_dir, split_path)
    assert rc == 0

    all_examples = read_jsonl(out_dir / "train.jsonl") + read_jsonl(out_dir / "eval.jsonl")
    conflicts = [ex for ex in all_examples if ex["task"] == "conflict_check"]
    assert conflicts == []


def test_manifest_counts_match_files(tmp_path):
    records = synthetic_records()
    corpus_path, digest = write_corpus(tmp_path, records)
    split_path = tmp_path / "split-v1.json"
    out_dir = tmp_path / "out"

    rc = run_builder(corpus_path, out_dir, split_path)
    assert rc == 0

    manifest = json.loads((out_dir / "dataset_manifest.json").read_text())
    assert manifest["corpus_sha256"] == digest
    assert manifest["split_version"] == "v1"

    train_examples = read_jsonl(out_dir / "train.jsonl")
    eval_examples = read_jsonl(out_dir / "eval.jsonl")
    assert manifest["counts"]["train"] == build_dataset.task_counts(train_examples)
    assert manifest["counts"]["eval"] == build_dataset.task_counts(eval_examples)
