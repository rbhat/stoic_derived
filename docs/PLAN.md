# Plan — from the 1-2-3 sequence to a deterministic signal generator

**Written 2026-07-31 on branch `123seq`. This is the whole plan, end to end.** It replaces the
four-line "Next, in order" that used to live in `docs/STATE.md`; that file now tracks position
within this plan rather than holding a plan of its own.

Binding documents are unchanged and win over anything here: `VISION.md` for the product,
`CLAUDE.md` for the one rule that governs everything, `coding_rules.md` before writing code.

## The target

A deterministic engine that reads NQ/ES bars and emits signal records — instrument, Type,
direction, entry, stop, target, R, setup type, confidence, timestamp, source — across the four
Types in the Timeframes Guide. No LLM or SLM anywhere in that path. The SLM is an offline tool
that helps us write the rulebook; the rulebook is plain code.

The measure of success is **fidelity, not edge**: does our implementation generate the trades the
method calls for. Divergence from the labelled material is a specification bug.

## Why this is plannable now

The 1-2-3 sequence is specified mechanically in the material, which the broader course never was.
`edu/123sequence/price_cycle.jpg` defines Step 1, Step 2, Step 3, Entry, Confirmation and Final
Technical Exit against a two-SMA structure;
`edu/123sequence/entry_technique/entry_technique_for_1-2-3_sequence.md` defines the pullback
trigger bar and first target; `edu/123sequence/entry_technique/step-3-livetrade.png` shows the
whole thing executed on a 5-minute MNQ chart with the fib target and R marked.

**Open those files — do not take a summary of them from anywhere, including this plan.** Phase 2
exists precisely because a cited, unambiguous restatement does not exist yet.

The surrounding context concepts — HCOM/LCOM, PDH/PDL/PDC, break & retest, swing failure pattern,
SBS, fib geometry, the no-edge zone, the 20/200 SMA session bias — are taught in
`edu/123sequence/start_here/only_trading_video.md` and the three supporting videos in `edu/videos/`.

## Ground we already stand on

- **Bars.** `data/historical/{NQ,ES}_1m.parquet` — 2019-06-10 → 2026-06-10, ~2.47M rows each,
  UTC-indexed OHLCV. Every timeframe in the Timeframes Guide resamples from these.
  `scripts/normalize_historical_bars.py` produced them.
- **Transcripts.** Five videos already transcribed in `edu/derived/`.
- **Validation material.** Eight case-study PDFs in `edu/resources/`.

---

## Phase 0 — Bar spine and session clock

**Goal.** One trustworthy way to ask for bars at any timeframe, with sessions labelled.

**Deliverable.** A bars module: resample 1m → 5m/15m/60m/Daily/Weekly; session labels for Asia,
London open, NY open, RTH, and the 1:58pm Pacific flatten boundary; UTC storage with Pacific
conversion at the edges only.

**Exit gate.** Resampled 60m matches `{NQ,ES}_1h.parquet` bar-for-bar over the full overlap, with
the mismatch count reported. Session boundaries verified across a DST transition in both directions.

**Watch.** `claude_memories/databento-ohlcv-buckets-by-ts-recv.md` bites here — bucket by the same
field the vendor did or the boundaries silently disagree.

## Phase 1 — Complete the corpus

**Goal.** Every video in `edu/123sequence/` is readable as text plus keyframes.

**Deliverable.** A minimal, resumable transcribe + keyframe pipeline, and its output for the three
untranscribed videos: Universal 1-2-3 Sequence, Stoic Traders Marker Study, Scalping Example.
Dependencies are already in `pyproject.toml`. The retired pipeline is at `git show main:edu/pipeline/`
— reference only; it was built for a broader corpus and should not be restored wholesale.

**Exit gate.** Three new directories under `edu/derived/`, each with a transcript and keyframes, and
a manifest that survives being killed mid-run.

## Phase 2 — The rulebook spec *(pivotal)*

**Goal.** One distilled strategy spec — rules, terms, worked examples, in plain language — that the
engine treats as source of truth, separate from the raw transcripts. `VISION.md` has been asking
for this document since v0.3.

**Deliverable.** `docs/RULEBOOK.md`. Every term the engine will implement, defined once, each with a
citation to where in the material it comes from (file + timestamp or diagram). At minimum: Step 1,
Step 2, Step 3, Confirmed Step 3, Step 3 High/Low, selected boundary, obvious base, meaningful
break, meaningful close, climax / visibly extended, PTB, entry, invalidation, first target, final
technical exit, HCOM, LCOM, PDH/PDL/PDC, break & retest, swing failure pattern, SBS model 1 and 2,
fib geometry targets, no-edge zone, trapped side.

Anything the material does not pin becomes a row in the decision register below rather than a
number someone quietly picked.

**Exit gate.** A reader who has never seen the videos can point at a chart and say where Step 3
confirmed, and two readers agree. Every rule cites its source. No rule cites this plan.

## Phase 3 — Labelled reference set

**Goal.** Ground truth. Without it, Phase 6 has nothing to measure against and the whole project is
unfalsifiable.

**Deliverable.** A set of labelled 1-2-3 instances: instrument, date, timeframe, the bar index of
Step 1 / Step 2 / Step 3, entry, stop, first target, outcome. Sourced from the live-trade
screenshots, the video walkthroughs, and the case-study PDFs. Each label carries its source
artifact so a disagreement can be adjudicated against the original, per the Evidence rule in
`VISION.md`.

**Exit gate.** Enough labelled instances on NQ/ES within 2019-06-10 → 2026-06-10 that Phase 6 can
report per-label outcomes. Report the count; do not set a target count in advance and do not treat
whatever number arrives as sufficient evidence of anything.

**Constraint to expect.** The case studies cover BTC, GC, RTY and GBP/JPY. We have bars for NQ and
ES only. Those labels can validate the *reading* of a setup but cannot be replayed bar-by-bar.
Split the set accordingly rather than discovering this during Phase 6.

## Phase 4 — The SLM

**Goal.** An offline research tool that accelerates Phases 2 and 3. Nothing more.

**Deliverable.** A small model that (a) proposes labels over the corpus for human confirmation, and
(b) proposes candidate formalizations of the fuzzy terms — "obvious base", "meaningful close" — with
the supporting passages attached. Training on the Windows box per `VISION.md`; artifacts under
`.artifacts/` per `claude_memories/artifact-locality.md`.

**Exit gate.** It has measurably reduced human labelling effort on Phase 3, and it appears nowhere
in Phase 5's import graph.

**Honest dependency note.** Phases 2, 3 and 4 bootstrap each other: seed labels by hand, let the SLM
propose more, confirm by hand, refine the spec, relabel. Run them as one loop, not a waterfall. The
engine depends on the spec and the labels — not on the model.

## Phase 5 — The rulebook engine

**Goal.** The deterministic core. Same inputs, same signal, every time, auditable line by line.

**Deliverable.** Pure functions over bars, layered in the order the method itself teaches:

| Layer | What it computes |
|---|---|
| L0 primitives | SMAs, swing points, HCOM/LCOM, PDH/PDL/PDC, session windows |
| L1 structure | consolidation vs expansion, base detection, boundary selection, extension from MA structure |
| L2 sequence | the Step 1 → Step 2 → Step 3 state machine; emits Confirmed Step 3 and Step 3 High/Low |
| L3 entry | PTB, stop-order price, invalidation, fib-geometry targets, R |
| L4 gating | HTF bias alignment, no-edge-zone filter, trapped side, does this setup deserve risk |
| L5 emission | the signal record in the `VISION.md` schema, with a deterministic confluence score |

Run per Type — Scalp, Day, Swing, Position — each with its own map → setup → execute timeframes from
the Timeframes Guide. The sequence is fractal by the method's own claim, so L2 should be
timeframe-agnostic and take its MA pair as a parameter.

**Exit gate.** Every layer unit-tested against hand-built bar fixtures. No network, no model, no
clock-dependent behaviour. Each gate has a negative control per `coding_rules.md`.

## Phase 6 — Fidelity measurement

**Goal.** Answer the only question we are allowed to ask: does our implementation generate the
trades the method calls for.

**Deliverable.** A replay harness that runs Phase 5 over the labelled dates and produces a
per-label reconciliation — fired or not, at which bar, direction, stop, target — plus a divergence
report where each divergence is triaged as a specification bug in the engine or a missing rule in
`docs/RULEBOOK.md`.

**Exit gate.** Divergences are explained, not just counted. Report counts, never verdicts; never
project direction; never conclude from small n.

## Phase 7 — Signal runtime and ledger

**Goal.** Signals become records that get tracked to an outcome.

**Deliverable.** A runner over live Databento and over replay, writing append-only per-source
ledger files reconciled into one ledger per Type, Google Drive as the source of truth. Every row
carries trade id, timestamp and source. Each signaled trade is tracked to take-profit or stop-loss.
The 1:58pm Pacific flatten fires for every Type except Position, guaranteed by a watchdog that
holds even if the process died earlier.

**Exit gate.** Kill the process mid-session and the flatten still happens. Two writers, no lost
rows, no corruption — this is the failure mode `VISION.md` calls unacceptable.

## Phase 8 — Dashboard

**Goal.** See it all at once — the point of the product.

**Deliverable.** The five sections in the `VISION.md` dashboard list: ledger with open and closed
sections plus charts, operational state, system management, user management with
rajeevmbhat@gmail.com immutable, Google auth invite-only as a GCP web client.

**Exit gate.** The admin-immutability rule holds against another admin attempting it.

## Phase 9 — Backtest, walk-forward, paper *(parallel)*

**Goal.** Measure expectancy, win rate, average R and max drawdown per timeframe and per instrument.

**Runs in parallel from Phase 5 onward and does not gate going live with signals** — v1 risks no
capital. Keep it out of the critical path, and keep its framing straight: this measures our
execution of the method, not whether the method works. No parameter grid searches for the best cell.

---

## Decision register — open, and the human decides

These are places the material genuinely underdetermines a number or a choice. Per `CLAUDE.md` they
are settled by the human and recorded as strategy decisions, never by searching for the best cell.
Phase 2 closes them; each one that closes gets a row in `docs/CONSTRAINTS.md`.

| # | Open question | Where the tension is |
|---|---|---|
| 1 | Which moving averages define the sequence | `price_cycle.jpg` and the step diagrams label **10 and 20 SMA**; `only_trading_video.md` teaches **20 and 200 SMA** on the 5m for session bias. The live-trade chart appears to show both pairs. Are 10/20 the sequence and 200 the directional filter? |
| 2 | What makes a break and a close "meaningful" | Body vs wick, distance beyond the MA, number of consecutive closes |
| 3 | What makes a base "obvious" | Bar count, range compression, proximity to the MA trend area |
| 4 | How the "selected boundary" of the base is selected | Undefined in the material; it is the entry trigger, so it must be pinned |
| 5 | What "visibly extended from the MA structure" means for climax | Needs a distance measure, likely normalised |
| 6 | Which target governs, and partial sizing | Entry doc says first target is Step 3 High/Low with partials and stop to break-even; the video teaches fib extensions at 2.618 / 4.23 / 6.86 |
| 7 | The MA pair per timeframe | The diagrams are 5m; the sequence is claimed fractal, so each Type's execute timeframe needs its pair pinned |
| 8 | HCOM/LCOM lookback | Current month only, or prior months retained as standing levels |
| 9 | Mechanical definition of the no-edge zone | Taught as a list of situations, not a condition |
| 10 | Minimum R for a setup to "deserve risk" | Taught as a principle with no number |

## Risks worth naming now

- **Phase 2 is the whole project.** If the spec is vague, Phase 5 encodes someone's guess and Phase 6
  measures that guess against itself. Resist starting Phase 5 early because it feels more productive.
- **Fuzzy terms will resist formalization.** "Obvious base" may not survive contact with code. When
  one doesn't, the answer is a human decision recorded in the register — not a swept parameter.
- **The labelled set will be small.** That is a reason to report counts and withhold verdicts, not a
  reason to manufacture labels.
- **Three source videos exist only on this disk** — gitignored and absent from `videos.zip`. Losing
  them costs Phase 1 its most on-scope input.

## Kickoff

Start at **Phase 0 and Phase 1** — they share no state and can run at the same time. Neither one
needs a decision from the register, which is why they come first: they build the ground Phase 2
stands on while the spec work is still open.

Do not start Phase 5 before Phase 2 has closed the register. Writing the engine against an
unfinished spec is the specific failure this plan is shaped to avoid.
