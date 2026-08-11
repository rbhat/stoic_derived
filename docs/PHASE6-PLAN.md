# Phase 6 — Fidelity Measurement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the replay harness that reconciles the Phase 5 engine's output against Phase 3's ten labels and produces `docs/evidence/phase6_reconciliation.md`.

**Architecture:** `stoic/fidelity.py` holds the pure measurement logic — path resolution, scope-consistency checking, per-class pairing, delta computation, report rendering — with hermetic unit tests. `scripts/reconcile_labels.py` is the only piece that touches disk: it loads bars and labels, runs `replay_entries` and `replay_signals` over one continuous frame, and writes the report. Nothing in L0–L5 ever imports `fidelity`, and a structural test enforces that.

**Tech Stack:** Python 3.14 via `.venv/bin/python`, pandas 3, PyYAML 6, pytest 9. All already in `pyproject.toml` — **no new dependencies**.

**The spec is `docs/PHASE6.md`.** Read it before Task 1. This plan implements it and does not restate its reasoning.

## Global Constraints

- **No threshold, fraction, tolerance or tuned number anywhere in `stoic/fidelity.py`.** `stoic/judgment.py` is the only module in the repo allowed to hold one (`docs/CONSTRAINTS.md`). Matching is exact-bar equality, which needs no number.
- **`stoic/fidelity.py` imports from L0–L5; nothing in L0–L5 imports it.** Task 6 enforces this with a test.
- **Lint with `uvx ruff check --fix`, never a bare `ruff check`.** Line length 100.
- **`.venv/bin/python` for everything.** Pillow is not installed; do not import PIL.
- **A script importing `stoic` needs `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))`** before the import — `python scripts/foo.py` puts only `scripts/` on the path and `[tool.uv] package = false` means there is nothing installed to fall back on. pytest works via the `pythonpath` config; the script does not.
- **Atomic writes:** write `<target>.tmp`, then `os.replace(tmp, target)`. Never leave a partial file at the real path.
- **Every gate needs a negative control** (`coding_rules.md`): inject the fault it exists to catch and confirm it fails.
- **Ruff `RUF005`:** build a fixture list as `[*PREFIX, ...]`, never `PREFIX + [...]`. **Ruff `RUF059`:** a trailing-underscore name is not a dummy; use `_` or a leading underscore.
- **Task 2 must be committed before Task 7 ever runs the engine.** The spec requires the scope blocks to predate the output, and the commit order is the proof.
- **Never edit an existing label field.** `phase6_scope` is additive only.
- **The engine is not modified by any task in this plan.** A divergence is reported, never fixed here.

## File Structure

| File | Responsibility |
|---|---|
| `stoic/fidelity.py` | **Create.** Pure. Path resolution, scope checking, pairing, deltas, report rendering. No disk, no network, no clock, no threshold |
| `tests/test_fidelity.py` | **Create.** Hermetic hand-built fixtures, one group per class, negative controls, the import-direction test |
| `scripts/reconcile_labels.py` | **Create.** The driver: bars, replays, label load, Gate 0, report write, per-stage timings |
| `docs/evidence/labels/*.yaml` | **Modify.** Add one `phase6_scope` block per label. Ten labels across four files. Additive only |
| `docs/evidence/phase6_reconciliation.md` | **Create (generated §1/§3, hand-written §2).** The deliverable |
| `docs/STATE.md`, `docs/CONSTRAINTS.md` | **Modify.** Task 8 only |

---

### Task 1: `stoic/fidelity.py` — path resolution and scope consistency

**Files:**
- Create: `stoic/fidelity.py`
- Create: `tests/test_fidelity.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `resolve_path(node: object, path: str) -> object | None`, `check_scope_consistency(label: dict) -> tuple[str, ...]`, and the module constants `SCOPE_KEYS: tuple[str, ...]` and `COMPARED_ATTRS: dict[str, tuple[str, ...]]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fidelity.py`:

```python
"""Unit tests for stoic.fidelity (Phase 6) -- hand-built fixtures only, no disk or network.

The pairing rule is the measurement instrument, so it is the part that must be tested. Every
check here gets a negative control per `coding_rules.md`: inject the fault it exists to catch and
confirm it is caught.
"""

from __future__ import annotations

import datetime as dt

from stoic.fidelity import check_scope_consistency, resolve_path


def _utc(y: int, m: int, d: int, hh: int, mm: int) -> dt.datetime:
    return dt.datetime(y, m, d, hh, mm, tzinfo=dt.UTC)


def _label() -> dict:
    """A `taken` label in the shape PyYAML produces from docs/evidence/labels/."""
    return {
        "id": "T-A2",
        "class": "taken",
        "direction": "short",
        "ptb": {
            "pos_ts": _utc(2026, 7, 31, 14, 50),
            "trigger": {"bars": 28289.75, "provenance": "read"},
        },
        "entry": {"price": 28286.67, "pos_ts": _utc(2026, 7, 31, 14, 55)},
        "stop": {
            "by_ptb_extreme": {"price": 28345.50, "distance": 58.83},
            "by_r_label": {"price": 28341.09, "distance": 54.42},
        },
        "tp1": None,
        "phase6_scope": {
            "anchor_bar": {"ts": _utc(2026, 7, 31, 14, 50), "from": "ptb.pos_ts"},
            "entry_bar": {"ts": _utc(2026, 7, 31, 14, 55), "from": "entry.pos_ts"},
            "trigger": {"price": 28289.75, "from": "ptb.trigger.bars"},
            "stop": {"price": 28345.50, "distance": 58.83, "from": "stop.by_ptb_extreme"},
            "tp1": None,
            "expect_fill": True,
            "circular": False,
            "never": ["exit", "outcome"],
        },
    }


def test_resolve_path_reaches_a_nested_scalar():
    assert resolve_path(_label(), "ptb.trigger.bars") == 28289.75


def test_resolve_path_returns_none_for_an_absent_segment():
    assert resolve_path(_label(), "ptb.by_rule.trigger") is None


def test_resolve_path_returns_none_when_a_segment_is_not_a_mapping():
    assert resolve_path(_label(), "entry.price.nope") is None


def test_consistent_scope_reports_no_problems():
    assert check_scope_consistency(_label()) == ()


def test_negative_control_wrong_price_is_caught():
    label = _label()
    label["phase6_scope"]["trigger"]["price"] = 28290.00
    problems = check_scope_consistency(label)
    assert len(problems) == 1
    assert "trigger.price" in problems[0]


def test_negative_control_wrong_timestamp_is_caught():
    label = _label()
    label["phase6_scope"]["entry_bar"]["ts"] = _utc(2026, 7, 31, 15, 0)
    problems = check_scope_consistency(label)
    assert len(problems) == 1
    assert "entry_bar.ts" in problems[0]


def test_negative_control_distance_is_compared_too():
    label = _label()
    label["phase6_scope"]["stop"]["distance"] = 54.42  # the by_r_label distance
    problems = check_scope_consistency(label)
    assert len(problems) == 1
    assert "stop.distance" in problems[0]


def test_dangling_from_path_is_caught():
    label = _label()
    label["phase6_scope"]["trigger"]["from"] = "ptb.by_rule.trigger"
    problems = check_scope_consistency(label)
    assert len(problems) == 1
    assert "resolves to nothing" in problems[0]


def test_missing_scope_block_is_caught():
    label = _label()
    del label["phase6_scope"]
    problems = check_scope_consistency(label)
    assert len(problems) == 1
    assert "no phase6_scope" in problems[0]


def test_null_scope_entries_are_not_checked():
    label = _label()
    label["phase6_scope"]["trigger"] = None
    assert check_scope_consistency(label) == ()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_fidelity.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stoic.fidelity'`

- [ ] **Step 3: Write the implementation**

Create `stoic/fidelity.py`:

```python
"""Phase 6 -- fidelity measurement. Pairs Phase 3's labels to the Phase 5 engine's output.

Design: `docs/PHASE6.md`. The question is `CLAUDE.md`'s and only `CLAUDE.md`'s -- does our
implementation generate the trades the method calls for. Never whether the method has an edge.

**This module is measurement, not signal.** `VISION.md` puts the deterministic signal path in
`stoic/`; a measurement module living beside it must never be reachable from it, and
`tests/test_fidelity.py` asserts the direction of dependence by parsing every other `stoic/*.py`.

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
# each are checked against the field `from:` points at. `expect_fill`, `circular`, `never` and
# `why` are declarations, not references, so they are not in this table.
SCOPE_KEYS: tuple[str, ...] = ("anchor_bar", "entry_bar", "trigger", "stop", "tp1")

COMPARED_ATTRS: dict[str, tuple[str, ...]] = {
    "anchor_bar": ("ts",),
    "entry_bar": ("ts",),
    "trigger": ("price",),
    "stop": ("price", "distance"),  # the label stores both together under one node
    "tp1": ("price",),
}


def resolve_path(node: object, path: str) -> object | None:
    """Dotted-path lookup into a parsed label. `None` if any segment is absent or not a mapping.

    Deliberately total: a dangling path is a reportable problem, not an exception, because the
    driver reports every problem in one pass rather than dying on the first.
    """
    current = node
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _same(stated: object, actual: object) -> bool:
    """Exact equality, with timestamps normalised. No tolerance -- a transcribed value is copied,
    so anything but equality is a transcription error."""
    if stated is None or actual is None:
        return stated is None and actual is None
    if hasattr(actual, "tzinfo") or isinstance(actual, pd.Timestamp):
        return pd.Timestamp(stated) == pd.Timestamp(actual)
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
    for key in SCOPE_KEYS:
        block = scope.get(key)
        if block is None:
            continue
        source = block.get("from")
        if source is None:
            problems.append(f"{label_id}.{key}: no from: path")
            continue
        node = resolve_path(label, source)
        if node is None:
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
    "SCOPE_KEYS",
    "check_scope_consistency",
    "resolve_path",
]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_fidelity.py -v`
Expected: PASS, 10 passed

- [ ] **Step 5: Lint**

Run: `uvx ruff check --fix stoic/fidelity.py tests/test_fidelity.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add stoic/fidelity.py tests/test_fidelity.py
git commit -m "Add Phase 6 scope-consistency checking, with negative controls"
```

---

### Task 2: The ten `phase6_scope` blocks — committed before any engine run

**Files:**
- Modify: `docs/evidence/labels/2026-07-27_LT.yaml` (labels `LT-A1`, `LT-B1`)
- Modify: `docs/evidence/labels/2026-07-30_LT3_LT4.yaml` (labels `LT34-A1`, `LT34-M1`, `LT34-M2`, `PTBV30-N1`)
- Modify: `docs/evidence/labels/2026-07-31_T1_T2.yaml` (labels `T-A1`, `T-A2`, `T-B1`)
- Modify: `docs/evidence/labels/2026-08-03_NQ3.yaml` (label `NQ3-A1`)

**Interfaces:**
- Consumes: `check_scope_consistency` from Task 1.
- Produces: a `phase6_scope` block on all ten labels, verified against the fields it names.

**This task adds no reading.** Every value below was read out of the label file it goes back into. Add the block as the **last key of its label**, indented to the label's other keys. Change nothing else.

- [ ] **Step 1: Add the two blocks in `2026-07-27_LT.yaml`**

Under `LT-A1`:

```yaml
    phase6_scope:
      anchor_bar:  {ts: 2026-07-27T13:35:00Z, from: ptb.pos_ts, provenance: read}
      entry_bar:   {ts: 2026-07-27T13:40:00Z, from: entry.pos_ts, provenance: exact}
      trigger:     {price: 28525.75, from: ptb.trigger.bars, provenance: read}
      stop:        {price: 28613.75, distance: 97.75, from: stop.by_ptb_extreme, provenance: derived}
      tp1:         null
      expect_fill: true
      circular:    false
      never:       [exit, outcome]
      why: >
        tp1 is unscoreable: the Step 3 Low is not drawn on this chart and tp1.bars is null.
        stop.by_r_label disagrees by 12.25 points and is never a reference (docs/CONSTRAINTS.md).
        The exit bar is itself unresolved — 28,345.00 lies inside three candidate bars.
```

Under `LT-B1`:

```yaml
    phase6_scope:
      anchor_bar:  {ts: 2026-07-27T13:50:00Z, from: ptb.pos_ts, provenance: read}
      entry_bar:   null
      trigger:     {price: 28446.50, from: ptb.trigger.bars, provenance: read}
      stop:        null
      tp1:         null
      expect_fill: null
      circular:    false
      never:       [exit, outcome]
      why: >
        class `named` — the trader declined it. Scored as "did the engine anchor here". An engine
        fill is correct-but-not-taken, never a false positive (docs/PHASE3.md §2); the label's own
        would_trigger_on says the bars would have filled it.
```

- [ ] **Step 2: Add the four blocks in `2026-07-30_LT3_LT4.yaml`**

Under `LT34-A1`:

```yaml
    phase6_scope:
      anchor_bar:  {ts: 2026-07-30T19:50:00Z, from: ptb.by_rule.pos_ts, provenance: derived}
      entry_bar:   {ts: 2026-07-30T19:55:00Z, from: entry.pos_ts, provenance: exact}
      trigger:     {price: 28241.75, from: ptb.by_rule.trigger, provenance: derived}
      stop:        {price: 28207.00, distance: 37.42, from: stop.by_ptb_extreme, provenance: derived}
      tp1:         {price: 28297.75, from: tp1, provenance: derived}
      expect_fill: true
      circular:    false
      never:       [exit, outcome]
      why: >
        Held past the 13:58 PT flatten on a 5m chart and type.reproducible_as is null — §9's table
        has no Type that is both, so v1 cannot reproduce this exit and that is an accepted scope
        limit (docs/STATE.md), not a divergence. The trigger reference is ptb.by_rule, not
        ptb.drawn_level: the label records the two disagree by 3.80 points and adopts neither, and
        by_rule is the §5.2.3 reading the engine computes.
```

Under `LT34-M1`:

```yaml
    phase6_scope:
      anchor_bar:  null
      entry_bar:   {ts: 2026-07-30T13:35:00Z, from: entry.pos_ts, provenance: exact}
      trigger:     null
      stop:        null
      tp1:         null
      expect_fill: true
      circular:    false
      never:       [exit, outcome]
      why: >
        ptb is null — no PTB level is drawn for this entry, so trigger and the §5.4.1 stop are
        both unavailable. Only by_r_label and by_lot_count exist and neither is ever a reference
        (docs/CONSTRAINTS.md). Scoreable: direction and entry bar.
```

Under `LT34-M2`:

```yaml
    phase6_scope:
      anchor_bar:  null
      entry_bar:   {ts: 2026-07-30T14:15:00Z, from: entry.pos_ts, provenance: exact}
      trigger:     null
      stop:        null
      tp1:         null
      expect_fill: true
      circular:    false
      never:       [exit, outcome]
      why: >
        ptb is null and no R label is printed, so §10.10's division has no input either.
        Scoreable: direction and entry bar.
```

Under `PTBV30-N1`:

```yaml
    phase6_scope:
      anchor_bar:  null
      entry_bar:   null
      trigger:     null
      stop:        null
      tp1:         null
      expect_fill: false
      circular:    false
      never:       [exit, outcome]
      why: >
        class `no_opportunity`. The label's own phase_6_expectation governs: identify the setup,
        emit NO fill. anchor_bar is null because the narration gives a 5m bar (13:25 ET) and no
        drawn PTB level, so there is no `from:` path in this file to transcribe — the driver
        locates the order by its narrated bar, recorded below, and scores the order's own
        lifetime rather than a bar equality.
      anchor_bar_narrated: {ts: 2026-07-30T17:25:00Z, et: "13:25", from: bar_5m_et, provenance: exact}
```

- [ ] **Step 3: Add the three blocks in `2026-07-31_T1_T2.yaml`**

Under `T-A1`:

```yaml
    phase6_scope:
      anchor_bar:  null
      entry_bar:   {ts: 2026-07-31T14:40:00Z, from: entry.pos_ts, provenance: exact}
      trigger:     null
      stop:        null
      tp1:         null
      expect_fill: true
      circular:    false
      never:       [exit, outcome]
      why: >
        ptb is null — the drawn `ptb` line starts at the 10:50 bar and belongs to T-A2, so there
        is nothing on this artifact to score this trigger against. The stop has only by_r_label,
        which is never a reference. Scoreable: direction and entry bar.
```

Under `T-A2`:

```yaml
    phase6_scope:
      anchor_bar:  {ts: 2026-07-31T14:50:00Z, from: ptb.pos_ts, provenance: read}
      entry_bar:   {ts: 2026-07-31T14:55:00Z, from: entry.pos_ts, provenance: exact}
      trigger:     {price: 28289.75, from: ptb.trigger.bars, provenance: read}
      stop:        {price: 28345.50, distance: 58.83, from: stop.by_ptb_extreme, provenance: derived}
      tp1:         null
      expect_fill: true
      circular:    false
      never:       [exit, outcome]
      why: >
        The +1R exit is a discretionary stop move, not §5.4.5 / D-25 — ptbv_narration.
        management_observed.disposition says score the entry, the trigger and R, never the exit.
        tp1 is unscoreable: the count numerals on T1/T2 do not resolve to bars (count_numerals).
```

Under `T-B1`:

```yaml
    phase6_scope:
      anchor_bar:  {ts: 2026-07-31T16:45:00Z, from: ptb.pos_ts, provenance: read}
      entry_bar:   {ts: 2026-07-31T16:50:00Z, from: entry.pos_ts, provenance: exact}
      trigger:     {price: 28349.75, from: ptb.trigger.bars, provenance: read}
      stop:        {price: 28308.50, distance: 42.42, from: stop.by_ptb_extreme, provenance: derived}
      tp1:         null
      expect_fill: true
      circular:    false
      never:       [exit, outcome]
      why: >
        tp1 is unscoreable — the count numerals on T1/T2 do not resolve to bars (count_numerals).
        This is the corpus's one close agreement between §10.10 and §5.4.1, at 0.99 points, and
        by_r_label is still not the reference.
```

- [ ] **Step 4: Add the block in `2026-08-03_NQ3.yaml`**

Under `NQ3-A1`:

```yaml
    phase6_scope:
      anchor_bar:  {ts: 2026-08-03T14:05:00Z, from: ptb.pos_ts, provenance: read}
      entry_bar:   {ts: 2026-08-03T14:10:00Z, from: entry.pos_ts, provenance: derived}
      trigger:     {price: 28597.50, from: ptb.trigger.bars, provenance: read}
      stop:        {price: 28529.50, distance: 68.00, from: stop.by_ptb_extreme, provenance: derived}
      tp1:         {price: 28628.00, from: tp1.price, provenance: derived}
      expect_fill: true
      circular:    true
      never:       [exit, outcome]
      why: >
        CIRCULAR: entry.pos_ts is provenance derived — the labeller computed it as "first bar
        trading above the 28,597.50 trigger", which is §5.2.4, the rule the engine applies. A
        match on this bar tests the labeller's arithmetic, not the engine, and the report says so
        (docs/PHASE6.md §4). The only E-mini fixture, so prices should agree exactly; there is no
        exit on the artifact, the position is still open at the screenshot.
```

- [ ] **Step 5: Verify every block against the fields it names**

Run:

```bash
.venv/bin/python - <<'PY'
import glob, sys, yaml
sys.path.insert(0, ".")
from stoic.fidelity import check_scope_consistency
problems, n = [], 0
for path in sorted(glob.glob("docs/evidence/labels/*.yaml")):
    for label in yaml.safe_load(open(path))["labels"]:
        n += 1
        problems.extend(check_scope_consistency(label))
print(f"labels checked: {n}")
print("problems:", len(problems))
for p in problems:
    print("  -", p)
PY
```

Expected, verbatim:

```
labels checked: 10
problems: 0
```

If any problem prints, **fix the block, never the label field it disagrees with** — convention 2 in the module docstring.

- [ ] **Step 6: Confirm the edits are additive**

Run: `git diff --stat docs/evidence/labels/`
Expected: four files changed, insertions only, **0 deletions**. A deletion means an existing field was touched, which this task forbids.

- [ ] **Step 7: Commit — alone, before any engine run**

```bash
git add docs/evidence/labels/
git commit -m "Add phase6_scope to all ten labels, before any Phase 6 engine run

Additive only: every value is transcribed from a field already in the file
and from: names that field's path. check_scope_consistency reports 0
problems across 10 labels. This commit precedes the first engine run so
the diff proves the scope was not fitted to the output."
```

---

### Task 3: Pairing and deltas for class `taken`

**Files:**
- Modify: `stoic/fidelity.py`
- Modify: `tests/test_fidelity.py`

**Interfaces:**
- Consumes: `resolve_path` from Task 1.
- Produces: `Delta`, `LabelResult`, `reconcile_taken(label, session, emissions, entries, bar_index) -> LabelResult`, and `bar_offset(bar_index, a, b) -> int | None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fidelity.py`:

```python
import pandas as pd

from stoic.fidelity import Delta, LabelResult, bar_offset, reconcile_taken

BAR_INDEX = pd.date_range("2026-07-31 14:00", periods=24, freq="5min", tz="UTC")


def _emissions(rows: list[dict]) -> pd.DataFrame:
    columns = [
        "ts", "event", "direction", "blocked_by", "anchor_ts",
        "trigger", "fill", "stop", "r", "tp1",
    ]
    return pd.DataFrame([{c: row.get(c) for c in columns} for row in rows], columns=columns)


def _entries(rows: list[dict]) -> pd.DataFrame:
    columns = ["ts", "event", "direction", "anchor_ts", "trigger", "stop", "fill", "step3_extreme"]
    return pd.DataFrame([{c: row.get(c) for c in columns} for row in rows], columns=columns)


def _signal_row(**over) -> dict:
    row = {
        "ts": pd.Timestamp("2026-07-31 14:55", tz="UTC"),
        "event": "SIGNAL",
        "direction": "bearish",
        "blocked_by": (),
        "anchor_ts": pd.Timestamp("2026-07-31 14:50", tz="UTC"),
        "trigger": 28289.75,
        "fill": 28286.67,
        "stop": 28345.50,
        "r": 58.83,
        "tp1": None,
    }
    row.update(over)
    return row


def test_bar_offset_is_signed_and_in_bars():
    a = pd.Timestamp("2026-07-31 14:55", tz="UTC")
    b = pd.Timestamp("2026-07-31 14:40", tz="UTC")
    assert bar_offset(BAR_INDEX, a, b) == 3
    assert bar_offset(BAR_INDEX, b, a) == -3


def test_bar_offset_is_none_off_the_frame():
    off = pd.Timestamp("2026-07-31 09:00", tz="UTC")
    assert bar_offset(BAR_INDEX, off, BAR_INDEX[0]) is None


def test_exact_bar_match_produces_zero_deltas():
    result = reconcile_taken(
        _label(), "2026-07-31", _emissions([_signal_row()]), _entries([]), BAR_INDEX
    )
    assert isinstance(result, LabelResult)
    assert result.matched is True
    assert result.engine_event == "SIGNAL"
    assert result.anchor_matched is True
    by_field = {d.field: d for d in result.deltas}
    assert by_field["trigger"].delta == 0.0
    assert by_field["stop"].delta == 0.0
    assert by_field["stop_distance"].delta == 0.0


def test_one_bar_off_is_unmatched_and_characterised():
    late = _signal_row(ts=pd.Timestamp("2026-07-31 15:00", tz="UTC"))
    result = reconcile_taken(_label(), "2026-07-31", _emissions([late]), _entries([]), BAR_INDEX)
    assert result.matched is False
    assert result.nearest_delta_bars == 1
    assert result.nearest_ts == pd.Timestamp("2026-07-31 15:00", tz="UTC")
    assert all(d.scoreable is False for d in result.deltas)


def test_opposite_direction_emission_never_matches():
    wrong = _signal_row(direction="bullish")
    result = reconcile_taken(_label(), "2026-07-31", _emissions([wrong]), _entries([]), BAR_INDEX)
    assert result.matched is False
    assert result.nearest_ts is None


def test_no_emissions_at_all_leaves_nearest_none():
    result = reconcile_taken(_label(), "2026-07-31", _emissions([]), _entries([]), BAR_INDEX)
    assert result.matched is False
    assert result.nearest_ts is None
    assert result.nearest_delta_bars is None


def test_suppressed_matches_and_borrows_prices_from_l3():
    suppressed = _signal_row(
        event="SUPPRESSED", blocked_by=("trend_50",),
        anchor_ts=None, trigger=None, fill=None, stop=None, r=None, tp1=None,
    )
    l3 = _entries([{
        "ts": pd.Timestamp("2026-07-31 14:55", tz="UTC"),
        "event": "ENTRY_FILLED",
        "direction": "bearish",
        "anchor_ts": pd.Timestamp("2026-07-31 14:50", tz="UTC"),
        "trigger": 28289.75, "stop": 28345.50, "fill": 28286.67, "step3_extreme": None,
    }])
    result = reconcile_taken(_label(), "2026-07-31", _emissions([suppressed]), l3, BAR_INDEX)
    assert result.matched is True
    assert result.engine_event == "SUPPRESSED"
    assert result.blocked_by == ("trend_50",)
    by_field = {d.field: d for d in result.deltas}
    assert by_field["trigger"].delta == 0.0
    assert by_field["stop_distance"].delta == 0.0
    assert result.anchor_matched is True


def test_unscoreable_field_states_a_reason_and_never_a_zero():
    label = _label()
    label["phase6_scope"]["trigger"] = None
    result = reconcile_taken(
        label, "2026-07-31", _emissions([_signal_row()]), _entries([]), BAR_INDEX
    )
    trigger = next(d for d in result.deltas if d.field == "trigger")
    assert trigger.scoreable is False
    assert trigger.delta is None
    assert trigger.reason != ""


def test_circular_flag_is_carried_onto_the_result():
    label = _label()
    label["phase6_scope"]["circular"] = True
    result = reconcile_taken(
        label, "2026-07-31", _emissions([_signal_row()]), _entries([]), BAR_INDEX
    )
    assert result.circular is True


def test_delta_sign_is_engine_minus_label():
    high = _signal_row(trigger=28292.75)
    result = reconcile_taken(_label(), "2026-07-31", _emissions([high]), _entries([]), BAR_INDEX)
    trigger = next(d for d in result.deltas if d.field == "trigger")
    assert trigger.delta == 3.0
    assert isinstance(trigger, Delta)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_fidelity.py -v`
Expected: FAIL — `ImportError: cannot import name 'Delta' from 'stoic.fidelity'`

- [ ] **Step 3: Write the implementation**

Add to `stoic/fidelity.py`, after `check_scope_consistency` and before `__all__`:

```python
from dataclasses import dataclass

# The four comparable quantities on a matched `taken` label, and where each side comes from.
# `stop_distance` compares the engine's `r` -- |fill - stop|, §5.4.2 -- against the label's own
# stop distance in points. The label's `r_label` is an OUTCOME MULTIPLE and is never compared to
# it: they are different quantities (docs/PHASE6.md §1).
_TAKEN_FIELDS: tuple[tuple[str, str, str, str], ...] = (
    # (delta field, scope key, scope attr, engine column)
    ("trigger", "trigger", "price", "trigger"),
    ("stop", "stop", "price", "stop"),
    ("stop_distance", "stop", "distance", "r"),
    ("tp1", "tp1", "price", "tp1"),
)

_TERMINAL_EVENTS: frozenset[str] = frozenset(
    {"ENTRY_FILLED", "ORDER_CANCELLED", "ORDER_VOIDED"}
)


@dataclass(frozen=True)
class Delta:
    """One comparable quantity. `delta` is engine minus label, in points."""

    field: str
    label: float | None
    engine: float | None
    delta: float | None
    scoreable: bool
    reason: str = ""


@dataclass(frozen=True)
class LabelResult:
    """One label's reconciliation. Carries no verdict -- only what was and was not found."""

    label_id: str
    session: str
    label_class: str
    direction: str
    matched: bool
    engine_event: str | None
    engine_ts: pd.Timestamp | None
    blocked_by: tuple[str, ...]
    anchor_matched: bool | None
    deltas: tuple[Delta, ...]
    nearest_ts: pd.Timestamp | None
    nearest_delta_bars: int | None
    circular: bool
    notes: tuple[str, ...]


def bar_offset(
    bar_index: pd.DatetimeIndex, a: pd.Timestamp | None, b: pd.Timestamp | None
) -> int | None:
    """Signed distance from `b` to `a` in bars of the replay frame. `None` if either is off it.

    Bars, not minutes: the frame holds no bars across the CME maintenance break, so a wall-clock
    difference is not a bar count (`docs/CONSTRAINTS.md` -- the row about blaming that break).
    """
    if a is None or b is None:
        return None
    try:
        return int(bar_index.get_loc(pd.Timestamp(a))) - int(bar_index.get_loc(pd.Timestamp(b)))
    except KeyError:
        return None


def _unscoreable(field: str, reason: str, label_value: float | None = None) -> Delta:
    return Delta(
        field=field, label=label_value, engine=None, delta=None, scoreable=False, reason=reason
    )


def _finite(value: object) -> float | None:
    """A float, or None for None / NaN / pandas NA. Guards against pandas' nullable columns."""
    if value is None or (isinstance(value, float) and value != value):
        return None
    if value is pd.NA:
        return None
    return float(value)  # type: ignore[arg-type]


def _l3_prices(entries: pd.DataFrame, ts: pd.Timestamp, direction: str) -> dict[str, object]:
    """L3's `ENTRY_FILLED` record at this bar, or an empty dict.

    A `SUPPRESSED` emission carries no `SignalRecord`, so every price on it is null
    (`stoic/emission.py`). The prices exist one layer down and this recovers them, which is why
    the driver runs both replays (`docs/PHASE6.md` §3).
    """
    hit = entries[
        (entries["ts"] == ts)
        & (entries["direction"].astype(str) == direction)
        & (entries["event"].astype(str) == "ENTRY_FILLED")
    ]
    if hit.empty:
        return {}
    row = hit.iloc[0]
    return {
        "anchor_ts": row["anchor_ts"],
        "trigger": row["trigger"],
        "stop": row["stop"],
        "fill": row["fill"],
        "r": (
            abs(_finite(row["fill"]) - _finite(row["stop"]))
            if _finite(row["fill"]) is not None and _finite(row["stop"]) is not None
            else None
        ),
        "tp1": row["step3_extreme"],
    }


def reconcile_taken(
    label: dict,
    session: str,
    emissions: pd.DataFrame,
    entries: pd.DataFrame,
    bar_index: pd.DatetimeIndex,
) -> LabelResult:
    """Pair one `taken` label to an emission on the SAME BAR, exactly (`docs/PHASE6.md` §4).

    `emissions` and `entries` are already sliced to this label's session; both directions may be
    present and this filters. An unmatched label is characterised by its nearest same-direction
    emission and the signed bar offset to it -- a miss by one bar and a miss by forty are
    different facts and §2 of the report cannot be written without knowing which.
    """
    scope = label["phase6_scope"]
    direction = str(label["direction"])
    engine_direction = "bullish" if direction == "long" else "bearish"
    circular = bool(scope.get("circular", False))

    candidates = emissions[
        (emissions["direction"].astype(str) == engine_direction)
        & (emissions["event"].astype(str).isin(["SIGNAL", "SUPPRESSED"]))
    ]

    entry_bar = scope.get("entry_bar")
    if entry_bar is None:
        return LabelResult(
            label_id=label["id"], session=session, label_class=str(label["class"]),
            direction=direction, matched=False, engine_event=None, engine_ts=None,
            blocked_by=(), anchor_matched=None,
            deltas=tuple(
                _unscoreable(f, "phase6_scope.entry_bar is null") for f, _, _, _ in _TAKEN_FIELDS
            ),
            nearest_ts=None, nearest_delta_bars=None, circular=circular,
            notes=("no entry bar in scope -- nothing to pair on",),
        )

    expected = pd.Timestamp(entry_bar["ts"])
    hit = candidates[candidates["ts"] == expected]

    if hit.empty:
        nearest_ts, nearest_bars = None, None
        if not candidates.empty:
            offsets = [
                (bar_offset(bar_index, ts, expected), ts)
                for ts in candidates["ts"]
                if bar_offset(bar_index, ts, expected) is not None
            ]
            if offsets:
                nearest_bars, nearest_ts = min(offsets, key=lambda pair: (abs(pair[0]), pair[0]))
        return LabelResult(
            label_id=label["id"], session=session, label_class=str(label["class"]),
            direction=direction, matched=False, engine_event=None, engine_ts=None,
            blocked_by=(), anchor_matched=False,
            deltas=tuple(
                _unscoreable(f, "no emission on the label's bar") for f, _, _, _ in _TAKEN_FIELDS
            ),
            nearest_ts=nearest_ts, nearest_delta_bars=nearest_bars, circular=circular,
            notes=(),
        )

    row = hit.iloc[0]
    event = str(row["event"])
    notes: list[str] = []
    if len(hit) > 1:
        notes.append(f"{len(hit)} same-direction emissions on this bar; the first is compared")

    engine: dict[str, object] = {
        "anchor_ts": row["anchor_ts"], "trigger": row["trigger"], "stop": row["stop"],
        "r": row["r"], "tp1": row["tp1"],
    }
    if event == "SUPPRESSED":
        borrowed = _l3_prices(entries, expected, engine_direction)
        if borrowed:
            engine = borrowed
            notes.append("prices recovered from L3's ENTRY_FILLED -- a SUPPRESSED row carries none")
        else:
            notes.append("SUPPRESSED with no L3 ENTRY_FILLED on the same bar -- prices unavailable")

    deltas: list[Delta] = []
    for field_name, scope_key, scope_attr, column in _TAKEN_FIELDS:
        block = scope.get(scope_key)
        if block is None:
            deltas.append(_unscoreable(field_name, f"phase6_scope.{scope_key} is null"))
            continue
        label_value = _finite(block.get(scope_attr))
        engine_value = _finite(engine.get(column))
        if label_value is None:
            deltas.append(_unscoreable(field_name, f"phase6_scope.{scope_key}.{scope_attr} is null"))
        elif engine_value is None:
            deltas.append(
                Delta(field_name, label_value, None, None, False, "the engine emitted no value")
            )
        else:
            deltas.append(
                Delta(field_name, label_value, engine_value, engine_value - label_value, True)
            )

    anchor_block = scope.get("anchor_bar")
    anchor_matched: bool | None = None
    if anchor_block is not None:
        engine_anchor = engine.get("anchor_ts")
        anchor_matched = engine_anchor is not None and pd.Timestamp(engine_anchor) == pd.Timestamp(
            anchor_block["ts"]
        )

    return LabelResult(
        label_id=label["id"], session=session, label_class=str(label["class"]),
        direction=direction, matched=True, engine_event=event, engine_ts=expected,
        blocked_by=tuple(str(r) for r in (row["blocked_by"] or ())),
        anchor_matched=anchor_matched, deltas=tuple(deltas),
        nearest_ts=None, nearest_delta_bars=None, circular=circular, notes=tuple(notes),
    )
```

Extend `__all__` to `["COMPARED_ATTRS", "SCOPE_KEYS", "Delta", "LabelResult", "bar_offset", "check_scope_consistency", "reconcile_taken", "resolve_path"]`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_fidelity.py -v`
Expected: PASS, 20 passed

- [ ] **Step 5: Lint and commit**

```bash
uvx ruff check --fix stoic/fidelity.py tests/test_fidelity.py
git add stoic/fidelity.py tests/test_fidelity.py
git commit -m "Pair taken labels on the exact bar, characterise the misses"
```

---

### Task 4: Pairing for `named` and `no_opportunity`

**Files:**
- Modify: `stoic/fidelity.py`
- Modify: `tests/test_fidelity.py`

**Interfaces:**
- Consumes: `Delta`, `LabelResult`, `bar_offset`, `_finite`, `_unscoreable`, `_TERMINAL_EVENTS` from Task 3.
- Produces: `reconcile_named(label, session, entries, bar_index) -> LabelResult` and `reconcile_no_opportunity(label, session, entries, bar_index) -> LabelResult`.

Both pair on L3 records, not L5 emissions: `replay_signals` emits only on a fill, so a label whose correct engine behaviour may be *no emission at all* has nothing there to pair with.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fidelity.py`:

```python
from stoic.fidelity import reconcile_named, reconcile_no_opportunity

NAMED_INDEX = pd.date_range("2026-07-27 13:30", periods=24, freq="5min", tz="UTC")
NOPP_INDEX = pd.date_range("2026-07-30 17:00", periods=24, freq="5min", tz="UTC")


def _named_label() -> dict:
    return {
        "id": "LT-B1",
        "class": "named",
        "direction": "short",
        "phase6_scope": {
            "anchor_bar": {"ts": _utc(2026, 7, 27, 13, 50), "from": "ptb.pos_ts"},
            "entry_bar": None,
            "trigger": {"price": 28446.50, "from": "ptb.trigger.bars"},
            "stop": None, "tp1": None, "expect_fill": None, "circular": False,
        },
    }


def _nopp_label() -> dict:
    return {
        "id": "PTBV30-N1",
        "class": "no_opportunity",
        "direction": "long",
        "phase6_scope": {
            "anchor_bar": None, "entry_bar": None, "trigger": None, "stop": None, "tp1": None,
            "expect_fill": False, "circular": False,
            "anchor_bar_narrated": {"ts": _utc(2026, 7, 30, 17, 25), "from": "bar_5m_et"},
        },
    }


def _anchor(ts, direction="bearish", trigger=28446.50) -> dict:
    return {
        "ts": ts, "event": "PTB_ANCHORED", "direction": direction,
        "anchor_ts": ts, "trigger": trigger, "stop": None, "fill": None, "step3_extreme": None,
    }


def test_named_matches_when_the_engine_anchored_on_that_bar():
    ts = pd.Timestamp("2026-07-27 13:50", tz="UTC")
    result = reconcile_named(_named_label(), "2026-07-27", _entries([_anchor(ts)]), NAMED_INDEX)
    assert result.matched is True
    assert result.engine_event == "PTB_ANCHORED"
    trigger = next(d for d in result.deltas if d.field == "trigger")
    assert trigger.delta == 0.0


def test_named_records_a_fill_as_correct_but_not_taken():
    ts = pd.Timestamp("2026-07-27 13:50", tz="UTC")
    fill = {
        "ts": pd.Timestamp("2026-07-27 13:55", tz="UTC"), "event": "ENTRY_FILLED",
        "direction": "bearish", "anchor_ts": ts, "trigger": 28446.50, "stop": 28500.0,
        "fill": 28440.0, "step3_extreme": None,
    }
    result = reconcile_named(
        _named_label(), "2026-07-27", _entries([_anchor(ts), fill]), NAMED_INDEX
    )
    assert result.matched is True
    assert any("correct-but-not-taken" in note for note in result.notes)


def test_named_unmatched_is_characterised_by_the_nearest_anchor():
    ts = pd.Timestamp("2026-07-27 14:00", tz="UTC")
    result = reconcile_named(_named_label(), "2026-07-27", _entries([_anchor(ts)]), NAMED_INDEX)
    assert result.matched is False
    assert result.nearest_delta_bars == 2


def test_no_opportunity_with_a_cancelled_order_is_a_match():
    ts = pd.Timestamp("2026-07-30 17:25", tz="UTC")
    cancel = {
        "ts": pd.Timestamp("2026-07-30 17:40", tz="UTC"), "event": "ORDER_CANCELLED",
        "direction": "bullish", "anchor_ts": ts, "trigger": 28100.0, "stop": None,
        "fill": None, "step3_extreme": None,
    }
    result = reconcile_no_opportunity(
        _nopp_label(), "2026-07-30",
        _entries([_anchor(ts, direction="bullish", trigger=28100.0), cancel]), NOPP_INDEX,
    )
    assert result.matched is True
    assert result.engine_event == "ORDER_CANCELLED"
    assert result.notes == ("engine emitted no fill -- the label's expectation",)


def test_no_opportunity_negative_control_a_fill_is_a_divergence():
    ts = pd.Timestamp("2026-07-30 17:25", tz="UTC")
    fill = {
        "ts": pd.Timestamp("2026-07-30 17:35", tz="UTC"), "event": "ENTRY_FILLED",
        "direction": "bullish", "anchor_ts": ts, "trigger": 28100.0, "stop": 28050.0,
        "fill": 28101.0, "step3_extreme": None,
    }
    result = reconcile_no_opportunity(
        _nopp_label(), "2026-07-30",
        _entries([_anchor(ts, direction="bullish", trigger=28100.0), fill]), NOPP_INDEX,
    )
    assert result.matched is False
    assert result.engine_event == "ENTRY_FILLED"
    assert any("DIVERGENCE" in note for note in result.notes)


def test_no_opportunity_with_no_anchor_at_all_says_so():
    result = reconcile_no_opportunity(_nopp_label(), "2026-07-30", _entries([]), NOPP_INDEX)
    assert result.matched is False
    assert any("never anchored" in note for note in result.notes)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_fidelity.py -v`
Expected: FAIL — `ImportError: cannot import name 'reconcile_named'`

- [ ] **Step 3: Write the implementation**

Add to `stoic/fidelity.py`:

```python
def _direction_rows(entries: pd.DataFrame, engine_direction: str) -> pd.DataFrame:
    return entries[entries["direction"].astype(str) == engine_direction].sort_values("ts")


def reconcile_named(
    label: dict, session: str, entries: pd.DataFrame, bar_index: pd.DatetimeIndex
) -> LabelResult:
    """Pair a `named` label to L3's `PTB_ANCHORED` on the same bar (`docs/PHASE6.md` §4).

    The trader declined this setup, so there is nothing to score but whether the engine SAW it.
    An engine fill here is **correct-but-not-taken, never a false positive** (`docs/PHASE3.md`
    §2) and is recorded as a note, not as a divergence.
    """
    scope = label["phase6_scope"]
    direction = str(label["direction"])
    engine_direction = "bullish" if direction == "long" else "bearish"
    rows = _direction_rows(entries, engine_direction)
    anchors = rows[rows["event"].astype(str) == "PTB_ANCHORED"]

    anchor_block = scope.get("anchor_bar")
    if anchor_block is None:
        return LabelResult(
            label_id=label["id"], session=session, label_class=str(label["class"]),
            direction=direction, matched=False, engine_event=None, engine_ts=None,
            blocked_by=(), anchor_matched=None,
            deltas=(_unscoreable("trigger", "phase6_scope.anchor_bar is null"),),
            nearest_ts=None, nearest_delta_bars=None, circular=False,
            notes=("no anchor bar in scope -- nothing to pair on",),
        )

    expected = pd.Timestamp(anchor_block["ts"])
    hit = anchors[anchors["ts"] == expected]

    if hit.empty:
        nearest_ts, nearest_bars = None, None
        offsets = [
            (bar_offset(bar_index, ts, expected), ts)
            for ts in anchors["ts"]
            if bar_offset(bar_index, ts, expected) is not None
        ]
        if offsets:
            nearest_bars, nearest_ts = min(offsets, key=lambda pair: (abs(pair[0]), pair[0]))
        return LabelResult(
            label_id=label["id"], session=session, label_class=str(label["class"]),
            direction=direction, matched=False, engine_event=None, engine_ts=None,
            blocked_by=(), anchor_matched=False,
            deltas=(_unscoreable("trigger", "the engine anchored no order on this bar"),),
            nearest_ts=nearest_ts, nearest_delta_bars=nearest_bars, circular=False,
            notes=("the engine never saw this setup on the label's bar",),
        )

    row = hit.iloc[0]
    notes: list[str] = []
    later = rows[rows["ts"] > expected]
    terminal = later[later["event"].astype(str).isin(_TERMINAL_EVENTS)]
    if not terminal.empty and str(terminal.iloc[0]["event"]) == "ENTRY_FILLED":
        notes.append(
            "the engine filled this order -- correct-but-not-taken, never a false positive "
            "(docs/PHASE3.md §2)"
        )

    trigger_block = scope.get("trigger")
    if trigger_block is None:
        delta = _unscoreable("trigger", "phase6_scope.trigger is null")
    else:
        label_value = _finite(trigger_block.get("price"))
        engine_value = _finite(row["trigger"])
        delta = (
            Delta("trigger", label_value, engine_value, engine_value - label_value, True)
            if label_value is not None and engine_value is not None
            else _unscoreable("trigger", "no trigger on one side", label_value)
        )

    return LabelResult(
        label_id=label["id"], session=session, label_class=str(label["class"]),
        direction=direction, matched=True, engine_event="PTB_ANCHORED", engine_ts=expected,
        blocked_by=(), anchor_matched=True, deltas=(delta,),
        nearest_ts=None, nearest_delta_bars=None, circular=False, notes=tuple(notes),
    )


def reconcile_no_opportunity(
    label: dict, session: str, entries: pd.DataFrame, bar_index: pd.DatetimeIndex
) -> LabelResult:
    """Score a `no_opportunity` label over the working order's OWN LIFETIME.

    The label says the bars never traded through the trigger, so the engine is required to emit
    no fill (`docs/PHASE3.md` §2; the label's own `phase_6_expectation`). This is the one class
    where absence is the right answer and the bars can settle it -- and it needs **no window**:
    the interval is the order's life, from its anchor to the first terminal event
    (`ENTRY_FILLED` / `ORDER_CANCELLED` / `ORDER_VOIDED`, §5.3.4a's closed list of three).
    A terminal event of `ENTRY_FILLED` is the divergence.
    """
    scope = label["phase6_scope"]
    direction = str(label["direction"])
    engine_direction = "bullish" if direction == "long" else "bearish"
    rows = _direction_rows(entries, engine_direction)

    anchor_block = scope.get("anchor_bar") or scope.get("anchor_bar_narrated")
    expected = pd.Timestamp(anchor_block["ts"]) if anchor_block else None
    anchors = rows[rows["event"].astype(str) == "PTB_ANCHORED"]
    hit = anchors[anchors["ts"] == expected] if expected is not None else anchors.iloc[0:0]

    if hit.empty:
        nearest_ts, nearest_bars = None, None
        if expected is not None:
            offsets = [
                (bar_offset(bar_index, ts, expected), ts)
                for ts in anchors["ts"]
                if bar_offset(bar_index, ts, expected) is not None
            ]
            if offsets:
                nearest_bars, nearest_ts = min(offsets, key=lambda pair: (abs(pair[0]), pair[0]))
        return LabelResult(
            label_id=label["id"], session=session, label_class=str(label["class"]),
            direction=direction, matched=False, engine_event=None, engine_ts=None,
            blocked_by=(), anchor_matched=False, deltas=(),
            nearest_ts=nearest_ts, nearest_delta_bars=nearest_bars, circular=False,
            notes=("the engine never anchored an order on this bar",),
        )

    later = rows[rows["ts"] > expected]
    terminal = later[later["event"].astype(str).isin(_TERMINAL_EVENTS)]
    if terminal.empty:
        return LabelResult(
            label_id=label["id"], session=session, label_class=str(label["class"]),
            direction=direction, matched=True, engine_event=None, engine_ts=expected,
            blocked_by=(), anchor_matched=True, deltas=(),
            nearest_ts=None, nearest_delta_bars=None, circular=False,
            notes=("the order was still working at the end of the slice -- no fill",),
        )

    end = terminal.iloc[0]
    event = str(end["event"])
    if event == "ENTRY_FILLED":
        return LabelResult(
            label_id=label["id"], session=session, label_class=str(label["class"]),
            direction=direction, matched=False, engine_event=event, engine_ts=end["ts"],
            blocked_by=(), anchor_matched=True, deltas=(),
            nearest_ts=end["ts"], nearest_delta_bars=bar_offset(bar_index, end["ts"], expected),
            circular=False,
            notes=(
                "DIVERGENCE: the engine filled an order the bars never traded through the "
                "trigger for",
            ),
        )
    return LabelResult(
        label_id=label["id"], session=session, label_class=str(label["class"]),
        direction=direction, matched=True, engine_event=event, engine_ts=end["ts"],
        blocked_by=(), anchor_matched=True, deltas=(),
        nearest_ts=None, nearest_delta_bars=None, circular=False,
        notes=("engine emitted no fill -- the label's expectation",),
    )
```

Add `"reconcile_named"` and `"reconcile_no_opportunity"` to `__all__`, keeping it sorted.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_fidelity.py -v`
Expected: PASS, 26 passed

- [ ] **Step 5: Lint and commit**

```bash
uvx ruff check --fix stoic/fidelity.py tests/test_fidelity.py
git add stoic/fidelity.py tests/test_fidelity.py
git commit -m "Score named against L3 anchors and no_opportunity over the order's own lifetime"
```

---

### Task 5: Unlabelled emissions and report rendering

**Files:**
- Modify: `stoic/fidelity.py`
- Modify: `tests/test_fidelity.py`

**Interfaces:**
- Consumes: `LabelResult`, `Delta` from Tasks 3–4.
- Produces: `unlabelled_emissions(emissions, results) -> pd.DataFrame` and `render_report(results, unlabelled, params) -> str`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fidelity.py`:

```python
from stoic.fidelity import render_report, unlabelled_emissions


def test_unlabelled_drops_the_matched_bars_only():
    matched = _signal_row()
    other = _signal_row(ts=pd.Timestamp("2026-07-31 15:10", tz="UTC"))
    results = [
        reconcile_taken(_label(), "2026-07-31", _emissions([matched]), _entries([]), BAR_INDEX)
    ]
    left = unlabelled_emissions(_emissions([matched, other]), results)
    assert len(left) == 1
    assert left.iloc[0]["ts"] == pd.Timestamp("2026-07-31 15:10", tz="UTC")


def test_unlabelled_keeps_a_same_bar_emission_of_the_other_direction():
    matched = _signal_row()
    opposite = _signal_row(direction="bullish")
    results = [
        reconcile_taken(_label(), "2026-07-31", _emissions([matched]), _entries([]), BAR_INDEX)
    ]
    left = unlabelled_emissions(_emissions([matched, opposite]), results)
    assert len(left) == 1
    assert str(left.iloc[0]["direction"]) == "bullish"


def test_report_states_the_no_verdict_line_and_the_counts():
    results = [
        reconcile_taken(_label(), "2026-07-31", _emissions([_signal_row()]), _entries([]), BAR_INDEX)
    ]
    text = render_report(results, _emissions([]), {"instrument": "NQ", "frame": "5m"})
    assert "the label set is not exhaustive" in text
    assert "no verdict" in text
    assert "T-A2" in text
    assert "instrument" in text


def test_report_marks_a_circular_row():
    label = _label()
    label["phase6_scope"]["circular"] = True
    results = [
        reconcile_taken(label, "2026-07-31", _emissions([_signal_row()]), _entries([]), BAR_INDEX)
    ]
    assert "circular" in render_report(results, _emissions([]), {}).lower()


def test_report_prints_unscoreable_rather_than_a_blank():
    label = _label()
    label["phase6_scope"]["trigger"] = None
    results = [
        reconcile_taken(label, "2026-07-31", _emissions([_signal_row()]), _entries([]), BAR_INDEX)
    ]
    assert "unscoreable" in render_report(results, _emissions([]), {})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_fidelity.py -v`
Expected: FAIL — `ImportError: cannot import name 'unlabelled_emissions'`

- [ ] **Step 3: Write the implementation**

Add to `stoic/fidelity.py`:

```python
_NO_VERDICT = (
    "**The label set is not exhaustive, so none of these is a false positive.** The four charts "
    "record what the trader took and named, never every setup the session offered. No rate is "
    "computed from this section and no verdict follows from it (`CLAUDE.md`)."
)


def unlabelled_emissions(emissions: pd.DataFrame, results: list[LabelResult]) -> pd.DataFrame:
    """Every `SIGNAL` / `SUPPRESSED` row that no label paired with.

    Pairing identity is `(ts, engine direction)`: an emission on a matched bar in the OTHER
    direction is a different candidate and stays in this list.
    """
    paired = {
        (pd.Timestamp(r.engine_ts), "bullish" if r.direction == "long" else "bearish")
        for r in results
        if r.matched and r.engine_ts is not None and r.label_class == "taken"
    }
    rows = emissions[emissions["event"].astype(str).isin(["SIGNAL", "SUPPRESSED"])]
    keep = [
        (pd.Timestamp(ts), str(direction)) not in paired
        for ts, direction in zip(rows["ts"], rows["direction"], strict=True)
    ]
    return rows[keep]


def _delta_cell(delta: Delta) -> str:
    if not delta.scoreable:
        return f"unscoreable — {delta.reason}"
    return f"{delta.delta:+.2f} (label {delta.label:.2f}, engine {delta.engine:.2f})"


def render_report(
    results: list[LabelResult], unlabelled: pd.DataFrame, params: dict[str, object]
) -> str:
    """The whole of `docs/evidence/phase6_reconciliation.md` except §2, which is hand-written.

    §2 is deliberately absent from this function: `docs/PLAN.md`'s exit gate asks for divergences
    **explained**, and an explanation is a reading of the artifact, not something a harness can
    produce. The driver writes a §2 stub for a human to fill in.
    """
    lines: list[str] = ["# Phase 6 — reconciliation", ""]
    lines.append("Design: `docs/PHASE6.md`. Generated by `scripts/reconcile_labels.py`;")
    lines.append("§2 is hand-written. **Counts, never verdicts** (`CLAUDE.md`).")
    lines.append("")
    lines.append("## Run parameters")
    lines.append("")
    lines.append("| | |")
    lines.append("|---|---|")
    for key, value in params.items():
        lines.append(f"| {key} | `{value}` |")
    lines.append("")

    lines.append("## 1. Per-label reconciliation")
    lines.append("")
    matched = sum(1 for r in results if r.matched)
    lines.append(f"{len(results)} labels, {matched} matched on the exact bar.")
    lines.append("")
    for result in results:
        flag = " — **CIRCULAR reference, nothing is drawn from this row**" if result.circular else ""
        lines.append(f"### {result.label_id} — {result.label_class}, {result.direction}{flag}")
        lines.append("")
        lines.append(f"- session: `{result.session}`")
        lines.append(f"- matched: **{result.matched}**")
        lines.append(f"- engine event: `{result.engine_event}` at `{result.engine_ts}`")
        if result.blocked_by:
            lines.append(f"- blocked_by: `{', '.join(result.blocked_by)}`")
        if result.anchor_matched is not None:
            lines.append(f"- anchor bar matched: **{result.anchor_matched}**")
        if not result.matched and result.nearest_ts is not None:
            lines.append(
                f"- nearest same-direction emission: `{result.nearest_ts}`, "
                f"**{result.nearest_delta_bars:+d} bars**"
            )
        for delta in result.deltas:
            lines.append(f"- {delta.field}: {_delta_cell(delta)}")
        for note in result.notes:
            lines.append(f"- note: {note}")
        lines.append("")

    lines.append("## 2. Divergences")
    lines.append("")
    lines.append("*Hand-written. Each divergence is triaged as a **specification bug in the")
    lines.append("engine**, a **missing rule in `docs/RULEBOOK.md`**, or **out of v1 scope** —")
    lines.append("and the third names the row that already put it out of scope.*")
    lines.append("")

    lines.append(f"## 3. Unlabelled emissions (n = {len(unlabelled)})")
    lines.append("")
    lines.append(_NO_VERDICT)
    lines.append("")
    lines.append("| ts | direction | event | trigger | fill | stop | R |")
    lines.append("|---|---|---|---|---|---|---|")
    for _, row in unlabelled.iterrows():
        lines.append(
            f"| `{row['ts']}` | {row['direction']} | {row['event']} | {row['trigger']} "
            f"| {row['fill']} | {row['stop']} | {row['r']} |"
        )
    lines.append("")
    return "\n".join(lines)
```

Add `"render_report"` and `"unlabelled_emissions"` to `__all__`, keeping it sorted.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_fidelity.py -v`
Expected: PASS, 31 passed

- [ ] **Step 5: Lint and commit**

```bash
uvx ruff check --fix stoic/fidelity.py tests/test_fidelity.py
git add stoic/fidelity.py tests/test_fidelity.py
git commit -m "List unlabelled emissions without a verdict, and render the report"
```

---

### Task 6: The import-direction test

**Files:**
- Modify: `tests/test_fidelity.py`

**Interfaces:**
- Consumes: nothing. Reads `stoic/*.py` as text and parses it with `ast`.
- Produces: nothing importable.

`VISION.md` puts the deterministic signal path in `stoic/`. A measurement module living beside it must never be reachable from it, and a comment saying so is not a check. This is the structural equivalent of the negative control `coding_rules.md` asks of a gate.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fidelity.py`:

```python
import ast
from pathlib import Path

STOIC = Path(__file__).resolve().parents[1] / "stoic"


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_no_engine_module_imports_fidelity():
    """Measurement must never be reachable from the signal path (docs/PHASE6.md §5)."""
    offenders = [
        path.name
        for path in sorted(STOIC.glob("*.py"))
        if path.name != "fidelity.py"
        if any("fidelity" in name for name in _imported_names(path))
    ]
    assert offenders == []


def test_the_import_check_can_actually_see_an_import(tmp_path):
    """Negative control: the same parser must catch a planted import."""
    planted = tmp_path / "planted.py"
    planted.write_text("from stoic.fidelity import reconcile_taken\n", encoding="utf-8")
    assert any("fidelity" in name for name in _imported_names(planted))
```

- [ ] **Step 2: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_fidelity.py -v -k import`
Expected: PASS, 2 passed. Both pass immediately — the first because the invariant already holds, the second because it plants the fault. If `test_no_engine_module_imports_fidelity` fails, an engine module has an import that must be removed; do not weaken the test.

- [ ] **Step 3: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: `273 passed` — the 240 baseline in `docs/STATE.md` plus this file's 33. Report the literal number you see; if it is not 240 + 33, say so rather than adjusting this line.

- [ ] **Step 4: Lint and commit**

```bash
uvx ruff check --fix tests/test_fidelity.py
git add tests/test_fidelity.py
git commit -m "Assert nothing in the signal path imports the measurement module"
```

---

### Task 7: `scripts/reconcile_labels.py` — the driver, and the first run

**Files:**
- Create: `scripts/reconcile_labels.py`
- Create (generated): `docs/evidence/phase6_reconciliation.md`
- Create (generated): `.artifacts/phase6/emissions.csv`, `.artifacts/phase6/entries.csv`

**Interfaces:**
- Consumes: everything from `stoic.fidelity`; `stoic.bars.load_bars`, `stoic.indicators.add_smas`, `stoic.judgment.attach_parent_pos`, `stoic.judgment.decided_judgment`, `stoic.entry.replay_entries`, `stoic.emission.replay_signals`, `stoic.emission.SignalType`.
- Produces: the report. Nothing imports this script.

- [ ] **Step 1: Write the driver**

Create `scripts/reconcile_labels.py`:

```python
"""Phase 6's driver: replay the engine over the label sessions and write the reconciliation.

Design: `docs/PHASE6.md`. This is the only file in Phase 6 that touches disk. All measurement
logic is in `stoic/fidelity.py`, which is pure and unit-tested; this script loads, runs, and
writes.

One continuous pass, per `docs/PHASE6.md` §3: `stoic/sequence.py` has no session awareness, so a
per-session run would start the state machine cold in a way live never is. The window opens on
2026-06-22, after the `2026-06-11` -> `2026-06-19` hole (`docs/STATE.md` Open), so the run never
crosses a known hole and needs no exclusion rule.

Gate 0 refuses to run if any `phase6_scope` block disagrees with the field it names. A stale
block is exactly the failure `docs/PHASE3.md` warns of -- nothing re-checks a label when a bar or
a reading changes -- and a run against one would report engine divergences that are ours.

Read-mostly: it writes the report and two CSVs and nothing else. It takes well under a minute, so
there is nothing to resume; each stage prints its own elapsed time.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stoic.bars import load_bars
from stoic.emission import SignalType, replay_signals
from stoic.entry import replay_entries
from stoic.fidelity import (
    check_scope_consistency,
    reconcile_named,
    reconcile_no_opportunity,
    reconcile_taken,
    render_report,
    unlabelled_emissions,
)
from stoic.indicators import add_smas
from stoic.judgment import attach_parent_pos, decided_judgment

REPO = Path(__file__).resolve().parents[1]
LABELS_DIR = REPO / "docs" / "evidence" / "labels"
REPORT = REPO / "docs" / "evidence" / "phase6_reconciliation.md"
ARTIFACTS = REPO / ".artifacts" / "phase6"

INSTRUMENT = "NQ"
FRAME = "5m"
WINDOW_START = "2026-06-22"
WINDOW_END = "2026-08-04"
TYPE_ = SignalType.SCALP


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def main() -> int:
    started = time.monotonic()

    files = sorted(LABELS_DIR.glob("*.yaml"))
    documents = [yaml.safe_load(path.read_text(encoding="utf-8")) for path in files]
    labels = [
        (document["session"], label) for document in documents for label in document["labels"]
    ]
    print(f"[load] {len(files)} label files, {len(labels)} labels")

    problems = [line for _, label in labels for line in check_scope_consistency(label)]
    print(f"[gate 0] scope consistency: {len(problems)} problems")
    for line in problems:
        print(f"  - {line}")
    if problems:
        print("[gate 0] [FAIL] fix the phase6_scope block, never the label field it names")
        return 1
    print("[gate 0] [PASS]")

    stage = time.monotonic()
    bars = attach_parent_pos(
        add_smas(load_bars(INSTRUMENT, FRAME).loc[WINDOW_START:WINDOW_END])
    )
    print(f"[bars] {len(bars)} rows, {bars.index[0]} -> {bars.index[-1]} ({time.monotonic() - stage:.1f}s)")

    judgment = decided_judgment()

    stage = time.monotonic()
    entries = replay_entries(bars, judgment)
    print(f"[L3] {len(entries)} records {dict(entries['event'].value_counts())} ({time.monotonic() - stage:.1f}s)")

    stage = time.monotonic()
    emissions = replay_signals(
        bars, judgment, instrument=INSTRUMENT, type_=TYPE_, htf=None
    )
    print(f"[L5] {len(emissions)} rows {dict(emissions['event'].value_counts())} ({time.monotonic() - stage:.1f}s)")

    sessions = sorted({session for session, _ in labels})
    results = []
    for session, label in labels:
        day = pd.Timestamp(session).date()
        in_day = emissions[emissions["ts"].dt.date == day]
        entries_in_day = entries[entries["ts"].dt.date == day]
        klass = str(label["class"])
        if klass == "taken":
            results.append(reconcile_taken(label, session, in_day, entries_in_day, bars.index))
        elif klass == "named":
            results.append(reconcile_named(label, session, entries_in_day, bars.index))
        elif klass == "no_opportunity":
            results.append(
                reconcile_no_opportunity(label, session, entries_in_day, bars.index)
            )
        else:
            raise ValueError(f"{label['id']}: unknown label class {klass!r}")

    session_days = {pd.Timestamp(s).date() for s in sessions}
    in_sessions = emissions[emissions["ts"].dt.date.isin(session_days)]
    unlabelled = unlabelled_emissions(in_sessions, results)

    params = {
        "instrument": INSTRUMENT,
        "frame": FRAME,
        "window": f"{WINDOW_START} -> {WINDOW_END}",
        "bars": len(bars),
        "type": TYPE_,
        "htf": "None -- confluence tops out at 2 of 3 (D-32's recorded consequence)",
        "judgment": "decided_judgment() -- D-29, D-30, D-34 defaults",
        "matching": "exact bar, no tolerance (docs/PHASE6.md §4)",
        "data holes": "2025-11-28 and 2026-06-11->06-19 both sit outside this window",
        "warm-up": "L4 needs 50 bars for any signal and 200 for a long on a fast chart",
    }

    _write_atomic(REPORT, render_report(results, unlabelled, params))
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    emissions.to_csv(ARTIFACTS / "emissions.csv", index=False)
    entries.to_csv(ARTIFACTS / "entries.csv", index=False)

    matched = sum(1 for r in results if r.matched)
    print(f"[report] {REPORT}")
    print(f"[report] {len(results)} labels, {matched} matched, {len(unlabelled)} unlabelled")
    print(f"[done] {time.monotonic() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Lint**

Run: `uvx ruff check --fix scripts/reconcile_labels.py`
Expected: `All checks passed!`

- [ ] **Step 3: Run it**

Run: `.venv/bin/python scripts/reconcile_labels.py`
Expected: `[gate 0] [PASS]`, then `[bars] 8784 rows`, then L3 and L5 counts, then `[report] ...` and `[done]`. Exit code 0.

**Paste the verbatim output into the task report.** `coding_rules.md`: never summarise a number you were asked to verify. If Gate 0 fails, stop and fix the block — do not edit the label field it disagrees with, and do not proceed to Task 8.

- [ ] **Step 4: Read the report before committing it**

Run: `cat docs/evidence/phase6_reconciliation.md`

Check three things and state each in the task report: every label appears in §1; `NQ3-A1` carries its **CIRCULAR** flag; §3 carries the not-exhaustive line. Do **not** edit any number to make it look better — a wrong number is a finding.

- [ ] **Step 5: Commit**

```bash
git add scripts/reconcile_labels.py docs/evidence/phase6_reconciliation.md
git commit -m "Run Phase 6 over the four label sessions, §1 and §3 generated

One continuous NQ 5m pass, 2026-06-22 -> 2026-08-04, Scalp, htf=None,
decided_judgment(). Exact-bar matching, no tolerance. §2 is still a stub —
divergences are explained by hand, not by the harness."
```

---

### Task 8: Triage §2 by hand, then update the two entry-point documents

**Files:**
- Modify: `docs/evidence/phase6_reconciliation.md` (§2 only)
- Modify: `docs/STATE.md`
- Modify: `docs/CONSTRAINTS.md`

**Interfaces:**
- Consumes: the report from Task 7.
- Produces: nothing importable.

**This task is reading, not coding.** No engine file, no label field and no line of `docs/RULEBOOK.md` is edited by it.

- [ ] **Step 1: Triage every divergence in §2**

For each unmatched label and each `DIVERGENCE` note in §1, write one entry under §2 with exactly these four lines:

```markdown
### <label id> — <one-line statement of what differs>

- **What the engine did:** <bar, direction, event, and the numbers, from §1>
- **What the label says:** <the reference values and their provenance>
- **Triage:** specification bug in the engine | missing rule in `docs/RULEBOOK.md` | out of v1 scope
- **Basis:** <the section, D-row or O-row that supports the triage; for "out of v1 scope", the row that already put it there>
```

Rules for this step, each from a document already in the repo:

- **Never conclude from small *n*.** Four sessions, ten labels. State counts; project no direction (`CLAUDE.md`).
- **"Out of v1 scope" must name the row that already put it there** — `LT34-A1`'s flatten (`docs/STATE.md` Open), `T-A2`'s discretionary stop move (`docs/CONSTRAINTS.md`), `NQ3-A1`'s open position. If no such row exists, it is not out of scope.
- **Check the label before the engine** (`VISION.md`, *Evidence*): there is no `verify_labels.py`, so a stale label presents as an engine divergence. Open the source artifact named in the label's `artifact:` field before calling anything an engine bug.
- **A specification bug is reported here and fixed nowhere.** Fixing it is a separate change against a rulebook section, with the register entry that requires.

- [ ] **Step 2: Verify the citation gate still passes**

Run: `.venv/bin/python scripts/verify_citations.py`
Expected: `222 citations across 8 sources, all resolve` and its negative control PASS. Paste the verbatim output.

- [ ] **Step 3: Update `docs/STATE.md`**

Replace the *"The critical path is Phase 3"* framing with what is now true. State, as counts and never as a verdict: labels reconciled, matched on the exact bar, divergences by triage class, unlabelled emissions. Name `docs/PHASE6.md` as the design and `docs/evidence/phase6_reconciliation.md` as the record. Add any open question the run raised to the **Open** list. Remove nothing that is still true; this file says what is true now, and `git log` says what happened.

- [ ] **Step 4: Add three rows to `docs/CONSTRAINTS.md`**

Each is a trigger pointing at a source — **the row is never the rule**:

| When you are about to… | Open |
|---|---|
| **Reconcile an engine emission against a label, or reach for a tolerance** | `docs/PHASE6.md` §4 — exact bar, no tolerance anywhere, the user's call 2026-08-11. `stoic/fidelity.py` holds no number and must stay that way |
| **Read the unlabelled-emission count as a false-positive rate** | `docs/evidence/phase6_reconciliation.md` §3 — the label set is not exhaustive, so it is not one |
| **Add or change a `phase6_scope` block** | `docs/PHASE6.md` §2 — additive only, `from:` must resolve, and Gate 0 in `scripts/reconcile_labels.py` refuses the run if a block disagrees with the field it names. A block that disagrees is a bug in the block |

- [ ] **Step 5: Commit**

```bash
git add docs/evidence/phase6_reconciliation.md docs/STATE.md docs/CONSTRAINTS.md
git commit -m "Triage Phase 6's divergences by hand and record the phase in STATE"
```

- [ ] **Step 6: Report the top three recurring errors**

`coding_rules.md` asks for them at the end of a task so they can be added to that file. Report them; do not edit `coding_rules.md` without the user's say-so.

---

## Self-review

**Spec coverage.** `docs/PHASE6.md` §1 → Tasks 3–4 (the heterogeneous-schema handling and the two non-comparisons). §2 → Task 2, gated by Task 1. §3 → Task 7. §4 → Tasks 3–4. §5 → Tasks 1, 3–6. §6 → Tasks 5, 7, 8. §7 → Task 8. *What this phase does not do* → the Global Constraints and Task 8's rules.

**Placeholders.** None. Every step shows the code or the exact command and its expected output. Task 8 is prose by design — a triage is a human reading — and it ships the exact four-line template rather than an instruction to "write it up".

**Type consistency.** `LabelResult` and `Delta` are defined once in Task 3 and used unchanged in Tasks 4–5. `bar_offset(bar_index, a, b)` keeps one signature. `_finite`, `_unscoreable`, `_TERMINAL_EVENTS` and `_direction_rows` are defined before first use. `reconcile_taken` takes `(label, session, emissions, entries, bar_index)`; `reconcile_named` and `reconcile_no_opportunity` take `(label, session, entries, bar_index)` — no emissions, because both pair on L3.

**One known gap, deliberate.** The engine's direction enum is `bullish`/`bearish` and a label's is `long`/`short`; every reconcile function converts at its top and the tests exercise both spellings.
