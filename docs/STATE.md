# Current state — what is true right now

**This file says what is true now. `git log` says what happened, `docs/CONSTRAINTS.md` says what
binds you, and the phase docs say how each phase was designed. Nothing here is a changelog.**

## Where the project is

| Phase | State |
|---|---|
| 0, 1, 2, 2a | Complete. Phase 2's deliverable is `docs/RULEBOOK.md`; its §12 register is closed — nothing blocks the engine. **Phase 2's exit gate names a two-reader test that has never been run**, which is not the same claim as the register being closed |
| 3 — labelled reference set | Labelling complete, 10 labels across 4 sessions. **Whether it closes is the user's call.** `docs/PHASE3.md` |
| 4 — the SLM | Off the critical path, three times running. Still its own: **O-9** and label proposals, neither blocking. `docs/evidence/phase4_room_left.md` |
| 5 — the engine | Complete. L0–L5 all built, every injected predicate filled |
| 6 — fidelity | Built, run once. `docs/PHASE6.md`, `docs/evidence/phase6_reconciliation.md` |
| 7 — forward test | Built, run, audited. `docs/PHASE7.md`, `docs/evidence/phase7_forward_test_NQ_scalp.md` |
| 7b, 8, 9 | Not started. `docs/PLAN.md` |

**Baseline:** `pytest` **357 passed**; `scripts/verify_citations.py` **222 citations across 8
sources, all resolve**, negative control PASS.

**The decision register is `docs/RULEBOOK.md` §11 (closed) and §12 (open) — nowhere else.** The
table in `docs/PLAN.md` is the superseded intake form.

## The two runs, and how to read them

Both are **counts, never verdicts** (`CLAUDE.md`): single instances, small *n*, nothing projected.

### Phase 6 — engine against the labelled set

`NQ` `5m`, `2026-06-22` → `2026-08-04`, 8,784 bars, `SCALP`, `htf=None`, exact-bar matching, no
tolerance. **10 labels reconciled, 2 matched on the exact bar** (`LT-B1`, `T-B1` — both agreeing on
price exactly), **25 unlabelled emissions** (not a false-positive rate; the label set is not
exhaustive).

**Phase 6 found no specification bug.** All eight unmatched labels traced to a rule working as
written — in seven, §5.4.7 invalidation fires between Step 3 confirmation and the labelled entry.
So building forward is not building on a known defect. The triage is in the report §2.

### Phase 7 — every signal tracked to an outcome

Same window and settings, deliberately, so the L5 totals cross-check. They do: 212 `signal`, 149
`break_even`, 49 `suppressed`, identical to Phase 6's run. **212 signals tracked:**

| outcome | count |
|---|---|
| `tp1` | 121 |
| `stop` | 63 |
| `invalidated` | 25 |
| `flatten` | 2 |
| `not_taken` | 1 |
| `ambiguous` | 0 |
| `open` | 0 |

**Read `tp1` 121 with the geometry, not as a hit rate:** TP1 is the Step 3 extreme frozen at fill
(§6.1, **D-16**), the *same near level* **D-25** moves the stop to break-even on. A target that
close being reached often is structure, not performance. **The report carries no expectancy, win
rate, average R or drawdown** — `docs/PHASE7.md` §8 makes that a requirement, and it is Phase 9's
measurement, not this one's.

**72 of the 212 needed the 1m spine** to say which level came first; none was unresolvable. The exit
gate is met: a fresh run writes 212 signals and 212 outcomes, an identical rerun appends **0 rows,
byte-identical file**, and a frame-start disagreement exits non-zero before the replay begins.

**`not_taken` 1 is a defect the harness found in its own first build.** A trade was booked as a
`flatten` with its exit priced *before its entry existed* — a sell stop the 1m bars put in the 20:59
minute against a 20:58 cutoff. The user's call, 2026-08-12: a fill at or after the cutoff on a
flatten Type is not a trade. Recorded, flagged, no P&L. **The engine still emits the signal** —
changing emission would move Phase 6's numbers.

**There is no `break_even` outcome.** TP1 and D-25's trigger are the identical frozen
`step3_extreme`, and TP1 is a full exit (user's call, 2026-08-12 — partial sizing is **O-7**, open).
The tripwire is
`tests/test_forward_test.py::test_tp1_and_the_break_even_trigger_are_the_same_frozen_number`, which
drives the real engine and **can fail**. The day it does, O-7 has landed.

## The material

- **`edu/123sequence/` — the main source.** 4 videos, the entry-technique write-up and diagrams, the
  concepts files, the war map, the user's `discussion/` and `concepts/PTB Questions.md` notes. Plus
  `PTBV` (1h38m, densest on §2.5/§5.3), `TPA` (58:00, densest on what a PTB is), and the marked
  charts `NQ3`, `T2`, `LT3`, `LT4`, `IBD`. **`DIA-P` is byte-identical to `DIA-L`** — one drawing at
  three paths, never two sources (§0).
- **`edu/videos/`** — 3 concept videos, supporting. **`edu/resources/`** — 8 case-study PDFs,
  validation not training. **`edu/derived/`** — 9 transcript sets, indexed by `manifest.json`.
- `docs/RULEBOOK.md` §13 records how the rest of the corpus is used: the daily-close layer is
  **complementary** — context and targets, never a step of the sequence, and it yields on conflict.

## Next

**`docs/PLAN.md` is the plan, end to end.** Nothing is blocked. The open choices, in the order they
would matter:

1. **Whether Phase 3 closes.** Its exit-gate counts are answerable (below); what is unfinished is
   only the optional per-keyframe clock table — build it *only* if a later pass needs a narrated
   setup placed on a specific bar.
2. **The eval set for D-34.** The base was chosen among rival constructions with **no eval set**;
   §10's marked charts are the natural one and are now dated and labelled, so it is finally
   buildable. Its §11 row names the rejected constructions so a measurement knows what it tests
   against.
3. **Whether to open a row for §7.3 *trapped side*.** The densest unmeasured term and a prerequisite
   for one of §7.4.2's instances, but it has **no open row**, so a proposal has nowhere to land.
   Opening one is the user's call, not the audit's.

**Phase 3's exit-gate counts** — every fixture is one session, so small *n* applies to all of them:

| Session | file | `taken` | `named` | `no_opportunity` |
|---|---|---|---|---|
| 2026-07-27 | `2026-07-27_LT.yaml` | 1 | 1 | 0 |
| 2026-07-30 | `2026-07-30_LT3_LT4.yaml` | 3 | 0 | 1 |
| 2026-07-31 | `2026-07-31_T1_T2.yaml` | 3 | 0 | 0 |
| 2026-08-03 | `2026-08-03_NQ3.yaml` | 1 | 0 | 0 |
| | **total** | **8** | **1** | **1** |

**Fixtures that would not date: 0** — all five dated with two independent agreements each
(`docs/evidence/fixture_dating.md`). **`PTBV` adds no id**: both its segments narrate executions
already labelled off the marked charts. That is the finding, not a shortfall.

## What Phase 0 and Phase 1 built

| | |
|---|---|
| `stoic/sessions.py` | CME trading day, session phases, the 13:58 PT flatten cutoff. UTC storage, local zones only inside this module |
| `stoic/bars.py` | 1m → 5m/15m/60m/1D/1W. Pure resample, no materialised parquet |
| `scripts/check_bar_spine.py` | Gates A–E, each with literal output and a negative control |
| `scripts/build_corpus.py` | Resumable transcribe + keyframe pipeline, 4 stages, no LLM/VLM |
| `scripts/verify_citations.py` | Every `KEY @ TIMESTAMP` in `RULEBOOK.md` resolves to a real marker, with a negative control. **Its `SOURCES` map is hand-maintained and drifts** — `TPA` was missing from it for the eight days it was the newest source, so 23 real citations reported as *unknown citation key* and nobody noticed. Add the key when you add a source, and run it after editing citations |
| `scripts/measure_ptb_atr.py` | Produced `docs/evidence/ptb_atr_distribution.md`, **now inert except for one number**: the two rejected PTB-anchor readings pick a different bar on **62.8%** of candidates (NQ 5m RTH 2019–2026), which is why **D-23** could not be adopted quietly and why it stands. O-5 closed by deleting the ATR stop floor (**D-18**), so nothing in the spec reads its percentiles |
| `tests/` | 25 tests, hermetic |

## What Phase 3 built so far

| | |
|---|---|
| `docs/PHASE3.md` | The design — data prerequisite, label schema, scope, order of work, exit gate. Read it before touching a label |
| `scripts/merge_signal_bars.py` | Extends `{NQ,ES}_1m.parquet` from `signals.db`. Idempotent, atomic, `--dry-run`, `$STOIC_SIGNALS_DB`. Our parquet wins on the overlap; the overlap check is **reported, never fatal** — that source is a lossy live capture, not a second vendor truth |
| `scripts/date_marked_chart.py` | Dates a chart by matching its four printed right-axis values against our SMAs, as a **sorted multiset** — the chart never says which label is which average. One sharp minimum is a candidate; `docs/PHASE3.md` needs a second, independent agreement |
| `scripts/fit_marked_chart.py` | Says which **bar** each mark sits on. Fits the candle comb and the price axis off the artifact, resolves execution arrows, and `--probe` prices any drawn line. **Read the comb's pixel residual first, then the price residual** — the comb should fit to ~1 px and the price to 0.4–1.0 pts sd. A comb residual near half a candle width means the slot count is wrong, which is what `LT3`/`LT4` was. Blobs past the live edge are dropped (the open-position P&L pill shares the arrow colours). `LT` is a different theme and returns zero candles |
| `docs/evidence/fixture_dating.md` | All five fixtures dated, each with its second agreement — `LT3` and `LT4` separately, being six hours apart. Also settles the SMA input series and puts §10.7's stop in doubt |
| `docs/evidence/labels/` | One YAML per fixture session. `2026-07-27_LT.yaml` (1 `taken`, 1 `named`), `2026-08-03_NQ3.yaml` (1 `taken`), `2026-07-31_T1_T2.yaml` (3 `taken`), `2026-07-30_LT3_LT4.yaml` (3 `taken`) |

**Every §10 fixture is dated** — reproduce with `scripts/date_marked_chart.py`:

| Fixture | CME session | Screenshot bar (ET) | SMA worst \|Δ\| | next-best bar |
|---|---|---|---|---|
| `LT` | 2026-07-27 | 10:05 | 1.77 | 32.41 |
| `LT3`/`LT4` | 2026-07-30 (exit 07-31) | 07-30 22:15 (`LT4`), 16:15 (`LT3`) | 0.16 / 1.08 | 12.93 / 9.92 |
| `PTBV` | 2026-07-30 | 15:10 | 0.59 | 10.05 |
| `T1`/`T2` | 2026-07-31 | 13:45 | 3.23 | 5.47 |
| `NQ3` | 2026-08-03 | 10:35 | 0.08 | 18.37 |

**Two gates needed a real fix when the spine grew, and neither was suppressed.** Gate A began
failing because the vendor 1h pull ended **mid-hour**: while the 1m spine also stopped there both
sides were truncated alike and agreed, and extending the spine made our bucket complete against the
vendor's partial one. `clip_to_comparable_span` drops that bar and everything past the vendor file's
end, and Gate B clips identically so the control measures Gate A's *logic* and not its *span*. **The
1h files stay frozen on purpose** — rebuilding them from our own 1m would make Gate A compare us to
us. Gate E names the bring-up window; the stale `2026-06-09` ES exception was removed, because a
named exception outliving its cause is the 2025-11-28 mislabel in miniature.

**The SMA input series is the close, and that is no longer a convention.** On `NQ3`'s bar the close
reproduces all four printed values to **0.08** points while `hl2`, `hlc3` and `ohlc4` are 9–13 out.
`stoic/indicators.py` had to pick one because §1.1 names none. It is corroborated, **not** a new
rule, and it gets no D-row.

## What Phase 5 L0–L5 built

Pure functions over bars — no disk I/O, no network, no clock, no model. Tests are hermetic and
hand-built; the suite is 240. L2's decided predicates add 42 in `tests/test_judgment.py` (15 of them
**D-34**'s), L3 adds 23 in `tests/test_entry.py`, L4 adds 27 in `tests/test_gating.py`, L5 adds 21
in `tests/test_emission.py`, and **D-34**'s five state-machine tests are in `tests/test_sequence.py`.

| | |
|---|---|
| `stoic/indicators.py` | 10/20 (sequence) and 50/200 (trend) SMAs of the close, on the frame given. Warm-up stays NaN — never `min_periods=1` |
| `stoic/candles.py` | `candle_structure` — inside-bar flags and **parent-bar** positions (§5.2.8a, **D-23**). A run of inside bars shares one parent; for a non-inside bar the parent is the nearest preceding non-inside bar, which is the reference **D-28** requires |
| `stoic/structure.py` | **L1.** `opens_pullback` / `find_pullback_start` / `leg_phases` — **D-28** (§5.2.1a): the pullback opens at the first completed candle whose **both** extremes move against the direction, measured against the parent bar. Never reads `open` or `close` (§5.3.3c) |
| `stoic/levels.py` | PDH/PDL/PDC, PWC/PWH/PLOW, HCOM/LCOM (§7.3, **D-8**). HCOM/LCOM are highest/lowest daily **close** — *"not the highest wick"* |
| `stoic/sequence.py` | **L2.** The Step 1 → Step 2 → Step 3 machine, the reset (**D-15**), the directional state (**D-21**), the running Step 3 High/Low (**D-16**, not frozen here), the Step 2 swing (**D-20**), and the three §5.4.7 invalidation events. **Under D-34 the base is a *state*, not a one-time selection:** `find_base` is re-asked on every bar while the base has never been broken, the span grows, and the Step 2 swing widens with it. `BASE_SELECTED` is emitted **once** on entry to the stage; a base that is cancelled and later re-forms emits again. Once `STEP3_BROKEN`, the line **freezes** — §2.3.1's *"pre-selected"*, and F6's re-break must re-break the same line. Still holds **no threshold** |
| `stoic/entry.py` | **L3.** The PTB walk — anchor, re-anchor per non-inside candle (**D-17**), inside-candle skip (**D-23**/§5.3.5a), the stop-market fill including the gap case (**D-22**), the stop at the opposite PTB extreme (**D-18**, no floor), and the break-even trigger (**D-25**) against the Step 3 extreme **frozen at fill** (**D-16**). Consumes L1's pullback and L2's events; derives neither |
| `stoic/gating.py` | **L4.** Two gates and no more: the 50 SMA direction gate (§7.1.2, **D-19** — per-bar close, no lookback, no tolerance, no chop detector) and the 200 SMA rule (§7.1.4 — **symmetric per D-31**, blocking a long at or below the 200 and a short at or above it, and **fast-chart-only**, so `fast_chart` is required with no default). Reason members are `TREND_50` and `INTO_200`; `gate(bars, pos, direction, *, fast_chart)` collects **every** reason, never short-circuits. A pure evaluator: the caller picks the bar — **L5 answered that with D-32 (the PTB anchor bar)**, and L4 still holds no opinion on it |
| `stoic/emission.py` | **L5.** The signal record (`VISION.md`'s schema + trigger *and* fill, §5.3.10), **R = \|fill − stop\|** fixed at fill with no floor (§5.4.2, **D-18**), **TP1** read from L3's frozen `step3_extreme` (**D-16**), `tp2` always `None` (anchors unpinned), the **confluence count** (**D-33**) and the **anchor-bar read** (**D-32**). Emits `SIGNAL`, `SUPPRESSED` (a fill L4 gated away — kept for Phase 6 triage, carrying no `SignalRecord`) and `BREAK_EVEN` (the event, never a second R). One `SignalEmitter` per direction; `replay_signals` drives both over `entry.iter_replay_steps`, which is the **one** implementation of the per-bar loop. Holds no threshold |

**L2's four terms stay injected, not implemented — and that is still true now that all four are
decided.** `Judgment` is a frozen dataclass of four predicates: *"meaningful"* break, obvious base,
boundary selection, *"meaningful close"*. L2 enforces every mechanical clause itself and asks a
predicate only about the unquantified adjective; a predicate is not even called when a mechanical
precondition fails. **The seam is what lets D-34's rejected constructions be replayed against it
without editing the engine** — `decided_judgment()` now defaults all four, and every default is
overridable for exactly that reason. §2.2.8 is enforced structurally, and twice over:
`select_boundary` receives bars truncated at the base's last bar, and under **D-34** that span
itself ends at the candle *before* the one whose break is being tested.

**`stoic/judgment.py` is where a decided predicate lives — never `stoic/sequence.py`.** It holds the
two **D-29** predicates, **D-30**'s `select_boundary_from_base`, **D-34**'s `find_base`, and the
two constants `MEANINGFUL_FRACTION = 0.10` (**D-29**) and `MIN_BASE_CANDLES = 2` (**D-34**) —
**the only numbers in the engine**. Each names the §11 row that authorised it. It fixes **four** conventions in its
docstring rather than in `docs/RULEBOOK.md`, the same disposition `candles.py` took for its
inside-bar tie-break: **no parent bar means not confirmed** (head of frame — no yardstick, so
`False`, never a pass); **a non-finite parent range means not confirmed**, while a parent range of
exactly zero is left to the literal arithmetic; **an unclassifiable candle is *basing***, which is
the *opposite* disposition to the first two and deliberately so, since D-34 makes basing the
residual rather than confirmation the thing being withheld; and **the Step 1 candle is never part
of the base**, or its close could set the boundary under D-30. `attach_parent_pos(bars)` must be
called once per frame — it now attaches **`is_inside` as well as `parent_pos`**, both prefix-stable
so it can be called once and sliced — and the predicates raise rather than guess if a column is
absent.

**Invalidation scope outlives the directional state, and that is the rulebook, not a convenience.**
An L2 count dies at the 10/20 reset (§2.5.8, **D-21**); the §5.4.7 conditions attach to a position
or a pending order, which does not (§6.5). Gating them on the count's stage made §5.4.7a
unreachable — the bullish reset predicate is character-identical to the bearish Step 1 predicate, so
the opposite Step 1 always resets us before its Step 3 can confirm. The §5.4.7 engine note settles
it: they *"fire before the opposite sequence completes — 5.4.7a can be many bars away."*

**L3 fixed three conventions in its module docstring rather than in `docs/RULEBOOK.md`**, the same
disposition `candles.py` and `judgment.py` took: an **exact touch of the trigger does not fill**
(§5.2.3 says *"trades above it"*; strict, not inclusive), **simultaneous §5.4.7 conditions cancel the
one working order once**, and `ORDER_CANCELLED` carries the cancelled order's own payload.

**L4 fixed five conventions the same way, and one of them has a consequence worth stating.** A close
exactly equal to either MA **blocks**; a **NaN SMA blocks**; `fast_chart` has no default; reasons are
collected, not short-circuited. The consequence: a frame needs **50 bars before any signal passes**,
and **200 before any long passes on a fast chart**. That is the intended reading — the alternative is
emitting signals whose gates were never actually checked — but it is a warm-up cost Phase 6 will see
at the head of every frame, not a bug.

**L5 fixed seven conventions the same way; three of them are load-bearing.** A **NaN SMA** and an
**exact tie** both make a confluence condition *absent*, never present — `gating.py`'s precedent, no
yardstick means not confirmed. **`htf=None` makes the HTF condition absent and the denominator stays
3**, so a caller who supplies no HTF frame tops out at 2 of 3 rather than being silently rescaled;
scores stay comparable across records. And **break-even links to its signal by `(direction, fill
price)`, earliest match first** — L3's `STOP_TO_BREAK_EVEN` carries no `fill_pos`, so price is the
only handle, and a break-even for a **suppressed** candidate emits nothing, since L3 does not know
about gating and keeps tracking it. The residual is stated in the docstring: two same-direction
entries filling at the identical price make that link ambiguous.

**Two orderings inside L3's bar are the design, not accidents.** The **fill is checked before L2's
events** because a fill is intrabar while all three §5.4.7 conditions are close-based (the §5.4.7
engine note), so on a bar that both fills and invalidates, the fill happened first. And a **`RESET`
does not cancel a working order** — it only disarms, so no *new* pullback is scanned. §5.3.4a says
there is *"no third outcome and no timeout"*: only a fill or §5.4.7a–c ends the walk. That is
**O-15** implemented exactly as the rulebook is written, not reconciled, and a test pins it.

**L1 is still only the pullback boundary, and base detection did not move into it.** Base detection
(**D-34**) and boundary selection (**D-30**) live in `stoic/judgment.py`, because both are decided
predicates and that is the only module allowed to hold one — but **D-34 is built out of L1's
`opens_pullback` logic rather than a second copy of it**, which is the layer rule working. **Climax
is still not built** (§4 is **J**), and **swing-point detection is not built either** — no rulebook
definition exists, any pivot needs an invented lookback, and nothing consumes one.

**Two unpinned choices are documented as conventions in their module docstrings, and deliberately
not written into `docs/RULEBOOK.md`:** a bar whose high *and* low exactly equal its parent's counts
as **inside** (`<=`/`>=`), and the SMA input series is the **close** (§1.1 names neither).

## What Phase 6 built

| | |
|---|---|
| `stoic/fidelity.py` | Pure measurement — pairs labels to L3/L5 records per `docs/PHASE6.md` §4 and computes signed deltas on scoped fields only. Holds no threshold and no tolerance; never imported by L0–L5, enforced by an import-direction test |
| `scripts/reconcile_labels.py` | The driver — Gate 0 checks every `phase6_scope` block for consistency before any replay runs, then drives `replay_entries` and `replay_signals` over the bars and writes the report |
| `docs/evidence/phase6_reconciliation.md` | The deliverable. §1 (per-label reconciliation) and §3 (unlabelled emissions) are generated by the driver; §2 (divergences) is hand-written, each entry triaged as a specification bug, a missing rulebook rule, or out of v1 scope |

## What Phase 7 built

| | |
|---|---|
| `stoic/tracking.py` | Pure measurement — one row per emitted `SIGNAL` with its outcome, exit bar, exit price and flags. Holds no threshold and no tolerance; never imported by L0–L5, enforced by an import-direction test. Reads **L2's** invalidation events and **L5's** signals; **not L3's** records, which carry nothing the other two do not. Infers its bar span from the index (median of positive diffs, so the CME break cannot poison it), so it is frame-agnostic |
| `scripts/forward_test.py` | The driver — resamples, runs both replays, tracks, folds and appends the ledger, writes the report, prints per-stage timing. Refuses a frame-start disagreement and refuses `--type swing` / `--type position`, which run on 60m and Daily per **D-7** while this driver resamples to 5m |
| `.artifacts/ledger/<type>.jsonl` | Append-only, one file per Type (`VISION.md`), `$STOIC_LEDGER_HOME` overriding. A trade closing is a **new row**, never an edit. Gitignored and regenerable by replay — the *report* is the tracked evidence |
| `docs/evidence/phase7_forward_test_<instrument>_<type>.md` | The deliverable, fully generated. Counts per outcome class, every `ambiguous` and flagged row named, open trades carried forward. **No expectancy, win rate, average R or drawdown** |

## Open

Real open questions and live caveats only. A finding that is *recorded and not acted on* belongs in
`docs/CONSTRAINTS.md` (as a trigger) or `docs/evidence/` (as the measurement), not here.

**Undecided, and not to be resolved by editing the engine:**

- **Is "Step 3 confirmed, no pullback opened yet" a pending setup under §5.4.7's own scope?** On
  four Phase 6 rows, §5.4.7c fired against an *armed* machine with no position and no working
  order, clearing `armed` before a PTB could anchor. §5.4.7 scopes itself to *"an open position and
  a pending setup alike"* and nothing says whether this counts. Both readings defensible, neither
  adopted. Same shape as **O-15** and **O-17**. `docs/evidence/phase6_reconciliation.md` §2.
- **Is the engine's selected boundary the line the trader traded against?** On `T-A1`/`T-A2` the
  engine anchored a PTB and cancelled it on §5.4.7c three and six bars before the labelled entries —
  the rule applied correctly, so the question is upstream at **D-30**, decided from a 6-to-5 corpus
  split no passage addresses directly. `T-A2` carries the most transcribed reference values of any
  unmatched row, so it is what would score most if the reading changed.
- **`T-B1`'s two disagreements, neither settled.** The engine reproduced the trade exactly and then
  suppressed it on §7.1.4 / **D-31**; separately its R (41.25) differs from the label's
  `by_ptb_extreme` distance (42.42) by 1.17 points. **n = 1.** No reading adopted.
- **L5's `continuation` flag survives a §5.4.7 invalidation**, because it clears only on `RESET`
  (**D-21**). Whether the directional state should die there is not stated anywhere. **Nothing
  depends on it** — no entry, stop, R or target reads the field — so it is not an O-row.

**Live data caveats. Any replay touching these must exclude or flag them:**

- **`2025-11-28` has a ~645-minute hole** in `data/historical/{NQ,ES}_1m.parquet` — the whole
  Asia/London portion, both instruments. Real missing data.
  `claude_memories/historical-bars-2025-11-28-outage.md`; Gate E reports it every run.
- **`2026-06-11` → `2026-06-19` is a second hole, and it is ours** — those sessions come from
  `signals.db` during that capture's bring-up, at 12%–65% per session (06-19 caught **9 bars of
  1,380**). From 2026-06-22 the source runs essentially complete. **No §10 fixture falls in it.**
- **Bars after 2026-06-10 are a live capture, not Databento OHLCV.** 25 of 3,240 overlap bars
  disagree, all inside the bring-up window; `source = signals_db` marks every affected row.
  Databento's historical API is not available here — the key is live-feed only.
- **`stoic/levels.py` reports a leading partial month as complete.** Daily history begins
  2019-06-10, so June 2019 holds 15 sessions and **45 sessions per symbol** read `hcom_m1`/`hcom_m2`
  off a truncated month with no NaN and no flag. A frame starting mid-week does the same to
  `pwc`/`pwh`/`plow`. The caller excludes or flags it; the function cannot detect it.
## What was removed on 2026-07-31, and how to restore it

Restore with `git show main:<path>` or `git checkout main -- <path>`.

| Removed | Restore from |
|---|---|
| `edu/derived/` for 7 case-study + live-session videos, `dataset.jsonl`, `index.json` | `main` (transcripts); keyframes are regenerable |
| 12 `.mp4` under `edu/resources/` | `videos.zip` → `./unzip_videos.sh` |
| `edu/pipeline/` (14 files) | `main` — superseded by `scripts/build_corpus.py` |
| root `requirements.txt` | superseded by `pyproject.toml` |

## What does not belong in this file

Completed work. This file says what is true now; `git log` says what happened.
