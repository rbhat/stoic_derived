# Phase 7 — forward-test harness

**Design, agreed 2026-08-12.** `docs/PLAN.md` Phase 7 is the charter; this file is how it gets
built. It does not restate a rule from `docs/RULEBOOK.md` — open the section it names.

The question stays `CLAUDE.md`'s: **does our implementation generate the trades the method calls
for.** Phase 6 answered it against ten labelled instances. This phase makes the same question
answerable on bars nobody has labelled, by tracking what the engine emits to an outcome. **An
outcome is not a verdict.** Counts per outcome class, never expectancy, never direction — that is
Phase 9's charter and `CLAUDE.md` forbids reading it as edge.

**The durability requirements this phase was split from are Phase 7b's** — live Databento, per-source
ledger files reconciled into one, Google Drive as the source of truth, the flatten watchdog. None of
them is here, and none of them gates forward testing.

## 1. What already exists, and the one thing that does not

`stoic/emission.py`'s `replay_signals` already emits every signal with a trade id, a timestamp and a
source (`VISION.md`'s three required ledger fields), and `stoic/sessions.py` already owns the
flatten cutoff. This phase adds **tracking**, not signal generation, and modifies **no layer**.

What no layer produces is an **exit**. L3 tracks a filled position exactly as far as its own job
requires — until break-even fires (§5.4.5, **D-25**) — and then drops it. Three consequences, all
measured off `stoic/entry.py` rather than assumed, and each one shapes the design below:

- **A §5.4.7 invalidation that drops open positions emits no record for them.** `stoic/entry.py`
  step 4 emits `ORDER_CANCELLED` **only if a working order existed**, then sets `positions=()`. So a
  position invalidated with no order resting disappears from L3's event stream silently. **The
  invalidation itself is L2's fact, not L3's** — `Event.INVALIDATED_OPPOSITE_STEP_3` /
  `INVALIDATED_MA_CLOSE` / `INVALIDATED_BOUNDARY_CLOSE`, emitted by `stoic/sequence.py` with their
  bar and direction. Tracking reads them there. That is the layer rule, not a workaround: reaching
  into L3 for a fact L2 owns is what `docs/PLAN.md`'s layer note warns against.
- **L3 drops a position from its book the moment break-even fires**, because §5.4.5 is the only
  stop move there is (§6.5b). The trade is still open; L3 simply has nothing left to do with it.
  Tracking therefore keeps **its own** position book.
- **`ORDER_VOIDED` (§5.3.4b, **D-35**) is not an exit.** It ends the walk and touches the working
  order only — positions are untouched, by design and by test. Tracking must not treat it as one.

## 2. What closes a trade — the user's call, 2026-08-12

**The first terminal event wins, and TP1 is a full exit.** Partial sizing is **O-7**, open, and
`tp2` is always `None` in v1 (§6.2's anchors unpinned) — so no rule exists that sizes a runner, and a
tracker that left one on would be describing a position the rulebook does not specify. Every event
is still written to the ledger, so a later O-7 decision re-derives outcomes from the file without a
re-run.

| outcome | fires when | exit price |
|---|---|---|
| `stop` | the bar's range reaches the stop (§5.4.1, **D-18**) | the stop |
| `tp1` | the bar's range reaches L3's frozen `step3_extreme` (§6.1, **D-6**, **D-16**) | TP1 |
| `invalidated` | L2 emits any of §5.4.7a–c for that direction while the trade is open | that bar's **close** |
| `flatten` | the bar **containing** 13:58 PT, every Type but Position | §4 |
| `not_taken` | the order fills at or after the cutoff on a flatten Type — the trade was never takeable | none, and **never a P&L row** |
| `ambiguous` | two terminal levels reached on one bar and the 1m spine cannot separate them | none — the trade is **closed**, at no recorded price |
| `open` | the bar spine ends first | none |

**`ambiguous` is terminal, not a deferral.** The trade certainly ended on that bar; what is unknown
is at which level. Carrying it forward would let one unresolvable bar contaminate every later bar's
book.

**Levels are reached by trading through them, not by closing through them.** A stop and a target are
resting orders, so the test is the bar's high/low — the same intrabar test `stoic/entry.py` already
uses for the fill (§5.3.7) and for break-even. **An exact touch does not trigger**, which is
`stoic/entry.py`'s own stated convention on §5.2.3 (*"trades above it"*) applied consistently rather
than a second convention invented here. §5.4.7 is the exception and stays close-based, because the
rulebook makes all three conditions close-based (its engine note) and they are L2's events, already
decided by the time tracking sees them.

**There is no `break_even` outcome, and the reason is structural.** TP1 is the Step 3 extreme frozen
at fill (§6.1, **D-6**, **D-16**) and D-25 fires break-even against **that same frozen extreme**
(`stoic/entry.py` step 3), so the bar that trips break-even is the bar that reaches TP1 — and TP1 is
a full exit. No trade can ever exit at its fill.

**The first build kept the class and pinned it at zero, and that pin was worthless** — nothing in the
module could construct it, so the assertion held whatever the code did. A pin by *absence* is not a
pin by *observation*, which is what makes `tests/test_entry.py` case 18's `ORDER_VOIDED` a real
tripwire: that one has a producer. So the class is **removed**, and the tripwire moved to where it
can fire — **a behavioural test over the real engine asserting that a `BREAK_EVEN` emission's linked
signal carries a `tp1` equal to the level that triggered it.** The day those two stop being the same
number, that test fails. **This is a consequence of O-7 being open, not a finding about the method:**
the moment partial sizing is decided, TP1 stops being a full exit and the class comes back.

The `BREAK_EVEN` *event* is still written to the ledger. **A caveat for whoever folds that file
later:** L3 evaluates break-even on the 5m bar, while tracking resolves the same bar at 1m — so a
`BREAK_EVEN` row can describe a stop move on a position that the 1m spine says had already stopped
out. Tracking is the finer instrument and its outcome is the one to trust.

**A gap fill already beyond TP1 exits on its own fill bar, at the fill.** `stoic/entry.py` names the
case (a gap fill above the frozen extreme opens already beyond break-even). Recording an exit at TP1
there would book a price the market never offered after entry. The row is **flagged**, and its count
is reported.

**`not_taken` is the user's call, 2026-08-12, and it exists because the alternative books a price
backwards.** The flatten cutoff sits two minutes before the close, so an order can trigger inside a
bar *after* the cutoff has already passed. The first build of this harness recorded exactly that
once in 212 trades — a fill in the 20:59 minute booked as a `flatten` priced at 20:58, `bars_held`
0, a negative R on a trade that could not have been entered. **The engine still emits the signal**:
emission is Phase 5's and changing it would move Phase 6's numbers. Phase 7 records the signal,
flags it `filled_after_cutoff`, and books no outcome and no P&L.

**`SUPPRESSED` is written to the ledger and never tracked.** It carries no `SignalRecord` (Phase 6
§4) and was never a trade. Keeping the row is what lets a later pass measure what the gate cost;
tracking it would be inventing a position L4 refused.

## 3. The intrabar rule — one function, one dependency

A bar whose range reaches **two** terminal levels does not say which came first. We hold
`data/historical/{NQ,ES}_1m.parquet`, so the harness **drills into that bar's own 1m bars and reads
the real order**. This is the only place in the phase that reads a second frame.

- The 1m bars are the same spine `stoic/bars.py` resamples the 5m frame from, so no new source and
  no new alignment question.
- If the 1m bars are **missing** (`2025-11-28`, `2026-06-11` → `2026-06-19` — `docs/STATE.md` Open)
  or **themselves ambiguous** (one 1m bar spanning both levels), the outcome is **`ambiguous`**, it
  is **counted in the report**, and no exit price is invented. `CLAUDE.md`'s standing rule applies:
  report the count, never guess the direction.
- **No tolerance, anywhere.** `stoic/tracking.py` holds no threshold, no fraction and no tuned
  number, exactly as `stoic/fidelity.py` does not — `docs/CONSTRAINTS.md` keeps `stoic/judgment.py`
  the only module allowed one.

A bar reaching one level and nothing else never touches the 1m frame. Drilling is the exception, and
its count is reported.

**Three windows need the 1m frame, not one, and all three are the same question asked over a
different span.** *Did this level get reached inside the part of the bar where the trade was
actually live?*

1. **Two levels on one bar** — the span is the whole bar.
2. **The fill bar** — the span starts at the first 1m bar trading through the trigger. A long's stop
   sits below its trigger, so a bar can dip to the stop *before* the entry ever triggers, and
   booking that as a stop-out records a loss on a position that did not exist yet.
3. **The flatten bar** — the span ends at the cutoff. A level reached at 16:59 is reached after the
   trade was already flat.

**The three compose; they are not alternatives.** The first build treated them as separate branches
and consulted the fill window only when a 5m level had been hit, so a bar that hit nothing fell
through to the flatten branch without anyone asking whether the trade was live at the cutoff — which
is how a fill in the 20:59 minute got booked as a flatten priced at 20:58. **Compute the live span
first, on every bar, then ask what it reached.** An empty live span is `not_taken` (§2), never a
coverage failure: the 1m data being complete and the window being empty are different facts and must
not report as the same flag.

## 3a. Ordering inside a bar

L3's own ordering, applied to exits: **intrabar before close-based.** `stoic/entry.py` fixes it for
the fill (§5.3.7 is intrabar; the §5.4.7 engine note makes all three invalidations close-based), and
an exit tracker that ordered them the other way would book a §5.4.7 close on a bar whose stop was
taken twenty seconds in. For each open trade, per bar, first match wins:

1. **The fill bar only** — the fill is already beyond TP1 (a gap): exit at the **fill**, flagged.
2. **Stop or TP1 reached**, per §3's window rules and the 1m drill when both are.
3. **§5.4.7a–c** for that direction (L2's event, close-based): exit at the bar's **close**.
4. **The flatten bar** (§4).

**On the flatten bar the order inverts against §5.4.7 and only against it.** The cutoff is 16:58 and
the bar closes at 17:00, so an invalidating close happens after the trade is already flat — the
flatten wins. A stop or TP1 still wins if the 1m frame puts it **before** the cutoff, which is
window 3 above. This is the one place a later step in the list can beat an earlier one, and it is
the clock saying so, not a preference.

**Terminal checks begin on the fill bar itself**, inclusive. A trade that fills and invalidates on
one bar opens and closes on that bar — `stoic/entry.py` fills before processing L2's events, so both
are true and in that order.

## 4. The flatten — and the gap `docs/STATE.md` already named

`VISION.md` flattens every Type but Position at 13:58 Pacific, derived from Pacific wall-clock so
DST needs no offset (`stoic/sessions.py`). Two facts make this more than a filter:

- **`past_flatten` is 0 for every 5m bar by construction** — the cutoff sits in a 2-minute window no
  5m bar can start in. Tracking needs the bar **containing** the cutoff (the 16:55 ET bar), not bars
  after it. Using `past_flatten` here is the trap; `docs/STATE.md` names it and this is the phase
  that hits it.
- **The exit price is the close of the 1m bar ENDING at the cutoff** — the 16:57 bar, whose close is
  the price at exactly 16:58:00. The user's call, 2026-08-12. The first build read the bar *starting*
  at 16:58, whose close is struck a minute late, which put pricing and detection in contradiction:
  §3's window 3 already treats `[bar_start, cutoff)` as the live span, so a stop taken at 16:58:30
  was invisible to detection while the exit was booked at a price struck 30 seconds after it. When
  the 1m bar is missing, the containing 5m bar's close is used and the row is **flagged**, never
  silently substituted.
- **A session with no bar containing the cutoff still flattens**, at that session's last bar's close,
  flagged. `VISION.md` makes the flatten unconditional, and a holiday early close otherwise produces
  no flatten at all — 2026-07-03 closed at 13:00 ET, and a trade open there would have ridden 53
  hours into the following Monday. The frame's own final session is not flattened: it has not ended.

Without the flatten the recorded outcomes for Scalp and Day are simply wrong, which is why it is in
this phase and not in 7b. **7b owns the watchdog** that guarantees it when a process died; a replay
cannot die mid-session.

## 5. The ledger

**Append-only JSONL, one file per Type** (`VISION.md`: one ledger per Type), at
`.artifacts/ledger/<type>.jsonl`, with `$STOIC_LEDGER_HOME` the sanctioned override
(`claude_memories/artifact-locality.md`). Every row carries **trade id, timestamp and source** —
`VISION.md` requires all three because 7b will have multiple writers.

- **A trade closing is a new row, never an edit.** Current state is a fold over the file, and the
  fold drops a torn trailing line.
- **A torn tail is truncated back to its last newline before the next append, and that is the one
  sanctioned rewrite of this file.** It removes only bytes that were never a complete row. Appending
  onto a torn line instead is not a smaller fix, it is a fatal one: the concatenation is still the
  trailing line, so the whole next run is silently swallowed, and the append after *that* turns it
  into a malformed **interior** line which every later fold rejects — one torn write bricking the
  ledger for good. `VISION.md` calls losing or corrupting it unacceptable. `coding_rules.md`'s
  tmp-then-`os.replace` governs the **report**, not the append path: rewriting an append-only ledger
  to add a row is the failure the format exists to prevent.
- **It belongs in `.artifacts/` because a replay regenerates it.** The *report* is evidence and is
  tracked (§7). That is `claude_memories/artifact-locality.md`'s regenerable-vs-evidence line, not
  a size judgement.
- **Idempotency is the engine's, not the ledger's.** `signal_id` is deterministic and clock-free
  (`stoic/emission.py` convention 5), so a longer frame re-derives the same ids and the runner
  appends only ids it has not seen. This is what makes "no row lost or duplicated" a property of the
  design rather than of a lock.
- **The frame start is pinned in its own `frame` row, one per `(instrument, timeframe)`** — not in
  the header, because one Type's ledger holds more than one instrument. Warm-up decides emissions —
  a frame needs 50 bars before any signal passes and 200 before any signal passes on a fast chart
  (`stoic/gating.py`'s conventions, symmetric since **D-31**) — so a different start can renumber
  history. A run whose frame start disagrees is **refused before the replay begins**, exit non-zero,
  both values named. Same disposition as Phase 6's Gate 0: a disagreement is a bug in the request.
- **`suppressed` and `break_even` rows need their own idempotency keys**, because neither carries a
  `signal_id` that identifies it: a `SUPPRESSED` row has no `SignalRecord` at all (Phase 6 §4), and
  a `BREAK_EVEN` row's `signal_id` names the signal it links to, not itself. **Both keys carry the
  instrument**: `(instrument, pos, direction)` and `(instrument, pos, direction, signal_id)`. `pos`
  is a frame-relative index into a *per-instrument* frame while one Type's ledger holds several
  instruments — the same reason the frame start is pinned per `(instrument, timeframe)`. The first
  build omitted it, and NQ then ES into one file would have dropped every ES suppression whose
  `(pos, direction)` matched an NQ one.
- **Duplicate detection covers every row kind, not just `signal`.** A duplicate absorbed silently
  into a set is a lost row that reports as success, which is the one thing the exit gate exists to
  rule out.

## 6. Resume and progress

`CLAUDE.md`'s standing directive: a long run picks up where it left off and reports time taken and
time left.

- **The ledger is the state.** On start the runner folds it to rebuild open trades, then replays.
- **A watermark row** records the last bar processed per `(instrument, timeframe, type)`. Per
  `coding_rules.md`, resumability is gated on **disk state, not a status flag** — the watermark is
  a fast path, and the fold is the truth.
- Progress is **per stage, not per bar, and that is a consequence of §7 rather than a shortfall.**
  Both replays are single whole-frame calls with no per-bar hook, and adding one would be the second
  bar loop §7 forbids. So the runner prints bars total / already recorded / new this run, then
  elapsed per stage — load, slice, prep, L2, L5, tracking, ledger. Timings cover work done **in the
  current run only** (`coding_rules.md`).

**The driver runs 5m Types only, and refuses the others rather than resampling them wrong.** §9 /
**D-7** puts Swing on the 60m and Position on the Daily; the driver resamples to 5m, so `--type
swing` and `--type position` exit non-zero naming the mismatch. `stoic/tracking.py` itself is
frame-agnostic — it infers the bar span from the index — so the limit is the driver's, not the
measurement's, and lifting it is a driver change.

## 7. Architecture

The shape is Phase 6's, which is the shape that worked: **one pure module, one driver.**

| | |
|---|---|
| `stoic/tracking.py` | Pure. Takes the L2 and L5 replay frames plus the 5m and 1m bars; returns one row per emitted `SIGNAL` with its outcome, exit bar, exit price and flags. No disk I/O, no network, no clock read, no model, no threshold. Never imported by L0–L5 — pinned by an import-direction test, as `stoic/fidelity.py` is |
| `scripts/forward_test.py` | The driver. Owns every side effect: reads bars, runs `stoic.sequence.replay` and `stoic.emission.replay_signals` over the same frame, folds and appends the ledger, writes the report, prints progress |
| `docs/evidence/phase7_forward_test_<instrument>_<type>.md` | The report — counts per outcome class, the ambiguous and flagged rows named individually, and the open trades carried forward. **The instrument and Type are in the filename because they are what the file is about**: one fixed path means a `--type day` run silently destroys the Scalp evidence in place |

**Two replays, and L3's is not one of them.** Everything tracking needs about a filled trade —
`fill_pos`, `fill`, `stop`, `tp1`, `r`, `direction`, `signal_id` — is already on L5's `SIGNAL` row,
and L5's `BREAK_EVEN` row carries the `signal_id` it links to (`stoic/emission.py` convention 4).
The one fact L5 does not carry is the §5.4.7 invalidation, and that is **L2's** event, not L3's (§1).
Reading L3 for either would be reaching past the layer that already owns the fact. Both replays are
flattenings of the same `iter_replay_steps` pass, which stays the one implementation of the per-bar
loop — no second bar loop is written anywhere in this phase.

## 8. The report

Generated, never hand-written. Counts per outcome class per Type and instrument; the `ambiguous`
rows and every flagged row listed individually; open trades carried forward with their age. **An
`ambiguous` row is named by its *entry* bar** — it has no exit bar by construction (§2: closed, at
no recorded price), and printing a blank there would read as a missing value rather than as the
finding it is. **No expectancy, no win rate, no average R, no drawdown** — those are Phase 9's, they
measure something this phase is not asking, and `CLAUDE.md` forbids concluding from small n. A
reader who wants to know whether the method works must be unable to get it from this file.

## 9. Exit gate

`docs/PLAN.md`'s, unchanged: **a signal emitted on one run is tracked to a closed outcome on a later
run, across a process restart, with no row lost or duplicated.** Tested as a real process boundary,
not a function call in one interpreter.

Every gate gets a **negative control** (`coding_rules.md`): duplicate a ledger row and confirm the
fold reports it; truncate the tail mid-line and confirm the fold recovers; move the frame start and
confirm the run is refused; **append after a torn tail** and confirm nothing is swallowed, which is
the step the first build's torn-tail test never took and the step that failed.

**A control that cannot fail is worse than no control**, because it reports as coverage. The first
build shipped two: an assertion that an `isoformat()` was not the empty string, and a count of an
`Outcome` member no code path could construct. Both passed whatever the code did. When a test pins
something at zero, say which producer it is observing.

## What this phase does not do

Each one is named so it is not built by accident.

- **No live Databento, no Drive, no multi-writer reconciliation, no watchdog** — Phase 7b, and it is
  required before any trade is placed off the system.
- **No signal generation, and no change to L0–L5.** If tracking seems to need a rule the engine does
  not emit, that is a finding for `docs/STATE.md`, not an edit to a layer.
- **No partial sizing and no TP2** (**O-7**, §6.2's anchors unpinned).
- **No expectancy, win rate, average R or drawdown** (Phase 9).
- **No tolerance and no threshold** in `stoic/tracking.py` (`docs/CONSTRAINTS.md`).
- **No tracking of `SUPPRESSED`** — recorded, never traded.
- **No verdicts.** Counts per class, and nothing projected past the instances measured.
