"""Split-version tooling: dev/holdout partitioning, sealing, quarantine.

Purpose guardrail: this governs how an OFFLINE research assistant's eval
data is partitioned; nothing here gates a live trading path, and no eval
score ever does (VISION.md, design doc section 7).

Pure stdlib -- no torch, no yaml, no import of `config.py` -- so both the
dataset builder and `evaluate.py` can import it anywhere.

Why this module exists (design doc section 5.1): individual runs are blind
to eval data, but *we* are not. Reading a score and picking the next
hyperparameter because it raised that score leaks the fixed eval sample
through our choices. The countermeasure is a two-tier eval set:

  - **dev** (`eval_dev.jsonl`) -- read every run, iterate freely;
  - **holdout** (`eval_holdout.jsonl`) -- SEALED. Scoring it requires an
    explicit `--unseal "<reason>"`, and every unsealing is appended to the
    committed ledger `splits/unseal-ledger.md`. Budget: single-digit
    unsealings per split version (design doc section 5.2).

Split files are immutable. `split-v2.json` does not restate or alter the
v1 train/eval boundary: it names its parent (`split-v1.json`) and only
subdivides that parent's `eval_videos` into `dev_videos` +
`holdout_videos`. `load_split_v2` re-reads the parent and refuses any v2
file whose dev+holdout is not exactly the parent's eval set, so a v2 can
never quietly promote an eval video into training.

The video stays the atomic split unit (design doc section 5.3,
non-negotiable): adjacent keyframes share narration and phrasing, so a
record-level split would score generalization we do not have.
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

SPLIT_V2_VERSION = "v2"
SPLIT_V2_PARENT = "v1"
# Distinct from v1's 20260724 so the dev/holdout partition is not correlated
# with the shuffle that produced the v1 train/eval boundary; it is the date
# split-v2.json was created.
SPLIT_V2_SEED = 20260725

ROLE_TRAIN = "train"
ROLE_DEV = "dev"
ROLE_HOLDOUT = "holdout"
EVAL_ROLES = (ROLE_DEV, ROLE_HOLDOUT)

DATASET_MANIFEST_NAME = "dataset_manifest.json"
UNSEAL_LEDGER_NAME = "unseal-ledger.md"

# Filename backstop for holdout detection: a copy of eval_holdout.jsonl made
# WITHOUT its dataset_manifest.json still trips the seal on its name alone.
HOLDOUT_FILENAME_STEMS = frozenset({"eval_holdout"})

# src/stoic_training/splits.py -> stoic_training -> src -> win_cuda
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPLITS_DIR = PACKAGE_ROOT / "splits"
DEFAULT_SPLIT_V1_PATH = DEFAULT_SPLITS_DIR / "split-v1.json"
DEFAULT_SPLIT_V2_PATH = DEFAULT_SPLITS_DIR / "split-v2.json"
DEFAULT_UNSEAL_LEDGER_PATH = DEFAULT_SPLITS_DIR / UNSEAL_LEDGER_NAME

UNSEAL_LEDGER_HEADER = """# Unseal ledger

Every scoring run against a **sealed holdout** eval set is appended here,
automatically, by `stoic_training.evaluate --unseal "<reason>"`. Refusing to
score the holdout without that flag -- and writing this file when it is
given -- is the mechanism that keeps the holdout a holdout.

Why (design doc `2026-07-24-eval-comparison-design.md` section 5.2): runs are
blind to eval data, but the iteration loop is not. Reading a score and
choosing the next change because it raised that score transmits information
about the fixed eval sample through our choices -- adaptive overfitting. The
dev set absorbs that pressure; the holdout only stays an honest estimate for
as long as it is rarely looked at.

**Budget: single-digit unsealings per split version.** Not a soft target. If
the count approaches ten, the holdout has been consumed: retire it and cut a
new split version rather than pretending the number still generalizes. Unseal
only to score a release candidate, never to check whether an idea worked.

New rows are appended by tooling; do not rewrite or delete history.

| run_id | date (UTC) | eval set | reason |
|---|---|---|---|
"""


class SplitError(RuntimeError):
    """Raised when a split file is malformed, inconsistent, or violated."""


class HoldoutSealedError(RuntimeError):
    """Raised when a sealed holdout eval set is scored without `--unseal`."""


def sha256_file(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# dev / holdout partitioning
# --------------------------------------------------------------------------


def partition_eval_videos(
    eval_videos: Iterable[str],
    *,
    seed: int = SPLIT_V2_SEED,
    holdout_target: int | None = None,
) -> tuple[list[str], list[str]]:
    """Seeded-deterministic dev/holdout partition of a parent split's eval videos.

    Procedure (documented verbatim in split-v2.json's `procedure` field so a
    reader can reproduce it without this source):

      1. sort the parent's `eval_videos` lexicographically -- the input order
         of a JSON list must never influence the outcome;
      2. shuffle that list with `random.Random(f"{seed}:v2")`;
      3. the first `holdout_target` entries are the holdout, the rest are dev;
      4. both lists are returned sorted.

    `holdout_target` defaults to `max(1, round(n / 3))`, capped at `n - 1` so
    the dev set is never empty. With n=3 that is a 2 dev / 1 holdout split.

    Deliberately NOT stratified by category: with exactly one eval video per
    category, stratification degenerates -- any 2/1 partition necessarily
    leaves one category unrepresented in dev and two unrepresented in
    holdout. Design doc section 5.3 accepts this coarseness explicitly ("with
    16 videos, any split is coarse"); the fix is more mined videos, not a
    cleverer partition of three.
    """
    videos = sorted(eval_videos)
    n = len(videos)
    if holdout_target is None:
        holdout_target = max(1, round(n / 3)) if n > 1 else 0
    holdout_target = max(0, min(holdout_target, max(n - 1, 0)))
    shuffled = list(videos)
    random.Random(f"{seed}:v2").shuffle(shuffled)
    holdout = sorted(shuffled[:holdout_target])
    dev = sorted(shuffled[holdout_target:])
    return dev, holdout


@dataclass(frozen=True, slots=True)
class SplitV2:
    """A validated split-v2 file, resolved against its parent split."""

    version: str
    parent_version: str
    parent_path: Path
    seed: int
    corpus_sha256: str
    train_videos: tuple[str, ...]
    dev_videos: tuple[str, ...]
    holdout_videos: tuple[str, ...]

    @property
    def eval_videos(self) -> tuple[str, ...]:
        return tuple(sorted(self.dev_videos + self.holdout_videos))

    def videos_for_role(self, role: str) -> tuple[str, ...]:
        if role == ROLE_TRAIN:
            return self.train_videos
        if role == ROLE_DEV:
            return self.dev_videos
        if role == ROLE_HOLDOUT:
            return self.holdout_videos
        raise SplitError(f"unknown split role: {role!r}")


def is_split_v2(payload: Mapping[str, Any]) -> bool:
    """True for a split file that subdivides a parent's eval set (auto-detection)."""
    return payload.get("version") == SPLIT_V2_VERSION or (
        "dev_videos" in payload and "holdout_videos" in payload
    )


def read_split_payload(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SplitError(f"cannot read split file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SplitError(f"invalid JSON in split file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SplitError(f"{path} must contain a JSON object")
    return payload


def load_split_v2(path: str | Path) -> SplitV2:
    """Read + validate a split-v2 file against the parent split it names.

    Validation is deliberately total, because every check here guards an
    invariant that would otherwise fail silently and poison a whole
    comparison lineage:

      - dev and holdout are disjoint and non-empty;
      - dev + holdout equals the parent's `eval_videos` EXACTLY -- a v2 that
        dropped an eval video would quietly shrink the eval set, and one that
        added a video would promote a training video into eval;
      - the parent's train set is disjoint from both (the v1 boundary is
        untouched, which is the whole point of subdividing rather than
        re-splitting);
      - corpus digests agree between v2 and its parent.
    """
    path = Path(path)
    payload = read_split_payload(path)
    if not is_split_v2(payload):
        raise SplitError(f"{path} is not a split-v2 file (version={payload.get('version')!r})")

    parent_name = payload.get("parent_split_file")
    if not isinstance(parent_name, str) or not parent_name:
        raise SplitError(f"{path} must name its parent via `parent_split_file`")
    parent_path = (path.parent / parent_name).resolve()
    if not parent_path.is_file():
        raise SplitError(f"{path} names parent split {parent_path}, which does not exist")
    parent = read_split_payload(parent_path)

    dev = payload.get("dev_videos")
    holdout = payload.get("holdout_videos")
    for name, value in (("dev_videos", dev), ("holdout_videos", holdout)):
        if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
            raise SplitError(f"{path}: {name} must be a non-empty list of video ids")

    dev_set, holdout_set = set(dev), set(holdout)
    overlap = dev_set & holdout_set
    if overlap:
        raise SplitError(f"{path}: dev and holdout overlap on {sorted(overlap)}")

    parent_eval = set(parent.get("eval_videos") or ())
    if dev_set | holdout_set != parent_eval:
        missing = sorted(parent_eval - (dev_set | holdout_set))
        extra = sorted((dev_set | holdout_set) - parent_eval)
        raise SplitError(
            f"{path}: dev+holdout must equal the parent's eval_videos exactly "
            f"(missing from v2: {missing}; not in parent eval: {extra}). The v1 "
            "train/eval boundary is immutable -- v2 only subdivides v1's eval set."
        )

    parent_train = list(parent.get("train_videos") or ())
    train_overlap = set(parent_train) & (dev_set | holdout_set)
    if train_overlap:
        raise SplitError(
            f"{parent_path}: train videos {sorted(train_overlap)} also appear in the "
            "v2 eval partition -- the parent split is inconsistent"
        )

    corpus_sha256 = payload.get("corpus_sha256")
    if not isinstance(corpus_sha256, str) or not corpus_sha256:
        raise SplitError(f"{path}: corpus_sha256 must be a non-empty string")
    if parent.get("corpus_sha256") != corpus_sha256:
        raise SplitError(
            f"{path}: corpus_sha256 {corpus_sha256} does not match parent "
            f"{parent_path} ({parent.get('corpus_sha256')}). A v2 must be frozen "
            "against the same corpus as its parent."
        )

    seed = payload.get("seed", SPLIT_V2_SEED)
    if not isinstance(seed, int):
        raise SplitError(f"{path}: seed must be an integer")

    return SplitV2(
        version=str(payload.get("version") or SPLIT_V2_VERSION),
        parent_version=str(parent.get("version") or SPLIT_V2_PARENT),
        parent_path=parent_path,
        seed=seed,
        corpus_sha256=corpus_sha256,
        train_videos=tuple(sorted(parent_train)),
        dev_videos=tuple(sorted(dev)),
        holdout_videos=tuple(sorted(holdout)),
    )


def quarantine_new_videos(
    corpus_video_ids: Iterable[str], split: SplitV2
) -> list[str]:
    """Videos present in the corpus but absent from the split, sorted.

    Design doc section 5.2 refresh path: "newly mined videos are quarantined
    into the holdout pool by default (they are the truly-unseen future)".
    Split files are immutable, so the enforcement point is the dataset
    builder -- this function only *identifies* the quarantine set; routing it
    into the holdout eval file (or failing) is `build_dataset`'s job. What is
    never allowed is the silent third option: a new video drifting into train
    or dev because nobody looked.
    """
    known = set(split.train_videos) | set(split.dev_videos) | set(split.holdout_videos)
    return sorted({video_id for video_id in corpus_video_ids} - known)


# --------------------------------------------------------------------------
# holdout sealing
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HoldoutDetection:
    """Why a given eval file was judged to be a sealed holdout set."""

    path: Path
    sha256: str | None
    reason: str
    manifest_path: Path | None


def read_dataset_manifest(path: str | Path) -> dict[str, Any] | None:
    """Read a dataset_manifest.json, or None if it is absent/unreadable.

    Unreadable is deliberately not fatal: a malformed manifest must not stop
    ad-hoc scoring of an unrelated file. The filename backstop in
    `detect_holdout` still applies.
    """
    path = Path(path)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def manifest_holdout_sha256s(manifest: Mapping[str, Any] | None) -> set[str]:
    """Every file sha256 the manifest marks with role "holdout"."""
    if not manifest:
        return set()
    files = manifest.get("files")
    if not isinstance(files, Mapping):
        return set()
    digests: set[str] = set()
    for entry in files.values():
        if isinstance(entry, Mapping) and entry.get("role") == ROLE_HOLDOUT:
            digest = entry.get("sha256")
            if isinstance(digest, str) and digest:
                digests.add(digest)
    return digests


def detect_holdout(eval_path: str | Path | None) -> HoldoutDetection | None:
    """Decide whether `eval_path` is a sealed holdout eval set.

    Two independent detectors, either of which seals the file:

      1. **Content digest** (primary, rename-proof): the file's sha256
         matches a sha256 that the `dataset_manifest.json` *sitting next to
         it* records with `role == "holdout"`. Renaming eval_holdout.jsonl to
         `notes.jsonl` changes nothing -- the bytes are the same.
      2. **Filename backstop**: the file's stem is `eval_holdout`, even with
         no manifest beside it. This catches the copy-it-somewhere-else
         bypass, where the manifest was left behind.

    Both are cheap and neither fires for ad-hoc files, so scoring a
    hand-made predictions/eval file stays friction-free: no manifest, no
    holdout name, no refusal.

    Returns None when the path is None/missing or neither detector fires.
    """
    if eval_path is None:
        return None
    path = Path(eval_path)
    if not path.is_file():
        return None

    manifest_path = path.parent / DATASET_MANIFEST_NAME
    manifest = read_dataset_manifest(manifest_path)
    holdout_digests = manifest_holdout_sha256s(manifest)
    digest: str | None = None
    if holdout_digests:
        digest = sha256_file(path)
        if digest in holdout_digests:
            return HoldoutDetection(
                path=path,
                sha256=digest,
                reason=(
                    f"content sha256 {digest[:16]}... is recorded with role "
                    f'"{ROLE_HOLDOUT}" in {manifest_path}'
                ),
                manifest_path=manifest_path,
            )

    if path.stem in HOLDOUT_FILENAME_STEMS:
        return HoldoutDetection(
            path=path,
            sha256=digest if digest is not None else sha256_file(path),
            reason=f"filename stem {path.stem!r} is reserved for sealed holdout eval sets",
            manifest_path=manifest_path if manifest is not None else None,
        )
    return None


def seal_message(detection: HoldoutDetection) -> str:
    return (
        f"refusing to score a SEALED HOLDOUT eval set: {detection.path}\n"
        f"  detected because {detection.reason}\n"
        "  The holdout is scored only when promoting a release candidate "
        "(design doc section 5.2). Iterate against eval_dev.jsonl instead.\n"
        '  To proceed deliberately, re-run with --unseal "<reason>"; the run id, '
        f"date and reason are appended to {DEFAULT_UNSEAL_LEDGER_PATH}.\n"
        "  Budget: single-digit unsealings per split version."
    )


def ensure_unseal_ledger(ledger_path: str | Path = DEFAULT_UNSEAL_LEDGER_PATH) -> Path:
    """Create the ledger with its header if absent; return its path."""
    path = Path(ledger_path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(UNSEAL_LEDGER_HEADER, encoding="utf-8")
    return path


def _escape_cell(text: str) -> str:
    """Make a value safe for a one-line markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def append_unseal_entry(
    *,
    run_id: str,
    reason: str,
    eval_set: str,
    date: str | None = None,
    ledger_path: str | Path = DEFAULT_UNSEAL_LEDGER_PATH,
) -> Path:
    """Append one row to the committed unseal ledger. Never rewrites history.

    Append-only for the same reason `runs/index.jsonl` is: a ledger you can
    quietly edit measures nothing.
    """
    path = ensure_unseal_ledger(ledger_path)
    when = date or datetime.now(UTC).isoformat()
    row = (
        f"| {_escape_cell(run_id)} | {_escape_cell(when)} | "
        f"{_escape_cell(eval_set)} | {_escape_cell(reason)} |\n"
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(row)
    return path


def count_unseal_entries(ledger_path: str | Path = DEFAULT_UNSEAL_LEDGER_PATH) -> int:
    """Number of recorded unsealings (data rows of the ledger table)."""
    path = Path(ledger_path)
    if not path.is_file():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or cells[0] in {"run_id", ""} or set(cells[0]) <= {"-", ":"}:
            continue
        count += 1
    return count


def build_split_v2_payload(
    *,
    parent: Mapping[str, Any],
    parent_file: str,
    seed: int = SPLIT_V2_SEED,
    dev_videos: Sequence[str] | None = None,
    holdout_videos: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Assemble the split-v2 JSON payload (used to generate splits/split-v2.json).

    Kept in-code rather than hand-written-only so the committed file is
    reproducible: regenerating it from split-v1.json must yield the same
    dev/holdout assignment, which is what makes the seeded procedure a claim
    anyone can check rather than a story about how the file was made.
    """
    if dev_videos is None or holdout_videos is None:
        dev_videos, holdout_videos = partition_eval_videos(
            parent.get("eval_videos") or (), seed=seed
        )
    return {
        "version": SPLIT_V2_VERSION,
        "parent_split": parent.get("version") or SPLIT_V2_PARENT,
        "parent_split_file": parent_file,
        "seed": seed,
        "corpus_sha256": parent.get("corpus_sha256"),
        "dev_videos": sorted(dev_videos),
        "holdout_videos": sorted(holdout_videos),
    }


__all__ = [
    "DATASET_MANIFEST_NAME",
    "DEFAULT_SPLITS_DIR",
    "DEFAULT_SPLIT_V1_PATH",
    "DEFAULT_SPLIT_V2_PATH",
    "DEFAULT_UNSEAL_LEDGER_PATH",
    "EVAL_ROLES",
    "ROLE_DEV",
    "ROLE_HOLDOUT",
    "ROLE_TRAIN",
    "SPLIT_V2_SEED",
    "SPLIT_V2_VERSION",
    "HoldoutDetection",
    "HoldoutSealedError",
    "SplitError",
    "SplitV2",
    "append_unseal_entry",
    "build_split_v2_payload",
    "count_unseal_entries",
    "detect_holdout",
    "ensure_unseal_ledger",
    "is_split_v2",
    "load_split_v2",
    "manifest_holdout_sha256s",
    "partition_eval_videos",
    "quarantine_new_videos",
    "read_dataset_manifest",
    "read_split_payload",
    "seal_message",
    "sha256_file",
]
