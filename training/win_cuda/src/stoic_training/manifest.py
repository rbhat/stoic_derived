"""Content-addressed run manifests for the offline research-assistant SLM.

Purpose guardrail: this records provenance for training an OFFLINE research
assistant that proposes cited rule candidates for human review; its output
never touches any live trading path.

Pure stdlib (plus `git` via subprocess). No torch/transformers/etc. import,
so this module stays cheap to import from tests and from train.py at
startup. Library versions are read via `importlib.metadata` rather than by
importing the libraries themselves.

The run_id is the sha256 (first 16 hex chars) of the canonical JSON of the
manifest's *identity* fields: dataset, config, code revision, base model,
and library versions. It deliberately excludes `created_utc` (wall-clock,
non-reproducible) and `outputs` (only known after the run finishes), so
identical inputs always produce the same run_id regardless of when or how
many times the manifest is built.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

_LIBRARIES = ("torch", "transformers", "peft", "trl", "bitsandbytes")


class ManifestError(ValueError):
    """Raised when a run manifest cannot be built or is malformed."""


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Encode an already-normalized mapping as canonical UTF-8 JSON."""
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def sha256_file(path: Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_hex(value: Mapping[str, Any]) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()


def sha256_dir(path: str | Path) -> str:
    """Deterministic sha256 over every file under path (relative path + content hash)."""
    path = Path(path)
    entries = [
        f"{file_path.relative_to(path).as_posix()}:{sha256_file(file_path)}"
        for file_path in sorted(p for p in path.rglob("*") if p.is_file())
    ]
    return sha256("\n".join(entries).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class DatasetRef:
    """Digest identity of the dataset a run trains/evaluates against."""

    corpus_sha256: str
    dataset_manifest_sha256: str
    train_sha256: str
    eval_sha256: str

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "corpus_sha256": self.corpus_sha256,
            "dataset_manifest_sha256": self.dataset_manifest_sha256,
            "train_sha256": self.train_sha256,
            "eval_sha256": self.eval_sha256,
        }


def load_dataset_ref(dataset_dir: str | Path) -> DatasetRef:
    """Read dataset_manifest.json + hash train/eval.jsonl under dataset_dir.

    corpus_sha256 is trusted from dataset_manifest.json (written by the
    dataset-builder component); this function does not recompute it from
    the source corpus.
    """
    dataset_dir = Path(dataset_dir)
    manifest_path = dataset_dir / "dataset_manifest.json"
    train_path = dataset_dir / "train.jsonl"
    eval_path = dataset_dir / "eval.jsonl"
    for path in (manifest_path, train_path, eval_path):
        if not path.is_file():
            raise ManifestError(f"missing required dataset file: {path}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"invalid JSON in {manifest_path}: {exc}") from exc
    if not isinstance(payload, dict) or "corpus_sha256" not in payload:
        raise ManifestError(f"{manifest_path} must contain corpus_sha256")
    corpus_sha256 = payload["corpus_sha256"]
    if not isinstance(corpus_sha256, str) or not corpus_sha256:
        raise ManifestError(f"{manifest_path} corpus_sha256 must be a non-empty string")
    return DatasetRef(
        corpus_sha256=corpus_sha256,
        dataset_manifest_sha256=sha256_file(manifest_path),
        train_sha256=sha256_file(train_path),
        eval_sha256=sha256_file(eval_path),
    )


@dataclass(frozen=True, slots=True)
class CodeRev:
    sha: str
    dirty: bool

    def canonical_dict(self) -> dict[str, Any]:
        return {"sha": self.sha, "dirty": self.dirty}


def git_rev(repo_dir: str | Path) -> CodeRev:
    """Return the HEAD sha and dirty flag of the git repo at repo_dir."""
    repo_dir = Path(repo_dir)
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ManifestError(f"git rev lookup failed in {repo_dir}: {exc}") from exc
    sha = head.stdout.strip()
    if not sha:
        raise ManifestError(f"git rev-parse HEAD returned no output in {repo_dir}")
    return CodeRev(sha=sha, dirty=bool(status.stdout.strip()))


def library_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in _LIBRARIES:
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = "unknown"
    return versions


def _identity_payload(
    *,
    dataset_ref: DatasetRef,
    config_resolved: Mapping[str, Any],
    code_rev: CodeRev,
    base_model: Mapping[str, Any],
    versions: Mapping[str, str],
) -> dict[str, Any]:
    if "repo_id" not in base_model or "revision" not in base_model:
        raise ManifestError("base_model must contain repo_id and revision")
    return {
        "base_model": {"repo_id": base_model["repo_id"], "revision": base_model["revision"]},
        "code_git_rev": code_rev.canonical_dict(),
        "config_sha256": sha256_hex(config_resolved),
        "dataset": dataset_ref.canonical_dict(),
        "versions": dict(versions),
    }


def build_run_manifest(
    *,
    dataset_ref: DatasetRef,
    config_resolved: Mapping[str, Any],
    code_rev: CodeRev,
    base_model: Mapping[str, Any],
    versions: Mapping[str, str] | None = None,
    hypothesis: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a full run manifest dict, with run_id derived from identity fields.

    `hypothesis` (when a non-empty string) is stamped in as a top-level,
    NON-identity field -- it is added after run_id is already derived, so
    pre-registering (or later editing, see update_manifest_evaluation's
    caller in evaluate.py) a hypothesis never changes run_id.
    """
    resolved_versions = dict(versions) if versions is not None else library_versions()
    identity = _identity_payload(
        dataset_ref=dataset_ref,
        config_resolved=config_resolved,
        code_rev=code_rev,
        base_model=base_model,
        versions=resolved_versions,
    )
    run_id = sha256_hex(identity)[:16]
    created_utc = (now or datetime.now(UTC)).isoformat()
    manifest = dict(identity)
    manifest["run_id"] = run_id
    manifest["created_utc"] = created_utc
    manifest["outputs"] = {"checkpoints": []}
    if hypothesis:
        manifest["hypothesis"] = hypothesis
    return manifest


def build_baseline_manifest(
    *,
    run_id: str,
    base_model: Mapping[str, Any],
    eval_set_sha256: str,
    corpus_sha256: str,
    scoring_version: str,
    code_rev: CodeRev,
    versions: Mapping[str, str] | None = None,
    hypothesis: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a manifest for a baseline evaluation of the un-fine-tuned base model.

    Unlike build_run_manifest, run_id is NOT derived here -- it is passed in
    already computed (see evaluate.baseline_run_id), from the eval-set
    digest + scoring_version + base model revision (design doc section 4.2),
    not from a training identity payload. Fields that do not apply to a
    baseline (no training config, no dataset ref, no checkpoints yet) are
    explicitly recorded as null, with `notes` explaining why.
    """
    resolved_versions = dict(versions) if versions is not None else library_versions()
    built: dict[str, Any] = {
        "run_id": run_id,
        "kind": "baseline",
        "created_utc": (now or datetime.now(UTC)).isoformat(),
        "base_model": {"repo_id": base_model["repo_id"], "revision": base_model.get("revision")},
        "code_git_rev": code_rev.canonical_dict(),
        "versions": resolved_versions,
        "config_sha256": None,
        "dataset": None,
        "outputs": {"checkpoints": []},
        "eval_set_sha256": eval_set_sha256,
        "corpus_sha256": corpus_sha256,
        "scoring_version": scoring_version,
        "notes": (
            "Baseline evaluation of the un-fine-tuned pinned base model: no "
            "training config, no dataset ref, no checkpoints. run_id is derived "
            "from eval-set digest + scoring_version + base model revision "
            "(design 4.2), not from the training identity payload."
        ),
    }
    if hypothesis:
        built["hypothesis"] = hypothesis
    return built


def write_manifest(manifest: Mapping[str, Any], run_dir: str | Path) -> Path:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def read_manifest(run_dir: str | Path) -> dict[str, Any]:
    path = Path(run_dir) / "manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ManifestError(f"{path} must contain a JSON object")
    return payload


def update_manifest_outputs(
    run_dir: str | Path, checkpoints: list[Mapping[str, Any]]
) -> dict[str, Any]:
    """Fill in outputs.checkpoints post-run and rewrite manifest.json.

    run_id is unaffected: it is derived only from the identity fields fixed
    at manifest-creation time, not from outputs.
    """
    manifest = read_manifest(run_dir)
    manifest["outputs"] = {"checkpoints": [dict(item) for item in checkpoints]}
    manifest["updated_utc"] = datetime.now(UTC).isoformat()
    write_manifest(manifest, run_dir)
    return manifest


def update_manifest_evaluation(
    run_dir: str | Path, evaluation: Mapping[str, Any]
) -> dict[str, Any]:
    """Merge an `evaluation` section into manifest.json and stamp updated_utc.

    run_id is unaffected: it derives only from the identity fields fixed at
    manifest-creation time (same invariant as update_manifest_outputs).
    """
    manifest = read_manifest(run_dir)
    manifest["evaluation"] = dict(evaluation)
    manifest["updated_utc"] = datetime.now(UTC).isoformat()
    write_manifest(manifest, run_dir)
    return manifest


__all__ = [
    "CodeRev",
    "DatasetRef",
    "ManifestError",
    "build_baseline_manifest",
    "build_run_manifest",
    "canonical_json_bytes",
    "git_rev",
    "library_versions",
    "load_dataset_ref",
    "read_manifest",
    "sha256_dir",
    "sha256_file",
    "sha256_hex",
    "update_manifest_evaluation",
    "update_manifest_outputs",
    "write_manifest",
]
