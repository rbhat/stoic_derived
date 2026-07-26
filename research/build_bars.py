"""Build NQ bars for the 2026-H1 research range through the production SP1 path.

Research artifact (ADR-0013), NOT a release. Uses the repo's own calendar,
roll-aware coverage planning, and MultiTimeframeAggregator so the bars carry
the same semantics the live path would produce.

Calendar note: the research manifest declares NO session overrides. That is a
deliberate, asymmetric choice -- omitting a real holiday is benign (the
calendar expects a session, no trades arrive, no bars are emitted), while
asserting a holiday that actually traded would silently delete a real trading
day. Holidays are detected empirically afterwards from per-day volume.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from stoic_derived.market_data.aggregate import AggregationSpec, MultiTimeframeAggregator
from stoic_derived.market_data.calendar import load_calendar_manifest
from stoic_derived.market_data.databento import inspect_dbn, iter_historical_trades, plan_coverage
from stoic_derived.market_data.model import Timeframe

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / ".artifacts/research/bars"
SRC = REPO / "data/historical/GLBX.MDP3__NQ__2026-01-01__2026-06-06.trades.dbn.zst"
MANIFEST = REPO / "config/market_data/calendars/cme-equity-index-2026-h1-research-v1.json"

TIMEFRAMES = (
    Timeframe.ONE_MINUTE,
    Timeframe.FIVE_MINUTES,
    Timeframe.FIFTEEN_MINUTES,
    Timeframe.SIXTY_MINUTES,
    Timeframe.DAILY,
)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    calendar = load_calendar_manifest(MANIFEST)
    coverage = plan_coverage((inspect_dbn(SRC),))
    aggregator = MultiTimeframeAggregator(
        calendar, AggregationSpec(timeframes=TIMEFRAMES, allowed_lateness_ns=0)
    )

    handles = {tf: (OUT / f"NQ_{tf.value}.jsonl").open("w", encoding="utf-8") for tf in TIMEFRAMES}
    counts = dict.fromkeys(TIMEFRAMES, 0)
    issues: list[dict] = []
    events = 0
    started = time.time()

    def emit(batch) -> None:
        for bar in batch.bars:
            handles[bar.timeframe].write(json.dumps(bar.canonical_dict(), sort_keys=True) + "\n")
            counts[bar.timeframe] += 1
        for issue in batch.issues:
            issues.append({"code": str(getattr(issue, "code", issue)), "detail": str(issue)})

    for event in iter_historical_trades(coverage):
        events += 1
        emit(aggregator.push(event))
        if events % 1_000_000 == 0:
            rate = events / max(time.time() - started, 1e-9)
            print(
                f"[build_bars] events={events:,} rate={rate:,.0f}/s "
                f"elapsed={time.time() - started:,.0f}s bars_1m={counts[Timeframe.ONE_MINUTE]:,} "
                f"issues={len(issues)}",
                flush=True,
            )
    emit(aggregator.finish())

    for handle in handles.values():
        handle.close()

    summary = {
        "events": events,
        "elapsed_s": round(time.time() - started, 1),
        "bars": {tf.value: counts[tf] for tf in TIMEFRAMES},
        "issue_count": len(issues),
        "issues_sample": issues[:20],
        "calendar_version": calendar.version,
        "calendar_fingerprint": calendar.fingerprint,
        "source": SRC.as_posix(),
    }
    (OUT / "build_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    print("[build_bars] DONE", json.dumps(summary["bars"]), f"events={events:,}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
