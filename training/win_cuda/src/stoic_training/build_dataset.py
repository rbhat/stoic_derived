"""Deterministic SFT dataset builder for the offline research-assistant SLM.

Reads the course corpus (edu/derived/dataset.jsonl), freezes (or verifies)
a video-level train/eval split, and emits SFT examples for three task
templates: rule_candidate, cited_qa, conflict_check. Stdlib only -- no
torch/datasets imports -- so this runs anywhere, not just on the GPU box.

The split file (splits/split-v1.json) is generated once and then treated
as immutable: if it already exists, its corpus_sha256 must match the
current corpus or the build fails loudly rather than silently drifting.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from pathlib import Path

BUILDER_VERSION = "1"
SPLIT_VERSION = "v1"
SPLIT_SEED = 20260724
EVAL_VIDEO_TARGET = 3

SYSTEM_PROMPT = (
    "You are an offline Stoic-trading research assistant. You answer only "
    "from the cited course material and always cite video_id + hms. Your "
    "proposals are candidates for human review, never trading signals."
)

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parent.parent
DEFAULT_CORPUS = REPO_ROOT / "edu" / "derived" / "dataset.jsonl"
DEFAULT_SPLIT_PATH = PACKAGE_ROOT / "splits" / "split-v1.json"


class SplitMismatchError(RuntimeError):
    pass


def default_out_dir() -> Path:
    """`$STOIC_TRAIN_HOME/datasets/v1`, defaulting under `<repo>/.artifacts/`.

    Kept in lockstep with config.default_train_home(); the default is
    inlined here rather than imported so this builder stays stdlib-only.
    """
    env = os.environ.get("STOIC_TRAIN_HOME")
    home = Path(env).expanduser() if env else REPO_ROOT / ".artifacts" / "training"
    return home / "datasets" / "v1"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_corpus(path: Path):
    raw = path.read_bytes()
    digest = sha256_bytes(raw)
    records = []
    for line in raw.decode("utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))
    return records, digest


def videos_by_category(records):
    order = {}
    for r in records:
        order.setdefault(r["video_id"], r["category"])
    by_cat = {}
    for vid, cat in order.items():
        by_cat.setdefault(cat, []).append(vid)
    for cat in by_cat:
        by_cat[cat].sort()
    return by_cat


def _adjust_counts(counts, sizes, categories, target):
    total = sum(counts.values())
    i = 0
    guard = 1000 * max(len(categories), 1)
    while total < target and i < guard:
        cat = categories[i % len(categories)]
        n = sizes[cat]
        cap = n - 1 if n > 1 else 0
        if counts[cat] < cap:
            counts[cat] += 1
            total += 1
        i += 1
    i = 0
    while total > target and i < guard:
        cat = categories[i % len(categories)]
        if counts[cat] > 0:
            counts[cat] -= 1
            total -= 1
        i += 1
    return counts


def generate_split(records, seed: int = SPLIT_SEED, eval_target: int = EVAL_VIDEO_TARGET):
    by_cat = videos_by_category(records)
    categories = sorted(by_cat)
    n_videos = sum(len(v) for v in by_cat.values())
    eval_target = min(eval_target, max(n_videos - 1, 0))

    shuffled = {}
    for cat in categories:
        vids = list(by_cat[cat])
        rng = random.Random(f"{seed}:{cat}")
        rng.shuffle(vids)
        shuffled[cat] = vids

    sizes = {cat: len(shuffled[cat]) for cat in categories}
    counts = {}
    for cat in categories:
        n = sizes[cat]
        frac = (eval_target / n_videos) if n_videos else 0
        k = round(n * frac)
        counts[cat] = max(0, min(k, n - 1)) if n > 1 else 0
    counts = _adjust_counts(counts, sizes, categories, eval_target)

    train_videos = []
    eval_videos = []
    for cat in categories:
        k = counts[cat]
        vids = shuffled[cat]
        eval_videos.extend(vids[:k])
        train_videos.extend(vids[k:])
    return sorted(train_videos), sorted(eval_videos)


def load_or_create_split(records, split_path: Path, corpus_sha256: str, seed: int = SPLIT_SEED):
    if split_path.exists():
        data = json.loads(split_path.read_text(encoding="utf-8"))
        if data.get("corpus_sha256") != corpus_sha256:
            raise SplitMismatchError(
                f"corpus_sha256 mismatch for {split_path}: split was frozen "
                f"against {data.get('corpus_sha256')}, current corpus is "
                f"{corpus_sha256}. The split is immutable -- regenerate "
                "deliberately under a new version rather than overwriting it."
            )
        return data

    train_videos, eval_videos = generate_split(records, seed=seed)
    data = {
        "version": SPLIT_VERSION,
        "seed": seed,
        "corpus_sha256": corpus_sha256,
        "train_videos": train_videos,
        "eval_videos": eval_videos,
    }
    split_path.parent.mkdir(parents=True, exist_ok=True)
    split_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


def group_by_video(records):
    grouped = {}
    for r in records:
        grouped.setdefault(r["video_id"], []).append(r)
    for vid in grouped:
        grouped[vid] = sorted(grouped[vid], key=lambda r: r["t"])
    return grouped


def narration_window(video_records, idx: int) -> str:
    parts = []
    if idx > 0:
        parts.append(video_records[idx - 1]["narration"])
    parts.append(video_records[idx]["narration"])
    if idx < len(video_records) - 1:
        parts.append(video_records[idx + 1]["narration"])
    return "\n".join(p for p in parts if p)


def _example(task: str, user: str, assistant: str, record) -> dict:
    return {
        "task": task,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ],
        "meta": {
            "video_id": record["video_id"],
            "hms": record["hms"],
            "category": record["category"],
        },
    }


def make_rule_candidate(record, window_text: str) -> dict:
    user = (
        f"Narration window (video {record['video_id']}, around {record['hms']}):\n"
        f"\"{window_text}\"\n\n"
        "Based on this narration window, propose a structured rule candidate."
    )
    assistant = (
        f"Rule candidate: {record['label']}\n"
        f"Setup / entry condition: {record['why']}\n"
        "Invalidation / caveat: not specified in the cited material\n"
        f"Citation: {record['video_id']} {record['hms']}"
    )
    return _example("rule_candidate", user, assistant, record)


def make_cited_qa(record) -> dict:
    user = f'What does the course say about "{record["label"]}"?'
    assistant = (
        f"{record['why']}\n\n"
        f"Source narration: \"{record['narration']}\"\n"
        f"Citation: {record['video_id']} {record['hms']}"
    )
    return _example("cited_qa", user, assistant, record)


def find_conflicts(records):
    """Pair records with an identical label from different videos whose
    why text disagrees. One representative (earliest by t) is taken per
    (label, video); representatives are sorted by video_id and paired off
    consecutively so the pairing is fully deterministic."""
    by_label = {}
    for r in records:
        if not r["label"] or not r["why"]:
            continue
        by_label.setdefault(r["label"], {}).setdefault(r["video_id"], []).append(r)

    pairs = []
    for label in sorted(by_label):
        video_map = by_label[label]
        video_ids = sorted(video_map)
        reps = [sorted(video_map[vid], key=lambda r: r["t"])[0] for vid in video_ids]
        for i in range(0, len(reps) - 1, 2):
            rec_a, rec_b = reps[i], reps[i + 1]
            if rec_a["why"] != rec_b["why"]:
                pairs.append((rec_a, rec_b))
    return pairs


def make_conflict(rec_a, rec_b) -> dict:
    user = (
        f'Two course segments both use the label "{rec_a["label"]}" but appear '
        "to give different guidance.\n"
        f'Excerpt A ({rec_a["video_id"]} {rec_a["hms"]}): "{rec_a["why"]}"\n'
        f'Excerpt B ({rec_b["video_id"]} {rec_b["hms"]}): "{rec_b["why"]}"\n'
        "Do these agree?"
    )
    assistant = (
        "These excerpts do not fully agree and should not be silently merged.\n"
        f"Citation: {rec_a['video_id']} {rec_a['hms']}\n"
        f"Citation: {rec_b['video_id']} {rec_b['hms']}\n"
        "This discrepancy is an unresolved question for the human rulebook "
        "decision queue."
    )
    example = _example("conflict_check", user, assistant, rec_a)
    example["meta"]["video_id_b"] = rec_b["video_id"]
    example["meta"]["hms_b"] = rec_b["hms"]
    example["meta"]["category_b"] = rec_b["category"]
    return example


def build_examples(records, train_videos, eval_videos):
    train_set = set(train_videos)
    eval_set = set(eval_videos)
    grouped = group_by_video(records)

    train_examples = []
    eval_examples = []

    def bucket_for(video_id):
        if video_id in train_set:
            return train_examples
        if video_id in eval_set:
            return eval_examples
        return None

    for video_id in sorted(grouped):
        target = bucket_for(video_id)
        if target is None:
            continue
        video_records = grouped[video_id]
        for idx, r in enumerate(video_records):
            if r["label"] and r["why"]:
                target.append(make_rule_candidate(r, narration_window(video_records, idx)))
        for r in video_records:
            if r["label"] and r["why"]:
                target.append(make_cited_qa(r))

    for rec_a, rec_b in find_conflicts(records):
        if rec_a["video_id"] in train_set and rec_b["video_id"] in train_set:
            train_examples.append(make_conflict(rec_a, rec_b))
        elif rec_a["video_id"] in eval_set and rec_b["video_id"] in eval_set:
            eval_examples.append(make_conflict(rec_a, rec_b))
        # cross-split pairs are dropped: pairing videos across train/eval
        # would leak eval material into a train example (or vice versa).

    return train_examples, eval_examples


def write_jsonl(path: Path, examples) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False))
            f.write("\n")


def task_counts(examples) -> dict:
    counts = {}
    for ex in examples:
        counts[ex["task"]] = counts.get(ex["task"], 0) + 1
    return counts


def build_manifest(corpus_sha256: str, split, train_examples, eval_examples) -> dict:
    return {
        "corpus_sha256": corpus_sha256,
        "split_version": split["version"],
        "counts": {
            "train": task_counts(train_examples),
            "eval": task_counts(eval_examples),
        },
        "builder_version": BUILDER_VERSION,
    }


def print_summary(split, train_examples, eval_examples, out_dir: Path) -> None:
    train_counts = task_counts(train_examples)
    eval_counts = task_counts(eval_examples)
    tasks = sorted(set(train_counts) | set(eval_counts))

    print(f"split: {split['version']} seed={split['seed']}")
    print(f"train videos ({len(split['train_videos'])}): {', '.join(split['train_videos'])}")
    print(f"eval videos ({len(split['eval_videos'])}): {', '.join(split['eval_videos'])}")
    print(f"output: {out_dir}")
    print(f"{'task':<18}{'train':>8}{'eval':>8}")
    for task in tasks:
        print(f"{task:<18}{train_counts.get(task, 0):>8}{eval_counts.get(task, 0):>8}")
    print(f"{'total':<18}{len(train_examples):>8}{len(eval_examples):>8}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build SFT dataset from the course corpus")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT_PATH)
    args = parser.parse_args(argv)

    out_dir = args.out if args.out is not None else default_out_dir()

    if not args.corpus.exists():
        print(f"error: corpus not found: {args.corpus}", file=sys.stderr)
        return 1

    records, corpus_sha256 = load_corpus(args.corpus)

    try:
        split = load_or_create_split(records, args.split, corpus_sha256)
    except SplitMismatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    train_examples, eval_examples = build_examples(
        records, split["train_videos"], split["eval_videos"]
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_dir / "train.jsonl", train_examples)
    write_jsonl(out_dir / "eval.jsonl", eval_examples)

    manifest = build_manifest(corpus_sha256, split, train_examples, eval_examples)
    (out_dir / "dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print_summary(split, train_examples, eval_examples, out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
