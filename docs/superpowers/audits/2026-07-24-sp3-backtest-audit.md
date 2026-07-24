# SP3 Observational Backtest, Chronological Replay, and Paper Audit

- Date: 2026-07-24
- Result: PASS; PRODUCTION STRATEGY REMAINS BLOCKED AS DESIGNED
- Scope: SP3 contracts, conservative simulator, exact metrics, release-bound
  runner, chronological folds, paper checkpoints, canonical codec, immutable
  artifacts, CLI, dependency boundaries, and portable tests

## Vision and Boundary Review

- `VISION.md` is unchanged and unstaged.
- SP3 calls only `SignalEngine.from_release(...)` and `SignalEngine.ingest(...)`
  for production composition. It never loads draft YAML or compiles a private
  strategy mapping.
- The public package exports only release-bound replay, chronological replay,
  paper observation, readiness, artifact publication, and artifact inspection.
- The CLI exposes only `readiness`, `run`, and `inspect`. It has no strategy,
  fixture, optimizer, tuning, promotion, filtering, broker, or order command.
- SP2 contains no SP3 import. Strong, poor, blocked, or absent performance
  evidence cannot configure or gate the live engine.
- Every result and manifest declares `execution: false` and `orders_placed: 0`.
  Simulated fills remain research observations.

## Truthful Production Readiness

No signed strategy release exists under `strategy/`. The SP0 authoring
candidate remains blocked by the missing human-approval envelope, four
unvalidated setup/direction profiles, three unknown executable rule contracts,
eleven unresolved semantic decisions, and the unresolved SMA source conflict.

`stoic-backtest readiness` reaches the public SP2 release boundary with no
release identity. It returns `blocked`, preserves the release blocker, and
reports zero signals and zero trades. No private mechanics fixture is reachable
from the public package or CLI.

## Causality, Lifecycle, and Accounting Review

- A signal cannot fill on its decision bar. Only a strictly later, complete,
  gap-free one-minute bar from the exact physical lineage is eligible.
- Entry requires a planned-level touch. The entry-bar target is ignored, the
  entry-bar stop wins, later stop/target ambiguity is stop-first, stop gaps use
  the worse open, and target gaps receive no favorable improvement.
- Entry and exit slippage are directional and adverse. Round-turn fees are
  subtracted exactly once. Gross and net R are reduced rationals over planned
  risk; binary floating point is absent.
- The exact complete bar ending at 13:58 Pacific closes open non-Position
  observations after stop-first evaluation. Pending observations do not gain a
  fabricated entry. Position observations are cutoff-exempt.
- A committed watermark beyond the cutoff proves an absent cutoff bar even
  when no later one-minute bar arrives. Such observations become
  `missing_cutoff_bar`, not a generic end-of-data result.
- DST uses `America/Los_Angeles`, not a fixed offset. Degraded or gapped cutoff
  evidence fails unresolved with a typed warning.
- Physical roll retires pending and open observations before SP2 lineage state
  is dropped. No Type, including Position, crosses a physical contract.
- Duplicate signals, bars, batches, and paper suffixes are idempotent; same
  interval conflicts and retired-lineage reappearance fail closed.

## Metrics, Folds, and Paper Review

- Metrics retain closed, pending, open, unresolved, and suppressed populations
  separately.
- Physical-contract partitions never mix instrument IDs. Root summaries
  combine only the same root/Type/execute timeframe/direction/setup and retain
  their physical contract count.
- Win rate, expectancy, average win/loss R, and maximum drawdown in R and ticks
  use exact closed-trade accounting. Samples below 30 carry
  `insufficient_sample`; multiple partitions carry the multiplicity warning.
- Chronological folds are half-open, non-overlapping, non-optimizing, and use a
  fresh public SP2 composition per fold. Only evaluation-interval decisions are
  admitted; active observations censor at fold end.
- Historical folds are labeled `retrospective_replay`, never genuine
  out-of-sample walk-forward. Incremental paper evidence is `paper_forward`.
- Paper restart replays canonical committed evidence and validates active state,
  release identity, signing-key fingerprint, policy, horizon, ordering, and
  content identity. Accepted batch count, active records, output records, and
  checkpoint bytes are bounded. The byte lower bound is checked before replay.

## Artifact and Portability Review

- Batch, policy, plan, record, run, checkpoint, and manifest identities exclude
  wall clock, locale, host, random state, and absolute paths.
- JSON/JSONL is canonical UTF-8. Inspection rejects unknown, missing, symlinked,
  reordered, noncanonical, identity-mismatched, or hash-mismatched content.
- The manifest pins every member hash and row count and includes the
  research-only disclaimer.
- Publication writes and synchronizes a sibling temporary directory, writes the
  manifest last, then uses native atomic no-replace rename semantics on macOS,
  Linux/WSL/GCP, and Windows. A target appearing during publication is retained
  untouched and publication fails closed.
- Windows directory fsync is skipped because the platform does not support it;
  each file is still flushed and synchronized before the Windows no-replace
  rename. Unsupported platforms fail closed rather than using an overwrite
  fallback.

## Independent Review Findings Resolved

An independent Terra review inspected the source in bounded chunks and reran
the focused suite. It found:

1. a watermark-past-cutoff path that could previously end as generic
   `end_of_data` when the exact cutoff bar and all later one-minute bars were
   absent;
2. a check-then-rename race where POSIX `os.rename` could replace a racing empty
   target directory;
3. one Ruff nested-context-manager finding in the checkpoint-bound test.

All three were fixed. Regression tests now cover the watermark-only missing
cutoff, runner integration, racing-target refusal, and pre-replay checkpoint
byte bound.

## Verification

```text
uv run pytest -q
251 passed, 1 skipped

uv run pytest -q tests/backtest
70 passed

uv run ruff format --check src tests
52 files already formatted

uv run ruff check src tests
All checks passed

uv run mypy src
Success: no issues found in 28 source files

uv lock --check
Resolved 64 packages

uv run stoic-backtest readiness
status: blocked
signal_count: 0
trade_count: 0
execution: false
orders_placed: 0

uv build
source distribution and wheel built successfully

git diff --check
passed
```

The blocked strategy state is intentional and remains the production safety
boundary until SP0 semantics are human-approved, semantically complete, and
published as a pinned signed release.
