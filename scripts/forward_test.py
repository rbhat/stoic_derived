"""Phase 7's driver: replay the engine over a window, track every `SIGNAL` to a closed (or still
open) outcome, and append the append-only ledger.

Design: `docs/PHASE7.md`. §4-§9 are this script's spec; `stoic/tracking.py` (pure, unit-tested) is
the measurement, this is the only file in Phase 7 that touches disk. Shape mirrors
`scripts/reconcile_labels.py` -- the `sys.path` preamble, the argparse CLI, the report written
tmp-then-`os.replace` -- because that is the shape Phase 6 already proved out.

**One continuous replay per run, always from the pinned frame start.** `stoic.sequence.replay`
and `stoic.entry`'s state machines have no serialisable checkpoint, so there is no partial-frame
resume of the replay itself -- see `docs/PHASE7.md` §7's "no second bar loop is written anywhere
in this phase," which is also why this script cannot show live per-bar progress: the two replays
it calls (`stoic.sequence.replay`, `stoic.emission.replay_signals`) are each one opaque pass over
the whole frame. What **is** resumable, and is the thing `CLAUDE.md`'s resumability directive
actually binds here, is the **ledger**: a fold reconstructs known signal ids, closed signal ids and
the pinned frame start before anything is written, and only rows for ids the fold has not already
seen are appended (§5, §6). The watermark row exists for exactly that framing -- it tells a human
how many bars are new since the last run, not how much replay work can be skipped.

**This script only supports Types whose setup timeframe is 5m** (Scalp, Day -- `stoic.emission.
TYPE_SPECS`). Swing (60m) and Position (1D) are out of scope: the pipeline always resamples the 1m
source to 5m (per this file's own spec) and D-7 requires the sequence run on its Type's setup
timeframe, so running Swing/Position through a 5m frame would silently mismatch the timeframe the
emitted `SignalRecord.setup_tf` claims. Refused at the CLI rather than run wrong.

Ledger row kinds, one JSON object per line, `<ledger_home>/<type>.jsonl`: `header` (first line),
`frame` (pins `frame_start` per `(instrument, timeframe)`, refused on disagreement), `signal`,
`suppressed`, `break_even`, `outcome`, `watermark`. `suppressed` and `break_even` rows carry no
`signal_id` of their own (`stoic.emission.EmissionRecord`'s schema) -- since this driver always
replays a pinned frame start to end, a rerun reproduces every prior `SUPPRESSED`/`BREAK_EVEN` event
identically, so each is keyed for idempotent appends by `(pos, direction)` /
`(pos, direction, signal_id)` respectively, not specified in `docs/PHASE7.md` and fixed here.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stoic.bars import resample
from stoic.emission import TYPE_SPECS, EmissionEvent, SignalType, replay_signals
from stoic.indicators import add_smas
from stoic.judgment import attach_parent_pos, decided_judgment
from stoic.sequence import replay as sequence_replay
from stoic.tracking import Outcome, TrackFlag, track_outcomes

REPO = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = REPO / "docs" / "evidence"


def default_report_path(instrument: str, type_: str) -> Path:
    """The report names its instrument and Type because they are what it is about. One fixed path
    means a `--type day` run silently destroys the Scalp evidence in place (docs/PHASE7.md §8)."""
    return EVIDENCE_DIR / f"phase7_forward_test_{instrument}_{type_}.md"
DEFAULT_LEDGER_HOME = REPO / ".artifacts" / "ledger"
TIMEFRAME = "5m"  # every supported Type (Scalp, Day) runs the sequence here -- see module docstring
SOURCE = "stoic_123"  # stoic.emission.replay_signals' own default; suppressed/break_even rows
# carry no `source` field of their own (see module docstring), so this driver supplies the same
# constant it asked the engine to emit under.

_FLAGGED_KINDS = (TrackFlag.GAP_BEYOND_TP1, TrackFlag.RESOLVED_ON_1M, TrackFlag.FLATTEN_5M_FALLBACK)


# ---------------------------------------------------------------------------
# The ledger -- fold (read) and append (write). docs/PHASE7.md §5, §9.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LedgerFold:
    """Everything a run needs from a prior one, read once at start (§6: "the fold is the truth,
    the watermark is a fast path"). `known_signal_ids` gates which `signal` rows get appended,
    `closed_signal_ids` gates which `outcome` rows do -- §5's idempotency rule, literally."""

    known_signal_ids: frozenset[str] = frozenset()
    closed_signal_ids: frozenset[str] = frozenset()
    # Both keys lead with the instrument (§5): `pos` indexes a *per-instrument* frame, while one
    # Type's ledger holds several instruments -- the same reason the frame start is pinned per
    # (instrument, timeframe). Without it, NQ then ES into one file drops every ES row whose
    # (pos, direction) happens to match an NQ one.
    known_suppressed_keys: frozenset[tuple[str, int, str]] = frozenset()
    known_break_even_keys: frozenset[tuple[str, int, str, str]] = frozenset()
    frame_starts: dict[tuple[str, str], pd.Timestamp] = field(default_factory=dict)
    watermarks: dict[tuple[str, str, str], pd.Timestamp] = field(default_factory=dict)


def _read_ledger_lines(path: Path) -> list[dict]:
    """Every parsed JSON row in `path`, tolerating a torn trailing line (§5, §9's negative
    control): dropped with a warning if the last line fails to parse, raised on any other line.
    """
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    raw_lines = text.split("\n")
    if raw_lines and raw_lines[-1] == "":
        raw_lines.pop()  # trailing newline, not a torn row

    records: list[dict] = []
    n = len(raw_lines)
    for i, line in enumerate(raw_lines):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            if i == n - 1:
                print(
                    f"[fold] warning: dropped a torn trailing line in {path} "
                    f"(line {i + 1}: {line!r})"
                )
                continue
            raise ValueError(
                f"{path}: malformed ledger line {i + 1} (not the trailing line): {line!r}"
            ) from exc
    return records


def fold_ledger(path: Path) -> LedgerFold:
    """The ledger's current state, rebuilt by reading every line (§6). Raises `ValueError` if the
    same `signal_id` appears in more than one `signal` row -- §9's negative control: this must
    never happen, and the check is what makes that a checked property rather than an assumption.
    """
    records = _read_ledger_lines(path)

    known: set[str] = set()
    closed: set[str] = set()
    suppressed_keys: set[tuple[str, int, str]] = set()
    break_even_keys: set[tuple[str, int, str, str]] = set()
    frame_starts: dict[tuple[str, str], pd.Timestamp] = {}
    watermarks: dict[tuple[str, str, str], pd.Timestamp] = {}
    # Duplicate detection covers EVERY row kind, not just `signal` (§5). A duplicate absorbed
    # silently into a set is a lost row that reports as success -- the one thing the exit gate
    # exists to rule out. `header` and `watermark` are exempt by design: one header is the format,
    # and a watermark is a moving position, not a record of an event.
    duplicates: dict[str, list[str]] = {}

    def seen(kind: str, key: object, into: set) -> None:
        if key in into:
            duplicates.setdefault(kind, []).append(repr(key))
        into.add(key)

    for i, rec in enumerate(records):
        kind = rec.get("kind")
        if kind == "header":
            continue
        if kind == "frame":
            frame_key = (rec["instrument"], rec["timeframe"])
            if frame_key in frame_starts:
                duplicates.setdefault("frame", []).append(repr(frame_key))
            frame_starts.setdefault(frame_key, pd.Timestamp(rec["frame_start"]))
        elif kind == "signal":
            seen("signal", rec["signal_id"], known)
        elif kind == "suppressed":
            seen(
                "suppressed",
                (str(rec["instrument"]), int(rec["pos"]), str(rec["direction"])),
                suppressed_keys,
            )
        elif kind == "break_even":
            seen(
                "break_even",
                (
                    str(rec["instrument"]),
                    int(rec["pos"]),
                    str(rec["direction"]),
                    str(rec["signal_id"]),
                ),
                break_even_keys,
            )
        elif kind == "outcome":
            seen("outcome", rec["signal_id"], closed)
        elif kind == "watermark":
            watermark_key = (rec["instrument"], rec["timeframe"], rec["type"])
            watermarks[watermark_key] = pd.Timestamp(rec["last_bar_ts"])
        else:
            raise ValueError(f"{path}: unknown ledger row kind {kind!r} at line {i + 1}")

    if duplicates:
        detail = "; ".join(f"{k}: {sorted(v)}" for k, v in sorted(duplicates.items()))
        raise ValueError(
            f"{path}: duplicate ledger rows -- this must never happen -- {detail}"
        )

    return LedgerFold(
        known_signal_ids=frozenset(known),
        closed_signal_ids=frozenset(closed),
        known_suppressed_keys=frozenset(suppressed_keys),
        known_break_even_keys=frozenset(break_even_keys),
        frame_starts=frame_starts,
        watermarks=watermarks,
    )


def _clean(value: object) -> object:
    """JSON-safe conversion for a single ledger field: pandas/numpy scalars, `pd.NA`/`NaT`/NaN,
    tuples and `StrEnum`s all need a hand -- `json.dumps` does not know any of them natively."""
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, (tuple, list)):
        return [_clean(v) for v in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, pd.Timedelta):
        return str(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if np.isnan(value) else float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if value is pd.NA:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None
    return value


def _clean_row(row: dict) -> dict:
    return {k: _clean(v) for k, v in row.items()}


def _truncate_torn_tail(path: Path) -> None:
    """Drop an incomplete final line, so the next append starts on a row boundary.

    A ledger file always ends in `\\n` when the last write completed. If it does not, the bytes
    after the last newline are a row that was never finished -- exactly what `_read_ledger_lines`
    already refuses to parse. Truncating them removes nothing a fold would have kept.
    """
    if not path.exists():
        return
    size = path.stat().st_size
    if size == 0:
        return
    with open(path, "rb+") as fh:
        fh.seek(-1, os.SEEK_END)
        if fh.read(1) == b"\n":
            return
        data = path.read_bytes()
        cut = data.rfind(b"\n")
        fh.truncate(cut + 1)  # cut == -1 (no newline at all) truncates to empty, correctly
        fh.flush()
        os.fsync(fh.fileno())
    print(f"[ledger] truncated an incomplete final line in {path} ({size - cut - 1} bytes)")


def _append_ledger_rows(path: Path, rows: list[dict]) -> None:
    """Append-mode, flush + fsync per row batch (`coding_rules.md`'s atomic-write rule does not
    apply here -- §5: rewriting an append-only ledger to add a row is the failure mode the format
    exists to avoid).

    **A torn tail is truncated back to its last newline first, and that is the one sanctioned
    rewrite of this file** (§5). It removes only bytes that were never a complete row. Appending
    straight onto a torn line instead is not a smaller fix but a fatal one, and it was measured:
    the concatenation is still the *trailing* line, so `_read_ledger_lines` drops it and the whole
    run's output vanishes silently; the append after that makes it a malformed **interior** line
    and every later fold raises. One torn write would brick the ledger permanently, and
    `VISION.md` calls losing or corrupting it unacceptable.
    """
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    _truncate_torn_tail(path)
    with open(path, "a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(_clean_row(row), sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


# ---------------------------------------------------------------------------
# Building the rows this run wants to append
# ---------------------------------------------------------------------------


def _signal_row(row: pd.Series) -> dict:
    data = row.to_dict()
    data.pop("event", None)
    return {"kind": "signal", "timestamp": data.get("signal_ts"), **data}


def _suppressed_row(row: pd.Series, *, instrument: str, type_: SignalType) -> dict:
    data = row.to_dict()
    return {
        "kind": "suppressed",
        "timestamp": data.get("ts"),
        "source": SOURCE,
        "instrument": instrument,
        "type": str(type_),
        "pos": data.get("pos"),
        "direction": data.get("direction"),
        "blocked_by": data.get("blocked_by"),
    }


def _break_even_row(row: pd.Series, *, instrument: str, type_: SignalType) -> dict:
    data = row.to_dict()
    return {
        "kind": "break_even",
        "timestamp": data.get("ts"),
        "source": SOURCE,
        "instrument": instrument,
        "type": str(type_),
        "pos": data.get("pos"),
        "direction": data.get("direction"),
        "signal_id": data.get("signal_id"),
    }


def _outcome_row(row: pd.Series, *, instrument: str, type_: SignalType) -> dict:
    data = row.to_dict()
    timestamp = data.get("exit_ts")
    if timestamp is None or pd.isna(timestamp):
        timestamp = data.get("fill_ts")  # ambiguous: no exit_ts -- fall back to the fill bar
    return {
        "kind": "outcome",
        "timestamp": timestamp,
        "source": SOURCE,
        "instrument": instrument,
        "type": str(type_),
        "signal_id": data.get("signal_id"),
        "outcome": data.get("outcome"),
        "exit_ts": data.get("exit_ts"),
        "exit_price": data.get("exit_price"),
        "bars_held": data.get("bars_held"),
        "r_realized": data.get("r_realized"),
        "flags": data.get("flags"),
    }


# ---------------------------------------------------------------------------
# The report -- docs/PHASE7.md §8. Counts and named rows only, never an aggregate of r_realized.
# ---------------------------------------------------------------------------


def render_report(
    *,
    params: dict[str, object],
    outcomes: pd.DataFrame,
    instrument: str,
    type_: SignalType,
    n_bars: int,
) -> str:
    lines: list[str] = ["# Phase 7 — forward test", ""]
    lines.append("Design: `docs/PHASE7.md`. Generated by `scripts/forward_test.py`.")
    lines.append(
        "**Counts per outcome class, never a verdict** (`CLAUDE.md`). This file reports counts "
        "and names rows only -- no aggregate of `r_realized` appears anywhere below; that "
        "measurement is Phase 9's, not this file's."
    )
    lines.append("")

    lines.append("## Run parameters")
    lines.append("")
    lines.append("| | |")
    lines.append("|---|---|")
    for key, value in params.items():
        lines.append(f"| {key} | `{value}` |")
    lines.append("")

    lines.append(f"## Counts per outcome class -- {instrument}, {type_}")
    lines.append("")
    lines.append("| outcome | count |")
    lines.append("|---|---|")
    counts = outcomes["outcome"].value_counts() if len(outcomes) else pd.Series(dtype="int64")
    for outcome in Outcome:
        lines.append(f"| {outcome} | {int(counts.get(outcome, 0))} |")
    lines.append(f"| **total** | **{len(outcomes)}** |")
    lines.append("")

    lines.append("## Ambiguous rows")
    lines.append("")
    ambiguous = outcomes[outcomes["outcome"] == Outcome.AMBIGUOUS]
    if ambiguous.empty:
        lines.append("None.")
    else:
        lines.append(
            "`exit_pos`/`exit_ts` are `None` by `stoic.tracking`'s own design (§2: the trade "
            "closed, the level is unknown) -- the fill bar is named as reference context instead."
        )
        lines.append("")
        lines.append("| signal_id | direction | fill_ts (entry bar) | why |")
        lines.append("|---|---|---|---|")
        for _, row in ambiguous.iterrows():
            why = ", ".join(str(f) for f in row["flags"]) or "(no flag recorded)"
            lines.append(
                f"| `{row['signal_id']}` | {row['direction']} | `{row['fill_ts']}` | {why} |"
            )
    lines.append("")

    lines.append("## Flagged rows (`gap_beyond_tp1`, `resolved_on_1m`, `flatten_5m_fallback`)")
    lines.append("")
    flagged = outcomes[
        outcomes["flags"].apply(lambda fs: any(f in _FLAGGED_KINDS for f in fs))
    ]
    if flagged.empty:
        lines.append("None.")
    else:
        lines.append("| signal_id | outcome | exit_ts | exit_price | flags |")
        lines.append("|---|---|---|---|---|")
        for _, row in flagged.iterrows():
            flags = ", ".join(str(f) for f in row["flags"])
            lines.append(
                f"| `{row['signal_id']}` | {row['outcome']} | `{row['exit_ts']}` | "
                f"{row['exit_price']} | {flags} |"
            )
    lines.append("")

    lines.append("## Open trades carried forward")
    lines.append("")
    open_trades = outcomes[outcomes["outcome"] == Outcome.OPEN]
    if open_trades.empty:
        lines.append("None.")
    else:
        lines.append("| signal_id | direction | fill_ts | age (bars) |")
        lines.append("|---|---|---|---|")
        for _, row in open_trades.iterrows():
            age = (n_bars - 1) - int(row["fill_pos"])
            lines.append(
                f"| `{row['signal_id']}` | {row['direction']} | `{row['fill_ts']}` | {age} |"
            )
    lines.append("")

    return "\n".join(lines) + "\n"


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 7 forward-test harness")
    parser.add_argument("--instrument", required=True, choices=["NQ", "ES"])
    parser.add_argument(
        "--type", required=True, dest="type_", choices=[t.value for t in SignalType]
    )
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--bars-path", default=None, type=Path)
    parser.add_argument("--ledger-home", default=None, type=Path)
    parser.add_argument("--report", default=None, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    started = time.monotonic()
    args = _parse_args(argv)

    instrument = args.instrument
    type_ = SignalType(args.type_)
    spec = TYPE_SPECS[type_]
    if spec.setup_tf != TIMEFRAME:
        print(
            f"[error] --type {type_} runs on setup_tf={spec.setup_tf!r}, but this driver always "
            f"resamples to {TIMEFRAME!r} (see module docstring) -- not supported, refusing to run"
        )
        return 1

    bars_path = args.bars_path or (REPO / "data" / "historical" / f"{instrument}_1m.parquet")
    ledger_home = (
        args.ledger_home
        or (Path(os.environ["STOIC_LEDGER_HOME"]) if "STOIC_LEDGER_HOME" in os.environ else None)
        or DEFAULT_LEDGER_HOME
    )
    report_path = args.report or default_report_path(instrument, str(type_))
    ledger_path = ledger_home / f"{type_}.jsonl"

    if not bars_path.exists():
        print(f"[error] bars file not found: {bars_path}")
        return 1

    stage = time.monotonic()
    minute_bars_full = pd.read_parquet(bars_path)
    bars_5m_full = resample(minute_bars_full, "5m")
    print(
        f"[load] {len(minute_bars_full)} 1m bars from {bars_path} "
        f"({time.monotonic() - stage:.1f}s)"
    )

    bars_5m = bars_5m_full.loc[args.start : args.end]
    minute_bars = minute_bars_full.loc[args.start : args.end]
    if len(bars_5m) == 0:
        print(f"[error] no 5m bars in [{args.start}, {args.end}]")
        return 1
    print(f"[slice] {len(bars_5m)} 5m bars, {bars_5m.index[0]} -> {bars_5m.index[-1]}")

    frame_start = bars_5m.index[0]
    frame_key = (instrument, TIMEFRAME)

    fold = fold_ledger(ledger_path)

    if frame_key in fold.frame_starts:
        pinned = fold.frame_starts[frame_key]
        if pinned != frame_start:
            print(
                f"[gate] frame start disagreement for {instrument}/{TIMEFRAME}: ledger has "
                f"{pinned.isoformat()}, this run requested {frame_start.isoformat()} -- a "
                "disagreement is a bug in the request, refusing to run"
            )
            return 1

    watermark_key = (instrument, TIMEFRAME, str(type_))
    prior_watermark = fold.watermarks.get(watermark_key)
    prior_bar_count = (
        int(bars_5m.index.searchsorted(prior_watermark, side="right"))
        if prior_watermark is not None
        else 0
    )
    new_bar_count = len(bars_5m) - prior_bar_count
    print(
        f"[progress] bars: {len(bars_5m)} total, {prior_bar_count} already recorded, "
        f"{new_bar_count} new this run"
    )

    stage = time.monotonic()
    bars_5m = add_smas(bars_5m)
    bars_5m = attach_parent_pos(bars_5m)
    judgment = decided_judgment()
    print(f"[prep] indicators + structure ({time.monotonic() - stage:.1f}s)")

    stage = time.monotonic()
    sequence_events = sequence_replay(bars_5m, judgment)
    print(f"[L2] {len(sequence_events)} sequence events ({time.monotonic() - stage:.1f}s)")

    stage = time.monotonic()
    emissions = replay_signals(bars_5m, judgment, instrument=instrument, type_=type_, htf=None)
    print(
        f"[L5] {len(emissions)} emission rows "
        f"{ {str(k): int(v) for k, v in emissions['event'].value_counts().items()} } "
        f"({time.monotonic() - stage:.1f}s)"
    )

    stage = time.monotonic()
    outcomes = track_outcomes(
        bars_5m,
        emissions=emissions,
        sequence_events=sequence_events,
        minute_bars=minute_bars,
        type_=type_,
    )
    print(f"[tracking] {len(outcomes)} tracked signals ({time.monotonic() - stage:.1f}s)")

    signal_rows = [
        _signal_row(row)
        for _, row in emissions.loc[emissions["event"] == EmissionEvent.SIGNAL].iterrows()
        if row["signal_id"] not in fold.known_signal_ids
    ]
    suppressed_rows = [
        _suppressed_row(row, instrument=instrument, type_=type_)
        for _, row in emissions.loc[emissions["event"] == EmissionEvent.SUPPRESSED].iterrows()
        if (instrument, int(row["pos"]), str(row["direction"]))
        not in fold.known_suppressed_keys
    ]
    break_even_rows = [
        _break_even_row(row, instrument=instrument, type_=type_)
        for _, row in emissions.loc[emissions["event"] == EmissionEvent.BREAK_EVEN].iterrows()
        if (instrument, int(row["pos"]), str(row["direction"]), str(row["signal_id"]))
        not in fold.known_break_even_keys
    ]
    outcome_rows = [
        _outcome_row(row, instrument=instrument, type_=type_)
        for _, row in outcomes.iterrows()
        if row["outcome"] != Outcome.OPEN and row["signal_id"] not in fold.closed_signal_ids
    ]

    print(
        f"[ledger] new this run: {len(signal_rows)} signal, {len(suppressed_rows)} suppressed, "
        f"{len(break_even_rows)} break_even, {len(outcome_rows)} outcome"
    )

    if args.dry_run:
        print("[dry-run] nothing written")
        print(render_report(
            params=_report_params(args, instrument, type_, bars_path, ledger_path, frame_start,
                                   len(bars_5m)),
            outcomes=outcomes,
            instrument=instrument,
            type_=type_,
            n_bars=len(bars_5m),
        ))
        print(f"[done] {time.monotonic() - started:.1f}s (dry-run)")
        return 0

    new_rows: list[dict] = []
    if not ledger_path.exists():
        new_rows.append({"kind": "header", "schema": 1, "type": str(type_)})
    if frame_key not in fold.frame_starts:
        new_rows.append(
            {
                "kind": "frame",
                "instrument": instrument,
                "timeframe": TIMEFRAME,
                "frame_start": frame_start,
            }
        )
    new_rows.extend(signal_rows)
    new_rows.extend(suppressed_rows)
    new_rows.extend(break_even_rows)
    new_rows.extend(outcome_rows)
    # Only when something else was appended: a no-op rerun must append nothing, or the file grows
    # without bound and "this run appended nothing" stops being literally true.
    if new_rows:
        new_rows.append(
            {
                "kind": "watermark",
                "instrument": instrument,
                "timeframe": TIMEFRAME,
                "type": str(type_),
                "last_bar_ts": bars_5m.index[-1],
            }
        )
    _append_ledger_rows(ledger_path, new_rows)
    print(f"[ledger] {ledger_path} <- {len(new_rows)} rows")

    report_text = render_report(
        params=_report_params(args, instrument, type_, bars_path, ledger_path, frame_start,
                               len(bars_5m)),
        outcomes=outcomes,
        instrument=instrument,
        type_=type_,
        n_bars=len(bars_5m),
    )
    _write_atomic(report_path, report_text)
    print(f"[report] {report_path}")

    print(f"[done] {time.monotonic() - started:.1f}s")
    return 0


def _report_params(
    args: argparse.Namespace,
    instrument: str,
    type_: SignalType,
    bars_path: Path,
    ledger_path: Path,
    frame_start: pd.Timestamp,
    n_bars: int,
) -> dict[str, object]:
    return {
        "instrument": instrument,
        "type": type_,
        "start": args.start,
        "end": args.end,
        "bars_path": bars_path,
        "ledger_path": ledger_path,
        "frame_start": frame_start,
        "bars": n_bars,
        "judgment": "decided_judgment() -- D-29, D-30, D-34 defaults",
        "htf": "None",
    }


if __name__ == "__main__":
    raise SystemExit(main())
