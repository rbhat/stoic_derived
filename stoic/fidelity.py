"""Phase 6 -- fidelity measurement. Pairs Phase 3's labels to the Phase 5 engine's output.

Design: `docs/PHASE6.md`. The question is `CLAUDE.md`'s and only `CLAUDE.md`'s -- does our
implementation generate the trades the method calls for. Never whether the method has an edge.

**This module is measurement, not signal.** `VISION.md` puts the deterministic signal path in
`stoic/`; a measurement module living beside it must never be reachable from it. Task 6 of
`docs/PHASE6-PLAN.md` will add a test to `tests/test_fidelity.py` that asserts the direction of
dependence by parsing every other `stoic/*.py`.

**It holds no threshold, fraction or tuned number**, and it must stay that way
(`docs/CONSTRAINTS.md` -- `stoic/judgment.py` is the only module allowed one). Matching is exact
bar equality (`docs/PHASE6.md` §4, the user's call on 2026-08-11), which needs no number: a
tolerance invented inside the measurement layer is the failure
`claude_memories/audit-hard-rules-not-in-material.md` names, and `docs/PHASE3.md` forbids one by
name.

Conventions fixed here rather than in `docs/PHASE6.md`:

1. **An absent value is unscoreable, never a pass.** A `phase6_scope` entry of `None`, or a field
   the artifact never printed, produces a `Delta` with `scoreable=False` and a stated reason. It
   never produces a zero delta.
2. **A stated value that disagrees with the field it names is a bug in the block, never a
   correction to the label.** `check_scope_consistency` reports it and the driver refuses to run.
3. **`stop.by_r_label` is never a reference.** `docs/CONSTRAINTS.md`: the dollar recovery is a
   suggestion and a `by_r_label` distance may never contradict §5.4.1 / D-18. It is carried as an
   informational column and no delta is ever computed from it.
"""

from __future__ import annotations

import pandas as pd

# The keys of a `phase6_scope` block that name a comparable reference, and which attributes of
# each are checked against the field `from:` points at. This list is not the full set of keys a
# real block may carry -- see DECLARATION_KEYS below for the rest, and note that each sub-block
# named here (e.g. `scope["anchor_bar"]`) may also carry a `provenance` key of its own (`read`,
# `derived` or `exact`); that key is metadata about the transcription, not a comparable attribute,
# so it never appears in COMPARED_ATTRS and is never checked.
#
# `anchor_bar_narrated` is deliberately NOT a member of this tuple even though it names a
# reference (`from: bar_5m_et`): that field holds a wall-clock string like `'13:25'`, while the
# block holds a full UTC timestamp, so the two are not comparable by equality -- checking it here
# would report a false problem. It is validated only as a known key, in DECLARATION_KEYS.
SCOPE_KEYS: tuple[str, ...] = ("anchor_bar", "entry_bar", "trigger", "stop", "tp1")

COMPARED_ATTRS: dict[str, tuple[str, ...]] = {
    "anchor_bar": ("ts",),
    "entry_bar": ("ts",),
    "trigger": ("price",),
    "stop": ("price", "distance"),  # the label stores both together under one node
    "tp1": ("price",),
}

# The keys of a `phase6_scope` block that are declarations rather than references: nothing in
# COMPARED_ATTRS checks them, so a misspelling of one of these must still be caught as an unknown
# key rather than silently ignored.
DECLARATION_KEYS: frozenset[str] = frozenset(
    {
        "expect_fill",  # whether the engine is expected to fill this order at all
        "circular",  # whether this block was derived from the engine's own output (excluded)
        "never",  # field names that must never be used as a scoring reference
        "why",  # free-text rationale for the block's scoreable/unscoreable choices
        "anchor_bar_narrated",  # narrated-bar anchor for no_opportunity labels; see note above
    }
)


# Sentinel distinguishing "the path is absent" from "the path resolves to a value of None" --
# both look like `None` to a caller of `resolve_path`, but the gate below must tell them apart
# (a scope block correctly pointing at a legitimately-null label field is not dangling).
_MISSING = object()


def _resolve_path(node: object, path: str) -> object:
    """Dotted-path lookup into a parsed label. Returns `_MISSING` if any segment is absent or not
    a mapping, distinct from a resolved value that is genuinely `None`. Internal: callers that
    don't need the distinction should use `resolve_path`.
    """
    current = node
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return _MISSING
        current = current[key]
    return current


def resolve_path(node: object, path: str) -> object | None:
    """Dotted-path lookup into a parsed label. `None` if any segment is absent or not a mapping.

    Deliberately total: a dangling path is a reportable problem, not an exception, because the
    driver reports every problem in one pass rather than dying on the first.
    """
    result = _resolve_path(node, path)
    return None if result is _MISSING else result


def _same(stated: object, actual: object) -> bool:
    """Exact equality, with timestamps normalised. No tolerance -- a transcribed value is copied,
    so anything but equality is a transcription error."""
    if stated is None or actual is None:
        return stated is None and actual is None
    if hasattr(actual, "tzinfo") or isinstance(actual, pd.Timestamp):
        try:
            return pd.Timestamp(stated) == pd.Timestamp(actual)
        except (ValueError, TypeError):
            # An unparseable `stated` (e.g. a placeholder string like "TBD") is a reportable
            # mismatch, not a crash -- the driver must still see every other label's problems.
            return False
    return bool(stated == actual)


def check_scope_consistency(label: dict) -> tuple[str, ...]:
    """Every problem with one label's `phase6_scope` block, as human-readable lines.

    Empty means the block agrees with every field it points at. This is the gate that makes the
    block safe: it adds no reading, so it must reproduce the readings it names exactly.
    """
    label_id = label.get("id", "<no id>")
    scope = label.get("phase6_scope")
    if scope is None:
        return (f"{label_id}: no phase6_scope block",)

    problems: list[str] = []
    known_keys = set(SCOPE_KEYS) | DECLARATION_KEYS
    for key in scope:
        if key not in known_keys:
            problems.append(f"{label_id}: unknown phase6_scope key '{key}'")

    for key in SCOPE_KEYS:
        block = scope.get(key)
        if block is None:
            continue
        source = block.get("from")
        if source is None:
            problems.append(f"{label_id}.{key}: no from: path")
            continue
        node = _resolve_path(label, source)
        if node is _MISSING:
            problems.append(f"{label_id}.{key}: from: '{source}' resolves to nothing")
            continue
        for attr in COMPARED_ATTRS[key]:
            stated = block.get(attr)
            actual = node.get(attr) if isinstance(node, dict) else node
            if not _same(stated, actual):
                problems.append(
                    f"{label_id}.{key}.{attr}: block says {stated!r}, "
                    f"'{source}' says {actual!r}"
                )
    return tuple(problems)


__all__ = [
    "COMPARED_ATTRS",
    "DECLARATION_KEYS",
    "SCOPE_KEYS",
    "check_scope_consistency",
    "resolve_path",
]
