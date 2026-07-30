"""Combine the historical bar sources under data/historical into one canonical set.

Two sources feed the same series, in different shapes:

* ``needs_normalization/{ES,NQ}_{1m,1h}.parquet`` — Databento OHLCV-1m / OHLCV-1h bars for the
  volume-continuous front month (``ES.v.0`` / ``NQ.v.0``), 2019-06-10 .. 2026-06-08. This is the
  spine; it is already bars, so it is only reshaped, never recomputed.
* ``GLBX.MDP3__*.trades.dbn.zst`` — raw trades. Only the tail pull extends past the spine, so only
  the tail is aggregated. The two big pulls sit entirely inside the spine's range and would add
  zero bars; see the module docstring in git history / the run report for the coverage table.

Where the tail overlaps the spine, aggregating it is a *check*, not an input: the overlapping bars
must match Databento's own OHLCV bars, and any mismatch is reported and fails the run. Only bars
strictly after the spine's last timestamp are appended.

Output: ``data/historical/{ES,NQ}_{1m,1h}.parquet``, UTC, ts_event = bar start, one row per bar.

The script is idempotent — it reads only immutable inputs and rewrites the outputs atomically, so
re-running it reproduces the same files. It takes well under a minute, so there is nothing to
resume; progress and per-stage timings are printed as it goes.

The ``needs_normalization/`` spine is not kept in the working tree: the outputs are verified
supersets of it, so holding both would duplicate ~85 MB for nothing. It is archived in git and can
be restored when this script needs to run again::

    mkdir -p data/historical/needs_normalization
    for f in ES_1h ES_1m NQ_1h NQ_1m; do
        git show "6e06f71:data/historical/needs_normalization/$f.parquet" \
            > "data/historical/needs_normalization/$f.parquet"
    done
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import databento as db
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = REPO_ROOT / "data" / "historical"
SPINE_DIR = HISTORICAL / "needs_normalization"

TAIL_TRADES = HISTORICAL / "GLBX.MDP3__NQ__2026-06-06__2026-06-10T16:45:00.trades.dbn.zst"

PRICE_SCALE = 1_000_000_000  # Databento fixed-point prices are 1e-9 units.
OHLC = ("open", "high", "low", "close")

# Bar-start label -> pandas floor frequency. Databento labels OHLCV bars by their opening minute.
TIMEFRAMES = {"1m": "1min", "1h": "1h"}

SOURCE_OHLCV = "databento-ohlcv"
SOURCE_TRADES = "databento-trades-agg"

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


def _finalize(frame: pd.DataFrame, source: str) -> pd.DataFrame:
    """Apply the canonical column set, dtypes and index to a normalized frame."""
    frame = frame.assign(source=source)
    frame = frame[COLUMNS].astype(DTYPES)
    frame.index.name = "ts_event"
    return frame.sort_index()


def load_spine(symbol: str, timeframe: str) -> pd.DataFrame:
    """Load a Databento OHLCV parquet as-is, dropping only the redundant rtype column."""
    path = SPINE_DIR / f"{symbol}_{timeframe}.parquet"
    frame = pd.read_parquet(path)
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError(f"{path}: expected a tz-aware DatetimeIndex of bar starts")
    return _finalize(frame, SOURCE_OHLCV)


def aggregate_trades(path: Path, timeframe: str) -> pd.DataFrame:
    """Aggregate a trades DBN file into bars, matching Databento's OHLCV construction.

    Bars are keyed by **``ts_recv``** — gateway receive time — floored to the timeframe, not by
    ``ts_event``. This is not a stylistic choice: it is what Databento's own OHLCV bars do, and it
    is the difference between a splice that agrees with the spine and one that does not. Bucketing
    the overlap day by ``ts_event`` mismatches 14 of 1380 one-minute bars, always as adjacent
    +n/-n volume pairs, because a burst of trades stamped ``ts_event 19:29:59.9996`` arrives at
    ``ts_recv 19:30:00.0001`` and Databento counts it in the 19:30 bar. Bucketing by ``ts_recv``
    mismatches none. ``check_overlap`` re-proves this on every run.

    open/close are taken in (ts_recv, sequence) order so the result does not depend on how the
    file happened to be written.
    """
    store = db.DBNStore.from_file(path)
    if store.metadata.schema != "trades":
        raise ValueError(f"{path}: expected the trades schema, got {store.metadata.schema}")

    # to_df indexes by ts_recv; make it an ordinary column so it can be sorted and floored.
    trades = store.to_df(price_type="fixed").reset_index()
    unexpected = set(trades["action"].unique()) - {"T"}
    if unexpected:
        raise ValueError(f"{path}: unexpected non-trade actions {sorted(unexpected)}")

    trades = trades.sort_values(["ts_recv", "sequence"], kind="stable")
    trades["price"] = trades["price"] / PRICE_SCALE
    trades["bar"] = trades["ts_recv"].dt.floor(TIMEFRAMES[timeframe])

    bars = trades.groupby("bar", sort=True).agg(
        symbol=("symbol", "last"),
        instrument_id=("instrument_id", "last"),
        publisher_id=("publisher_id", "last"),
        open=("price", "first"),
        high=("price", "max"),
        low=("price", "min"),
        close=("price", "last"),
        volume=("size", "sum"),
    )
    return _finalize(bars, SOURCE_TRADES)


@dataclass(frozen=True)
class OverlapCheck:
    """How aggregated trade bars compared against Databento's own bars on the shared range."""

    bars: int
    mismatched: int
    worst: pd.DataFrame

    @property
    def ok(self) -> bool:
        return self.bars > 0 and self.mismatched == 0


def check_overlap(agg: pd.DataFrame, spine: pd.DataFrame) -> OverlapCheck:
    """Compare every bar the two sources share on OHLC and volume."""
    shared = agg.index.intersection(spine.index)
    left, right = agg.loc[shared], spine.loc[shared]
    fields = [*OHLC, "volume"]
    diff = (left[fields].astype("float64") - right[fields].astype("float64")).abs()
    bad = diff[diff.max(axis=1) > 0]
    return OverlapCheck(bars=len(shared), mismatched=len(bad), worst=bad.nlargest(5, "close"))


def combine(spine: pd.DataFrame, extension: pd.DataFrame | None) -> pd.DataFrame:
    """Append the extension bars that start after the spine ends, under the spine's symbol.

    The two pulls used different continuous conventions — the spine is volume-continuous
    (``NQ.v.0``), the tail pull calendar-continuous (``NQ.c.0``) — so the raw labels would make one
    output file carry two symbols. They are relabelled to the spine's symbol, but *only* after
    confirming both resolve to the same ``instrument_id`` at the seam. If a future pull splices
    across a roll, that assumption breaks and the relabel would assert a continuity that does not
    exist, so this raises rather than papering over it. Provenance stays in ``source``.
    """
    if extension is None:
        return spine
    tail = extension[extension.index > spine.index[-1]]
    if tail.empty:
        return spine

    spine_symbol = spine["symbol"].iloc[-1]
    spine_instrument = spine["instrument_id"].iloc[-1]
    seam_instruments = set(tail["instrument_id"].unique())
    if seam_instruments != {spine_instrument}:
        raise ValueError(
            f"refusing to relabel to {spine_symbol}: the spine ends on instrument_id "
            f"{spine_instrument} but the extension covers {sorted(seam_instruments)}. "
            "The splice crosses a contract roll — resolve the continuous series before merging."
        )

    tail = tail.assign(symbol=spine_symbol).astype({"symbol": DTYPES["symbol"]})
    return pd.concat([spine, tail])


def validate(frame: pd.DataFrame, label: str) -> None:
    """Assert the invariants a bar series must hold before it is written."""
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


def describe(frame: pd.DataFrame) -> str:
    by_source = frame["source"].value_counts().to_dict()
    first, last = frame.index[0], frame.index[-1]
    return (
        f"{len(frame):>9,} bars  {first:%Y-%m-%d %H:%M} .. {last:%Y-%m-%d %H:%M}  {by_source}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="run the overlap check and validations without writing any output",
    )
    args = parser.parse_args()

    started = time.perf_counter()
    failures: list[str] = []

    for timeframe in TIMEFRAMES:
        print(f"\n[{timeframe}] aggregating the NQ tail pull")
        with stage(f"{TAIL_TRADES.name} -> {timeframe} bars"):
            extension = aggregate_trades(TAIL_TRADES, timeframe)

        for symbol in ("ES", "NQ"):
            print(f"[{timeframe}] {symbol}")
            with stage("load spine"):
                spine = load_spine(symbol, timeframe)

            # The tail pull is NQ only; ES has no source that reaches past its spine.
            symbol_extension = extension if symbol == "NQ" else None

            if symbol_extension is not None:
                check = check_overlap(symbol_extension, spine)
                verdict = "MATCH" if check.ok else "MISMATCH"
                print(
                    f"    overlap: {check.bars:,} shared bars, "
                    f"{check.mismatched:,} differ [{verdict}]"
                )
                if not check.ok:
                    failures.append(f"{symbol} {timeframe}: overlap check failed")
                    print(check.worst.to_string())

            combined = combine(spine, symbol_extension)
            validate(combined, f"{symbol} {timeframe}")
            print(f"    {describe(combined)}")

            if not args.check_only:
                out = HISTORICAL / f"{symbol}_{timeframe}.parquet"
                with stage(f"write {out.name}"):
                    write_atomic(combined, out)

    print(f"\ntotal {time.perf_counter() - started:.1f}s")
    if failures:
        print("FAILED:\n  " + "\n  ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
