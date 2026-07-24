# SP1 - Market Data Layer Implementation Plan

## Milestone

Deliver a portable, deterministic NQ/ES trade-normalization and six-timeframe
bar layer with local DBN ingestion, a thin live adapter, typed quality facts,
and Vision-aligned fitness tests.

## Task 1 - Domain and calendar `[portable, complete]`

Files:

- `src/stoic_derived/market_data/model.py`
- `src/stoic_derived/market_data/calendar.py`
- `tests/market_data/test_model.py`
- `tests/market_data/test_calendar.py`

Work:

- immutable fixed-point trade/bar contracts;
- canonical serialization and stable identities;
- strict committed CME equity-index schedule manifests, reviewed horizons,
  provenance, and explicit overrides;
- UTC/DST-safe daily and weekly bucket assignment.

Verification:

- validation, canonical bytes, half-open boundaries, DST, maintenance, weekend,
  and override tests.

## Task 2 - Pure aggregation `[portable, complete]`

Files:

- `src/stoic_derived/market_data/aggregate.py`
- `tests/market_data/test_aggregate.py`

Work:

- direct 1m/5m/15m/60m/D/W aggregation;
- deterministic event-time reorder buffer and watermark;
- canonical equal-timestamp ordering and trusted progress/series-close APIs;
- immutable finalization and typed late/gap/roll issues;
- no synthetic bars.

Verification:

- OHLCV/count, boundary, permutation, lateness, gap, roll, flush, and
  repeated-build tests.

## Task 3 - Historical Databento adapter `[portable, complete]`

Files:

- `src/stoic_derived/market_data/databento.py`
- `tests/market_data/test_databento.py`

Work:

- strict metadata inspection and symbol mapping;
- streaming fixed-point record normalization;
- input-order-independent contiguous coverage planning and redundant-source
  exclusion;
- dependency injection for zero-network unit tests.

Verification:

- fake DBN unit tests;
- opt-in bounded integration against the local tail DBN;
- nested NQ coverage cannot double volume, while equal-timestamp and
  byte-identical legitimate trades are preserved.

## Task 4 - Live adapter and cursor `[portable, complete]`

Files:

- `src/stoic_derived/market_data/live.py`
- `tests/market_data/test_live.py`

Work:

- fixed Databento trades subscription for NQ/ES continuous symbols;
- explicit replay/reconnect, provider progress, skipped-record halt, and
  credential hygiene;
- timestamp-and-count resume cursor plus explicit continuous-roll resubscribe;
- injected client fake for tests.

Verification:

- exact subscription parameters, replay overlap, cursor restart, heartbeat,
  exception, and no-secret-serialization tests.

## Task 5 - CLI and actual-data smoke `[portable, complete]`

Files:

- `src/stoic_derived/market_data/cli.py`
- `pyproject.toml`
- `tests/market_data/test_cli.py`

Work:

- `stoic-data inspect`;
- `stoic-data sample` for bounded normalized events/bars;
- JSON output only, with no credential values;
- add the supported Databento SDK dependency and lock it.

Verification:

```bash
uv run stoic-data inspect data/historical/<tail-file>
uv run stoic-data sample data/historical/<tail-file> --records 10000 \
  --calendar-manifest \
  config/market_data/calendars/cme-equity-index-2026-06-tail-v1.json
```

## Task 6 - Audit and milestone delivery `[portable, complete]`

Audit:

- review tests first and implementation in chunks below 400 lines;
- adversarially check timestamps, ticks, order, duplicates, lateness, rolls,
  malformed metadata, calendar gaps, secret leakage, and dependency boundaries;
- compare actual tail-file sample aggregates with an independent oracle;
- confirm no historical DBN, secrets, cache, or `VISION.md` change is staged.

Verification:

```bash
uv run pytest -q
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy src
uv lock --check
git diff --check
```

Delivery:

- commit one coherent SP1 milestone using a Conventional Commit;
- push to the configured upstream;
- update `Windows_steps.md` with the portable SP1 verification commands.
