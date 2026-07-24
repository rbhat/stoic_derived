# Windows Setup

## Windows role

The Windows desktop is the CUDA training machine for the offline research SLM.
Its RTX 5070 Ti is intended for QLoRA fine-tuning on the education corpus. This
work belongs alongside SP0 strategy-rule mining and may run in parallel with
the deterministic subsystem roadmap; it does not need to wait for SP3.

This file records that responsibility and the handoff contract. It does not
start a training job.

## What the training is for

The fine-tuned SLM is a research assistant that helps turn the education corpus
into reviewable, evidence-backed rule candidates. Its useful output is not a
trade decision. It should surface:

- candidate setup, entry, stop, target, invalidation, and confluence semantics;
- the source video and timestamp supporting each candidate;
- contradictory examples, ambiguity, and unresolved questions;
- structured proposals that a human can compare with the primary sources.

The intended handoff is:

```text
education corpus
  -> offline SLM fine-tuning and inference
  -> cited candidate rules and conflicts
  -> human review against the videos
  -> approved rulebook semantics
  -> deterministic Python rules and tests
  -> signed strategy release
```

Your understanding is therefore correct with one important qualification:
training helps discover and organize the information needed to write the
scripts deterministically. Training does not make model inference
deterministic enough to replace those scripts. The live system must produce the
same result from the same inputs without consulting an LLM or SLM.

Model output cannot approve, promote, enable, disable, tune, or filter a live
signal. A model confidence value is not the live confluence score. The
confluence score is computed by approved deterministic rules.

## When fine-tuning starts

The Windows training track is an SP0 research dependency and should start as
soon as its version-controlled training package is ready. It is not sequenced
after SP3.

Do not launch an ad-hoc fine-tune from an unpinned notebook or one-off command.
The repository must first contain a reproducible Windows training package with:

- a content digest and immutable train/evaluation split for the input corpus;
- a pinned base-model identifier, revision, and license record;
- pinned CUDA/PyTorch/fine-tuning dependencies;
- a reviewed QLoRA configuration, fixed seeds, and bounded resource settings;
- commands for training, evaluation, offline inference, and artifact export;
- evaluation of citation fidelity, held-out behavior, and conflicting evidence;
- content-addressed outputs that record the dataset, code, configuration, and
  model revisions used.

As of 2026-07-24, `edu/derived/dataset.jsonl` exists, but that reproducible CUDA
training package has not yet been implemented. Until it is committed and
pushed, Windows fine-tuning is not ready to run. Do not choose a base model or
install an unpinned training stack locally to work around that gap.

This readiness condition protects the research record; it does not turn model
performance into a production gate. The actual live-readiness gate remains a
human-approved, semantically complete, signed SP0 strategy release.

## Production boundary

For v1, production means deterministic live signal generation plus ledger
lifecycle tracking. It does not mean automated broker execution or order
placement.

The SLM and its fine-tuning artifacts remain offline research inputs. They are
never loaded by the live signal engine, ledger, or flatten watchdog. Simulated
or model-proposed actions are observations and proposals only.

## SP3 portable verification on Windows/WSL

SP3 is ordinary deterministic Python and may be verified on the Windows
machine from the repository root in WSL. It does not use CUDA and it does not
start or depend on SLM training.

```bash
uv sync --frozen
uv run pytest -q
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy src
uv lock --check
uv run stoic-backtest readiness
```

Until a human-approved, semantically complete, signed SP0 release exists, the
last command must report `status: blocked`, zero signals, zero trades,
`execution: false`, and `orders_placed: 0`. That is the correct production
safety result, not a reason to load the draft rulebook or a private fixture.

## SP5 dashboard verification on Windows/WSL

SP5 remains portable deterministic software. Its production UI is a compiled
React 19/Vite static SPA; FastAPI is only the same-origin typed JSON/control
API. Windows verification does not start SLM training, load a private release,
or grant dashboard users Google Drive scopes.

From the repository root:

```bash
uv sync --frozen
uv run pytest -q
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy src
uv lock --check
uv run stoic-dashboard readiness
uv build
npm --prefix web ci
npm --prefix web run typecheck
npm --prefix web run test
npm --prefix web run build
npm --prefix web exec playwright install chromium
npm --prefix web run e2e
```

The readiness command must remain blocked with zero observations until the
real signed SP0 release boundary passes. Realistic dashboard records are
test-only. The Vite build under `web/dist/` is the static artifact that SP6
will deploy on GCP; FastAPI must not serve application HTML.

## Governing references

- [`VISION.md`](VISION.md), **“What the SLM does vs what generates signals”**
  (lines 12–16): the SLM helps build the rulebook; plain deterministic code
  makes the calls.
- [`VISION.md`](VISION.md), **environment strategy** (lines 30–34): Mac mines
  and infers, Windows performs CUDA fine-tuning, and deterministic code remains
  portable.
- [System roadmap §1, “Guardrails”](docs/superpowers/specs/2026-07-24-system-roadmap-design.md#1-guardrails-from-vision-non-negotiable):
  no model in the live path and offline SLM research only.
- [System roadmap §3, “Subsystem decomposition”](docs/superpowers/specs/2026-07-24-system-roadmap-design.md#3-subsystem-decomposition):
  SP0 semantics are SLM-assisted but must be human-validated.
- [System roadmap §5, “Environment strategy”](docs/superpowers/specs/2026-07-24-system-roadmap-design.md#5-environment-strategy-cross-cutting):
  `win-cuda` owns research-SLM QLoRA fine-tuning while deterministic systems
  stay portable.
- [ADR 0004, “Strategy source authority”](docs/architecture/adr/0004-strategy-source-authority.md):
  primary education sources outrank transcripts, labels, and model output.
