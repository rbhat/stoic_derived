# SP2 - Deterministic Signal Engine Implementation Plan

## Milestone

Deliver the portable signal-engine substrate and prove deterministic,
causal, replay-safe behavior while truthfully keeping live strategy evaluation
blocked until SP0 publishes unambiguous human-approved semantics.

## Task 1 - Contracts and identities `[portable]`

Files:

- `src/stoic_derived/signal_engine/model.py`
- `tests/signal_engine/test_signal_model.py`

Work:

- frozen Type, direction, lineage, gap, suppression, and signal records;
- fixed timeframe plans and exact `1d`/`1w` translation;
- tick-exact prices, rational R, canonical JSON, and stable signal IDs.

Verification:

- strict validation, all four maps, exact R/orientation, canonical bytes, and
  same-value/different-provenance identity tests.

## Task 2 - Release compiler and readiness `[portable]`

Files:

- `src/stoic_derived/signal_engine/compiler.py`
- `tests/signal_engine/test_compiler.py`

Work:

- accept only the SP0 published-release loader output plus pinned release hash;
- compile mappings into a closed typed program;
- reject duplicate profiles and missing Type/role/feature, confidence
  threshold, repeated-setup rearm, and market-data binding semantics;
- expose deterministic blockers for the current candidate/no-release state;
- provide a clearly isolated strategy-neutral test program factory.

Verification:

- release tamper/path/hash/key tests reuse SP0 coverage;
- production compiler refuses semantic gaps and cannot enable a test program;
- test program covers long/short formulas without claiming strategy validity.

## Task 3 - Causal alignment `[portable]`

Files:

- `src/stoic_derived/signal_engine/alignment.py`
- `tests/signal_engine/test_alignment.py`

Work:

- validate committed batches and structured gaps;
- buffer by physical lineage and process same-end bars atomically;
- select only complete required bars ending no later than execute close;
- enforce monotonic finalization, bounded history, and replay idempotence.

Verification:

- future leak, same-close permutations, roll/source/fingerprint isolation,
  degraded/missing/gap cases, duplicate/conflicting bars, and all four maps.

## Task 4 - Predicate and signal evaluation `[portable]`

Files:

- `src/stoic_derived/signal_engine/evaluator.py`
- `src/stoic_derived/signal_engine/engine.py`
- `tests/signal_engine/test_evaluator.py`
- `tests/signal_engine/test_engine.py`

Work:

- exact operand and closed predicate evaluation;
- bounded temporal operations with explicit insufficient-history results;
- complete signal construction, orientation, exact R, confidence bounds;
- deterministic signal/suppression ordering and provenance closure.

Verification:

- every operator, boundary lookback, off-tick/unfillable/orientation failures,
  two directions, four Types, replay equality, and no future input IDs.

## Task 5 - Readiness CLI and dependency fitness `[portable]`

Files:

- `src/stoic_derived/signal_engine/cli.py`
- `src/stoic_derived/signal_engine/__init__.py`
- `pyproject.toml`
- `tests/signal_engine/test_signal_cli.py`
- `tests/signal_engine/test_boundaries.py`

Work:

- JSON-only readiness command for a pinned release or the repository candidate;
- no secrets or raw approval key material in output;
- static boundary checks for forbidden live-path dependencies.

Verification:

```bash
uv run stoic-signal readiness \
  --candidate strategy/rulebook.yaml
```

The committed candidate must report blocked and produce no release or signal.

## Task 6 - Audit and milestone delivery `[portable]`

Audit:

- review tests first, then implementation;
- adversarially check lookahead, same-close ordering, contract rolls, gaps,
  degraded bars, duplicate delivery, tick math, partial records, and imports;
- confirm SP3 cannot tune or feed engine parameters;
- confirm no release, secret, local data, cache, or `VISION.md` change is staged.

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

- record the SP2 audit under `docs/superpowers/audits/`;
- update `Windows_steps.md` with portable SP2 verification;
- commit and push one coherent verified SP2 milestone.
