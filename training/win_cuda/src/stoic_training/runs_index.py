"""Append-only run history for the offline research-assistant SLM.

Purpose guardrail: this records provenance for training an OFFLINE research
assistant that proposes cited rule candidates for human review; its output
never touches any live trading path.

Pure stdlib (json, pathlib, os, typing, collections.abc) -- no torch, no
yaml, no import of `config.py` -- so this stays cheap to import from tests
and from evaluate.py at the end of a run.

`runs/index.jsonl` is the experiment history: one compact JSON line per
completed evaluation, written by `evaluate.py`'s run-dir path on
completion. It is strictly append-only -- `append_entry` opens the file in
"a" mode and writes exactly one line; it never reads or rewrites existing
lines, so a crash mid-run can never corrupt history that already landed.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

INDEX_NAME = "index.jsonl"


def index_path(runs_root: str | Path) -> Path:
    return Path(runs_root) / INDEX_NAME


def read_index(runs_root: str | Path) -> list[dict[str, Any]]:
    """Read every line of the index; `[]` if the index does not exist yet."""
    path = index_path(runs_root)
    if not path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def last_entry(runs_root: str | Path) -> dict[str, Any] | None:
    entries = read_index(runs_root)
    return entries[-1] if entries else None


def flatten_config(config: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten a nested config mapping to dotted keys.

    Nested mappings recurse; lists and other scalars are kept as-is and
    compared whole (a list is a single leaf value, not exploded by index).
    """
    flat: dict[str, Any] = {}
    for key, value in config.items():
        dotted = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            flat.update(flatten_config(value, dotted))
        else:
            flat[dotted] = value
    return flat


def diff_configs(
    previous: Mapping[str, Any] | None, current: Mapping[str, Any] | None
) -> dict[str, dict[str, Any]]:
    """Dotted-key diff of two resolved configs: `{}` if either side is None.

    Covers added keys (`from: None`), removed keys (`to: None`), and changed
    keys (`from`/`to` both set to their differing values).
    """
    if previous is None or current is None:
        return {}
    flat_previous = flatten_config(previous)
    flat_current = flatten_config(current)
    diff: dict[str, dict[str, Any]] = {}
    for key in sorted(set(flat_previous) | set(flat_current)):
        had_previous = key in flat_previous
        had_current = key in flat_current
        old_value = flat_previous.get(key)
        new_value = flat_current.get(key)
        if not had_previous:
            diff[key] = {"from": None, "to": new_value}
        elif not had_current:
            diff[key] = {"from": old_value, "to": None}
        elif old_value != new_value:
            diff[key] = {"from": old_value, "to": new_value}
    return diff


def previous_config_resolved(runs_root: str | Path) -> dict[str, Any] | None:
    """The previous run's `manifest.json["config_resolved"]`, or None.

    Assumes a run dir is named after its run_id (`<runs_root>/<run_id>/`),
    which is how train.py lays runs out (`config.paths.run_dir /
    manifest["run_id"]`). A run dir named anything else is simply not found,
    and the caller falls back to an empty knob diff rather than failing --
    a missing diff is a cosmetic loss in the history, never a wrong one.

    Tolerates -- by returning None rather than raising -- a missing index,
    a missing manifest for the last-indexed run_id, and a malformed
    (non-JSON or non-object) manifest.json.
    """
    try:
        entry = last_entry(runs_root)
    except (OSError, json.JSONDecodeError):
        return None
    if entry is None:
        return None
    run_id = entry.get("run_id")
    if not run_id:
        return None
    manifest_path = Path(runs_root) / run_id / "manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    config_resolved = payload.get("config_resolved")
    return config_resolved if isinstance(config_resolved, dict) else None


def build_entry(
    *,
    run_id: str,
    date: str,
    config_sha256: str | None,
    knob_diff: Mapping[str, Any],
    hypothesis: str | None,
    metrics: Mapping[str, Any],
    scoring_version: str,
    eval_set_sha256: str,
    corpus_sha256: str,
) -> dict[str, Any]:
    """Build one index line in the exact key order/shape of the pinned schema."""
    return {
        "run_id": run_id,
        "date": date,
        "config_sha256": config_sha256,
        "knob_diff": dict(knob_diff),
        "hypothesis": hypothesis,
        "metrics": dict(metrics),
        "scoring_version": scoring_version,
        "eval_set_sha256": eval_set_sha256,
        "corpus_sha256": corpus_sha256,
    }


def append_entry(runs_root: str | Path, entry: Mapping[str, Any]) -> Path:
    """Append one compact JSON line to the index. Never rewrites existing lines."""
    path = index_path(runs_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(dict(entry), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.write("\n")
    return path


__all__ = [
    "INDEX_NAME",
    "append_entry",
    "build_entry",
    "diff_configs",
    "flatten_config",
    "index_path",
    "last_entry",
    "previous_config_resolved",
    "read_index",
]
