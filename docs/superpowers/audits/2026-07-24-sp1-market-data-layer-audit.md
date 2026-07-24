# SP1 Market Data Layer Audit

- Date: 2026-07-24
- Result: PASS
- Scope: SP1 historical/live normalization, calendars, aggregation, CLI, and
  portable tests

## Vision and Boundary Review

- `VISION.md` is unchanged and unstaged.
- The market-data package has no strategy, education, model, broker,
  execution, ledger, or backtest dependency.
- Backtesting consumes the same immutable bars and remains parallel and
  non-gating for live processing.
- SP1 does not enable live signals. SP0 still blocks them until the exact
  strategy rulebook and human approval are complete.

## Determinism and Safety Review

- Historical and live-shaped records normalize to the same canonical trade.
- Prices remain exact integer 0.25-point ticks; source record multiplicity is
  preserved.
- Equal event timestamps use venue sequence, receive timestamp, then canonical
  bytes, producing arrival-independent OHLC and bar identities.
- Provider heartbeat/replay progress can finalize quiet bars without wall
  clock access.
- Events behind a trusted watermark, after finalization, or after an explicit
  contract close are quarantined.
- SDK automatic reconnect is disabled. Explicit reconnect retains durable
  timestamp/count cursors, replays older unacknowledged work, and retires stale
  post-roll cursors.
- Skipped-record gaps halt the live session. Roll resubscription refuses to
  discard unacknowledged old-contract trades.
- Calendar publication requires a strict committed manifest. The checked-in
  June-tail and current July-live bundles have reviewed, fingerprinted
  coverage and CME provenance. Unprovenanced or out-of-range dates fail closed;
  the wider holiday-bearing historical range is intentionally unavailable
  until its schedule bundle is reviewed.
- Historical overlap uses input-order-independent
  `widest-coverage-then-path/v1`; individual records are never deduplicated.

## Actual Data Evidence

The three local DBN v1 sources inspect as `GLBX.MDP3` trades with continuous
input and instrument-ID output. Coverage planning selects:

- ES and NQ from the 2025-09-01 to 2026-06-06 main file;
- NQ from the contiguous 2026-06-06 tail;
- no records from the wholly contained NQ January-June file.

A 100,000-record NQ-tail replay was run twice:

- event SHA-256:
  `1951274be0ba7fd5b923ca80a859f97b079233ac81ff93938e3fc3e090c6caae`;
- canonical bar SHA-256:
  `881464876467570543941057b2d4efa04c3d8bde8c30a76f66b562565e591653`;
- 647 bars across 1m, 5m, 15m, 60m, D, and W;
- 641 complete bars and six expected degraded end-of-sample bars;
- zero quality issues;
- all 501 one-minute bars matched an independent order-aware OHLCV/count
  oracle;
- bounded state: zero reorder backlog, six open builders, approximately
  128 MiB peak RSS on macOS.

## Verification

```text
uv run pytest -q
115 passed, 1 skipped

STOIC_RUN_DBN_SMOKE=1 uv run pytest -q tests/market_data/test_databento.py
13 passed

uv run ruff format --check src tests
18 files already formatted

uv run ruff check src tests
All checks passed

uv run mypy src tests/market_data
Success: no issues found in 17 source files

uv lock --check
Resolved 64 packages

git diff --check
passed
```

Two independent Terra reviews passed the portable, adversarial, actual-data,
and resource-bound checks. The Sol architecture audit reproduced the original
recovery, roll, watermark, ordering, and calendar failure modes, then verified
their fixes.

No credentialed live network session was opened during SP1. Live provider
behavior is covered through a strict injectable adapter and official Databento
timestamp/count, system-progress, mapping, and error contracts.
