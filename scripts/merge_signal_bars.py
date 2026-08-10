"""Extend data/historical/{NQ,ES}_1m.parquet forward using the live signal system's capture.

Source: ``/Users/rajeev/dev/trading_signal/data/signals.db``, table ``bars``, columns ``symbol,
ts_event, open, high, low, close, volume, interval_s, buy_vol, sell_vol``. Only ``interval_s = 60``
rows are used; ``symbol`` is ``'NQ'`` or ``'ES'``; ``ts_event`` is INTEGER nanoseconds since epoch
UTC and is the **bar start**, the same convention our parquet uses — converted with
``pd.to_datetime(ts_event, unit="ns", utc=True)``. Only ``open, high, low, close, volume`` are
taken; ``buy_vol``/``sell_vol``/``id``/``interval_s`` are ignored (see
``claude_memories/databento-ohlcv-buckets-by-ts-recv.md`` for why a live capture's own volume split
is not treated as a bar field here).

**Our parquet is authoritative on the overlap.** Only bars strictly after the existing file's last
timestamp are appended; an existing bar is never overwritten. The overlap comparison is a *reported
check, not an input* — unlike ``normalize_historical_bars.py``'s tail check against Databento's own
OHLCV bars, a mismatch here is expected and does not fail the run: ``signals.db`` is a live capture,
known lossy (feed dropouts, bring-up gaps), not a second vendor truth. Every mismatching bar is
printed with both readings.

Column conformance: appended rows match the existing files' column set and dtypes exactly.
``symbol`` is carried through as the *existing file's* symbol (e.g. ``NQ.v.0``) rather than
``signals.db``'s bare ``NQ`` — ``signals.db`` has no continuous-contract convention, and switching
labels mid-series would misrepresent the roll convention ``normalize_historical_bars.py`` is careful
to preserve. ``instrument_id``/``publisher_id`` are not present in ``signals.db`` at all; appended
rows get the sentinels ``UINT32_MAX`` / ``UINT16_MAX`` (dtype-max, not ``0``, since ``0`` is not
reserved and a real id could plausibly be small) — chosen over pandas nullable ints so the columns
keep the existing files' plain ``uint32``/``uint16`` dtype and round-trip through parquet unchanged.
``source`` is set to ``"signals_db"`` so provenance stays visible.

Idempotent: reads only immutable inputs (the parquet files are read-only to this script;
``signals.db`` is a live-appended log but only its already-committed rows as of the read are used)
and rewrites output atomically (temp file + replace). Re-running with no new rows in ``signals.db``
reproduces the same files byte-for-byte. Takes seconds; per-stage timings are printed as it goes.

2026-06-11 .. 2026-06-19 is a known ragged hole in ``signals.db``'s own bring-up (see
``docs/PHASE3.md`` section 1) — expected, not a bug in this script.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = REPO_ROOT / "data" / "historical"
ARTIFACTS = REPO_ROOT / ".artifacts"
REPORT_PATH = ARTIFACTS / "merge_signal_bars_report.md"

# stoic lives at the repo root; running this file directly puts only scripts/ on sys.path.
sys.path.insert(0, str(REPO_ROOT))

from stoic.sessions import session_date  # noqa: E402

# The capture lives outside this repo and at a different path on each machine, so it is config, not
# a constant: $STOIC_SIGNALS_DB wins, then --db, then this Mac default (VISION.md's portability
# contract — pathlib only, config via env vars, no hardware assumptions).
SIGNALS_DB = Path(
    os.environ.get("STOIC_SIGNALS_DB", "/Users/rajeev/dev/trading_signal/data/signals.db")
)

SYMBOLS = ("NQ", "ES")
OHLC = ("open", "high", "low", "close")
OHLCV = (*OHLC, "volume")

SOURCE_SIGNALS_DB = "signals_db"

# Sentinels for columns signals.db does not carry, chosen to round-trip through the existing files'
# plain (non-nullable) uint32/uint16 dtypes. Dtype-max rather than 0: 0 is not a reserved id in the
# data observed so far (min instrument_id seen is 118), while UINT32_MAX/UINT16_MAX cannot collide
# with any real Databento id in this dataset (max seen is ~42.3M, far below 2**32-1).
INSTRUMENT_ID_SENTINEL = 2**32 - 1
PUBLISHER_ID_SENTINEL = 2**16 - 1

COLUMNS = [
    "symbol",
    "instrument_id",
    "publisher_id",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
]

DTYPES = {
    "symbol": "string",
    "instrument_id": "uint32",
    "publisher_id": "uint16",
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "volume": "uint64",
    "source": "string",
}


@contextmanager
def stage(label: str) -> Iterator[None]:
    """Print a stage banner and how long it took."""
    print(f"  {label} ... ", end="", flush=True)
    started = time.perf_counter()
    yield
    print(f"done in {time.perf_counter() - started:.1f}s")


def load_existing(symbol: str) -> pd.DataFrame:
    """Load the existing parquet as-is. This is the spine: authoritative on the overlap."""
    path = HISTORICAL / f"{symbol}_1m.parquet"
    frame = pd.read_parquet(path)
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError(f"{path}: expected a tz-aware DatetimeIndex of bar starts")
    if list(frame.columns) != COLUMNS:
        raise ValueError(f"{path}: unexpected column set {list(frame.columns)}, expected {COLUMNS}")
    return frame.sort_index()


def load_signals_db(symbol: str, db_path: Path) -> pd.DataFrame:
    """Load 1-minute bars for `symbol` from the live signal system's SQLite capture.

    interval_s = 60 only. ts_event (ns since epoch UTC, bar start) becomes the index, matching our
    parquet convention. Only open/high/low/close/volume are taken.
    """
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        raw = pd.read_sql_query(
            "SELECT ts_event, open, high, low, close, volume FROM bars "
            "WHERE symbol = ? AND interval_s = 60",
            con,
            params=(symbol,),
        )
    finally:
        con.close()

    raw["ts_event"] = pd.to_datetime(raw["ts_event"], unit="ns", utc=True)
    raw = raw.set_index("ts_event").sort_index()
    raw.index.name = "ts_event"
    raw["volume"] = raw["volume"].astype("uint64")
    return raw[list(OHLCV)]


@dataclass(frozen=True)
class OverlapCheck:
    """How signals.db's bars compare against our existing (authoritative) bars, over the overlap.

    `mismatched` counts a bar if *any* of the 5 fields differ (volume included) — that is the
    population in `all_mismatches`, per rule 2 of the spec. `ohlc_mismatched` is the narrower count
    of bars where open/high/low/close differ (volume excluded); volume disagrees on essentially
    every bar for a live capture (partial trade attribution is expected — see
    claude_memories/databento-ohlcv-buckets-by-ts-recv.md), so OHLC-only is the meaningful figure
    for judging price-data fidelity and is what's reported alongside the full count.
    """

    bars: int
    mismatched: int
    ohlc_mismatched: int
    field_counts: dict[str, int]
    all_mismatches: pd.DataFrame


def check_overlap(source: pd.DataFrame, existing: pd.DataFrame) -> OverlapCheck:
    """Compare every bar the two sources share on OHLCV. Informational only, never fails the run."""
    shared = source.index.intersection(existing.index)
    left, right = source.loc[shared], existing.loc[shared]

    diffs = {}
    any_diff = pd.Series(False, index=shared)
    ohlc_diff = pd.Series(False, index=shared)
    for field in OHLCV:
        d = (left[field].astype("float64") - right[field].astype("float64")).abs()
        mismatched = d > 0
        diffs[field] = mismatched
        any_diff = any_diff | mismatched
        if field in OHLC:
            ohlc_diff = ohlc_diff | mismatched

    field_counts = {field: int(diffs[field].sum()) for field in OHLCV}

    bad_index = shared[any_diff]
    rows = []
    for field in OHLCV:
        rows.append(left.loc[bad_index, field].rename(f"signals_db_{field}"))
        rows.append(right.loc[bad_index, field].rename(f"existing_{field}"))
    all_mismatches = pd.concat(rows, axis=1).sort_index() if len(bad_index) else pd.DataFrame()

    return OverlapCheck(
        bars=len(shared),
        mismatched=int(any_diff.sum()),
        ohlc_mismatched=int(ohlc_diff.sum()),
        field_counts=field_counts,
        all_mismatches=all_mismatches,
    )


def build_extension(source: pd.DataFrame, existing: pd.DataFrame) -> pd.DataFrame:
    """Bars from `source` strictly after `existing`'s last timestamp, conformed to its columns."""
    tail = source[source.index > existing.index[-1]].copy()
    if tail.empty:
        return tail

    tail["symbol"] = existing["symbol"].iloc[-1]
    tail["instrument_id"] = INSTRUMENT_ID_SENTINEL
    tail["publisher_id"] = PUBLISHER_ID_SENTINEL
    tail["source"] = SOURCE_SIGNALS_DB
    tail = tail[COLUMNS].astype(DTYPES)
    tail.index.name = "ts_event"
    return tail


def combine(existing: pd.DataFrame, extension: pd.DataFrame) -> pd.DataFrame:
    if extension.empty:
        return existing
    return pd.concat([existing, extension])


def validate(frame: pd.DataFrame, label: str) -> None:
    """Assert the invariants a bar series must hold (mirrors normalize_historical_bars.validate)."""
    if frame.index.has_duplicates:
        raise ValueError(f"{label}: duplicate bar timestamps")
    if not frame.index.is_monotonic_increasing:
        raise ValueError(f"{label}: bar timestamps are not sorted")
    bad = frame[
        (frame["high"] < frame["low"])
        | (frame["open"] > frame["high"])
        | (frame["open"] < frame["low"])
        | (frame["close"] > frame["high"])
        | (frame["close"] < frame["low"])
    ]
    if not bad.empty:
        raise ValueError(f"{label}: {len(bad)} bars violate low <= open,close <= high")
    if (frame["volume"] == 0).any():
        raise ValueError(f"{label}: bars with zero volume")
    symbols = frame["symbol"].unique()
    if len(symbols) != 1:
        raise ValueError(f"{label}: expected one symbol per file, got {sorted(symbols)}")


def write_atomic(frame: pd.DataFrame, path: Path) -> None:
    """Write the parquet via a temp file so an interrupted run never leaves a partial output."""
    tmp = path.with_suffix(".parquet.tmp")
    frame.to_parquet(tmp, compression="zstd")
    tmp.replace(path)


def coverage_report(symbol: str, extension: pd.DataFrame) -> pd.DataFrame:
    """1m bar count per CME trading day for every session the extension touches."""
    if extension.empty:
        return pd.DataFrame(columns=["session_date", "bars"])
    sd = session_date(extension.index)
    counts = sd.value_counts().sort_index()
    return pd.DataFrame({"session_date": counts.index, "bars": counts.to_numpy()})


def describe(frame: pd.DataFrame) -> str:
    by_source = frame["source"].value_counts().to_dict()
    first, last = frame.index[0], frame.index[-1]
    return f"{len(frame):>9,} bars  {first} .. {last}  {by_source}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="do everything except write the output parquet files",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=SIGNALS_DB,
        help=f"path to signals.db (default: {SIGNALS_DB})",
    )
    args = parser.parse_args()

    if not args.db.exists():
        print(f"signals.db not found at {args.db}", file=sys.stderr)
        return 1

    started = time.perf_counter()
    report_lines: list[str] = [
        "# merge_signal_bars.py run report",
        "",
        f"signals.db: `{args.db}`",
        f"dry-run: {args.dry_run}",
        "",
    ]

    for symbol in SYMBOLS:
        print(f"\n[{symbol}]")
        report_lines.append(f"## {symbol}")

        with stage("load existing parquet"):
            existing = load_existing(symbol)
        print(f"    existing: {describe(existing)}")
        report_lines.append(f"- existing: {describe(existing)}")

        with stage("load signals.db"):
            source = load_signals_db(symbol, args.db)
        print(f"    signals.db: {len(source):,} bars  {source.index[0]} .. {source.index[-1]}")
        report_lines.append(
            f"- signals.db: {len(source):,} bars  {source.index[0]} .. {source.index[-1]}"
        )

        with stage("overlap check (informational)"):
            check = check_overlap(source, existing)
        print(
            f"    overlap: {check.bars:,} shared bars, {check.mismatched:,} differ on any of "
            f"OHLCV, {check.ohlc_mismatched:,} differ on OHLC (volume excluded)"
        )
        print(f"    mismatch count by field: {check.field_counts}")
        report_lines.append(
            f"- overlap: {check.bars:,} shared bars, {check.mismatched:,} differ on any of OHLCV, "
            f"{check.ohlc_mismatched:,} differ on OHLC (volume excluded)"
        )
        report_lines.append(f"- mismatch count by field: {check.field_counts}")
        if check.mismatched:
            print("    mismatching bars (signals_db vs existing):")
            print(check.all_mismatches.to_string())
            report_lines.append("")
            report_lines.append("Mismatching bars (signals_db vs existing):")
            report_lines.append("")
            report_lines.append("```")
            report_lines.append(check.all_mismatches.to_string())
            report_lines.append("```")

        with stage("build extension"):
            extension = build_extension(source, existing)
        print(f"    extension: {len(extension):,} new bars")
        report_lines.append(f"- extension: {len(extension):,} new bars")
        if not extension.empty:
            print(f"      {extension.index[0]} .. {extension.index[-1]}")
            report_lines.append(f"  - {extension.index[0]} .. {extension.index[-1]}")

        cov = coverage_report(symbol, extension)
        if not cov.empty:
            print("    per-session 1m bar coverage for appended sessions:")
            print(cov.to_string(index=False))
            report_lines.append("")
            report_lines.append("Per-session 1m bar coverage for appended sessions:")
            report_lines.append("")
            report_lines.append("```")
            report_lines.append(cov.to_string(index=False))
            report_lines.append("```")

        with stage("combine + validate"):
            combined = combine(existing, extension)
            validate(combined, f"{symbol} 1m")
        print(f"    combined: {describe(combined)}")
        report_lines.append(f"- combined: {describe(combined)}")

        if not args.dry_run:
            out = HISTORICAL / f"{symbol}_1m.parquet"
            with stage(f"write {out.name}"):
                write_atomic(combined, out)
        report_lines.append("")

    elapsed = time.perf_counter() - started
    print(f"\ntotal {elapsed:.1f}s")
    report_lines.append(f"total: {elapsed:.1f}s")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    tmp = REPORT_PATH.with_suffix(".md.tmp")
    tmp.write_text("\n".join(report_lines) + "\n")
    tmp.replace(REPORT_PATH)
    print(f"report written to {REPORT_PATH}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
