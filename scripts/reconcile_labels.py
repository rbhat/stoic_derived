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
    print(
        f"[bars] {len(bars)} rows, {bars.index[0]} -> {bars.index[-1]} "
        f"({time.monotonic() - stage:.1f}s)"
    )

    judgment = decided_judgment()

    stage = time.monotonic()
    entries = replay_entries(bars, judgment)
    print(
        f"[L3] {len(entries)} records {dict(entries['event'].value_counts())} "
        f"({time.monotonic() - stage:.1f}s)"
    )

    stage = time.monotonic()
    emissions = replay_signals(
        bars, judgment, instrument=INSTRUMENT, type_=TYPE_, htf=None
    )
    print(
        f"[L5] {len(emissions)} rows {dict(emissions['event'].value_counts())} "
        f"({time.monotonic() - stage:.1f}s)"
    )

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
