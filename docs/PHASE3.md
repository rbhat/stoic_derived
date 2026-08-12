# Phase 3 — the labelled reference set

**Design, agreed 2026-08-10.** `docs/PLAN.md` Phase 3 is the charter; this file is how it gets
built. It does not restate a rule from `docs/RULEBOOK.md` — open the section it names.

Phase 6 measures fidelity against this set. Without it, `docs/PLAN.md` says the project is
unfalsifiable, and `docs/STATE.md` says the Phase 5 engine can execute but cannot report.

## The finding that reshaped the phase

**Every marked chart in `docs/RULEBOOK.md` §10 is from a session our bars did not cover.** Read off
the source artifacts, not off our own output:

| Artifact | What it prints | Reading |
|---|---|---|
| `PTBV` keyframe `0399_005323.jpg` | crosshair `Thu 30 Jul '26 02:05 PM`, clock `03:14:52 PM UTC-4` | the session is **2026-07-30** |
| `LT4` | x-axis day separator `31` at the right edge; `PWC 28,306.75` | the session is the **30th**; same PWC as `PTBV`, so the same week |
| `T2` | `Jun LCOM 28,473.81` | a June close below anything in our June |
| `NQ3` | `Jun LCOM ~28,471`, `PDH 28,716.75` | same era |
| `data/historical/NQ_1m.parquet` | ends **2026-06-10 16:44 UTC**; June's lowest close through Jun 10 is **28,752.00** | an LCOM of 28,471 needs a close after our data ends |

**An earlier note claimed both that the charts were May–June 2026 and that the SMA fingerprint
does not work. Both were wrong, and the lesson is
`claude_memories/negative-result-over-an-incomplete-range.md`.** The dating came from a scan that
could only see up to 2026-06-10; the price band recurs at the edge of the data and continues past
it. And matching printed moving averages was the wrong handle: the plotted indicator values
are not tick-valid (`28,540.74`, `28,473.81`) and shift with the contract roll, which is why the
closest fit in seven years was 41 points off.

**The handle that works is printed daily and weekly levels, and exact execution prices.** Week of
2026-07-20→24 last close is **28,306.50** in the bars; `LT4` and `PTBV` both print **PWC 28,306.75**
— one tick. `T2`'s band (~28,075–28,750) puts it at the **2026-07-31** session (28,079.75–28,725.75)
— that is **one** agreement on a pixel-read range, so it is a candidate, not a dated fixture, until
step 2 below finds a second one from exact text.

## 1. Bars — the prerequisite

The gap is filled from `~/dev/trading_signal/data/signals.db`, the live signal system's capture. The
Databento API key on this machine is for the live feed only, not historical.

- Table `bars`, `interval_s = 60`, `ts_event` in **nanoseconds UTC**, bar-start — the same
  convention as our parquet. In the overlap, `only-db = 0`: every DB timestamp is one of ours.
- Coverage is ragged during the DB's own bring-up and clean after it:

  | Window | 1m coverage |
  |---|---|
  | 2026-06-04 → 06-19 | 12%–100%, with 06-19 at **0.7%** |
  | 2026-06-22 → 2026-08-07 | **essentially 100% every session**, 2026-07-30 at 1380/1380 |
  | 2026-08-10 | 64% (partial day, live) |

- Overlap disagreement, NQ, 3,240 common bars: **25 rows differ**. Two classes — a ±1-trade boundary
  attribution (`claude_memories/databento-ohlcv-buckets-by-ts-recv.md`), and **feed dropouts**, e.g.
  2026-06-08 15:29 carries volume 1,936 in ours against 84 in the DB. **All 25 sit inside the
  bring-up window.**

**`scripts/merge_signal_bars.py`**, following `scripts/normalize_historical_bars.py`'s contract:
idempotent, reads only immutable inputs, atomic rewrite, per-stage timings.

- Our parquet is **authoritative on the overlap**. Only bars strictly after its last timestamp are
  appended.
- The overlap is a **reported check, not an input**: every mismatching bar is printed with both
  readings. It does not fail the run — unlike the Databento tail pull, this source is known lossy,
  so the check informs rather than gates.
- `scripts/check_bar_spine.py` re-runs afterwards. Gates A–E must still pass.

**2026-06-11 → 2026-06-19 is recorded as a known hole**, the same disposition as the 2025-11-28
outage: real missing data, the caller excludes or flags it, the function cannot detect it. **No
fixture falls in it** — every one dates to 2026-06-22 or later.

## 2. What a label is

`docs/evidence/labels/<session>.yaml`, **tracked**. Phase 6 cites these, so they are evidence, not
run artifacts — `claude_memories/artifact-locality.md`.

Three classes, and the second and third are the point:

- **`taken`** — a trade the trader executed. Exact prices, exact outcome.
- **`named`** — a setup he names on screen or in narration and **declines**. He could have taken
  it and chose not to.
- **`no_opportunity`** — a setup he **wanted** and the market never triggered. Added by the user
  on 2026-08-10 for `PTBV30-N1`, where a working buy stop was placed and price failed back below
  before reaching it. *"The market never gave us a chance to take the trade — will happen quite
  frequently. We don't mark it as a trade."*

An engine signal matching a `named` label is **correct but not taken**, not a false positive.
`PTBV` is full of these. Without the class, Phase 6 cannot tell *the engine invented a setup* from
*the trader declined a real one*, and `CLAUDE.md`'s rule that divergence is a specification bug
would bias every such case toward a false alarm.

**`no_opportunity` is not a weaker `named` — it scores differently, and more sharply.** A `named`
label says nothing about what the bars did, so Phase 6 can only check that the engine saw the
setup. A `no_opportunity` label says the bars **never traded through the trigger**, so the engine
is required to emit *no fill*: identifying the setup is correct, emitting a fill is a real
divergence. It is the one class where the absence of a signal is the right answer and is checkable
against the bars rather than against narration.

Every field carries its provenance. A field never gets a value without one:

| Provenance | Meaning |
|---|---|
| `exact` | read off printed text — an execution price, a level tag |
| `read` | read off pixels, ±10 points |
| `derived` | computed from a cited rule, with the rule named |

```yaml
fixture: LT3/LT4
session: 2026-07-30          # CME trading day
instrument: NQ               # our bars
chart_instrument: MNQ        # prints differ by a few points — not an engine divergence
timeframe: 5m
type: Swing                  # LT4 is held past the 13:58 PT flatten — docs/STATE.md open row
dating:
  - {field: PWC, chart: 28306.75, bars: 28306.50, source: "LT4 right-axis tag"}
  - {field: session_high, chart: ~28414, bars: 28414.50, source: "LT4 candles"}
labels:
  - id: LT4-A1
    class: taken
    direction: long
    step1: {pos: <i>, ts: <utc>, provenance: read}
    step2: {pos: <i>, ts: <utc>, provenance: read}
    step3: {pos: <i>, ts: <utc>, provenance: read}
    ptb_level: {chart: 28245, bars: <bar high>, provenance: read}
    entry:   {price: 28244.42, provenance: exact, source: "LT4 execution text"}
    stop:    {price: 28205.9, provenance: derived, basis: "§10.10 — 173.08 ÷ 4.5R = 38.5 pt"}
    tp1:     {price: <step3 extreme>, provenance: read}
    outcome: {exit: 28417.50, r: 4.5, provenance: exact, past_flatten: true}
```

`chart_instrument` is load-bearing. `NQ3` is the E-mini; `T1`, `T2`, `LT`, `LT3`, `LT4` are the
Micro. Our bars are NQ. A few points of disagreement between an MNQ print and an NQ bar is the
contract, not the engine, and Phase 6 must not triage it as a divergence.

`type` is load-bearing for `LT3`/`LT4` for the reason `docs/STATE.md` already gives: the trade is
held past the 13:58 Pacific flatten, so it is only reproducible as a Swing or Position Type.

**There is no `scripts/verify_labels.py`.** It was designed and cut on 2026-08-10 to reach a first
labelled set sooner. The consequence, stated once: **nothing re-checks a label when the bars or a
reading change**, so a stale label will present in Phase 6 as an engine divergence. The provenance
fields keep the information a verifier would have used; only the automation is absent.

## 3. Scope

**Replayable NQ/ES only.** The §10 marked charts — `NQ3`, `T1`/`T2`, `LT`, `LT3`/`LT4` — plus
`PTBV`. All NQ/ES, all now inside the bars, every label carrying a real timestamp and bar index.

**`PTBV` is two sessions, and this line used to say "`PTBV`'s full 2026-07-30 session".** Measured
2026-08-10: the video is a cut of **2026-07-30** (video 00:00 → ~01:05) and **2026-07-31** (~01:06
→ 01:37:54), the clock jumping backward from 16:06:53 to 09:27:07 at the seam. The second segment
is **`T1`/`T2`'s session narrated live** and ends 34 seconds before `T2`'s screenshot bar. See
`docs/evidence/ptbv_session_map.md`. Two consequences:

- `PTBV` gets **no YAML of its own**. Its labels go into the two session files that already exist,
  because §2 puts one YAML per session.
- A `PTBV` execution reconciles against **both** `2026-07-30_LT3_LT4.yaml` (`LT34-A1`/`M1`/`M2`)
  **and** `2026-07-31_T1_T2.yaml`. Reconciling against only the first is the `DIA-P` double-count
  in a new place.

Out of scope for v1, and each for its own reason:

- **The narrated-only examples** — `M1 @ 17:04`–`21:21` including its negative case, `SCALP @
  25:59`–`27:21`, `DISC` + `Q1.png`. No prices and no dates, so they cannot be replayed. They are a
  separate label class if Phase 6 needs one.
- **The case-study PDFs** in `edu/resources/`. BTC, GC, RTY and GBP/JPY; we have no bars for them.
  `docs/PLAN.md` already says to split the set rather than discover this during Phase 6.

Cite the pairs as one instance, never two: `T1`/`T2` are one session (§10.2, §10.8), `LT3`/`LT4` are
one trade (§10.9). Double-counting them is the error `docs/AUDIT-2a.md` F-1 caught for `DIA-P`.

## 4. Order of work

1. **Merge the bars.** `scripts/merge_signal_bars.py`, then `scripts/check_bar_spine.py`.
2. **Date every fixture.** Two independent `exact` agreements each. A fixture that will not date is
   recorded **undated** — never guessed, and never dated off a moving average.
3. **Label class `taken`** from exact execution text, resolving each mark to a bar index.
4. **Label class `named`** from `PTBV`'s transcript and keyframes, **written incrementally** —
   `claude_memories/long-research-tasks-write-incrementally.md`. That memory was overridden once
   here, on 2026-08-10, by dispatching the keyframe-clock map to a subagent; it died on a session
   limit having written nothing, the fourth such loss.

   **How a narrated setup gets a bar, and it is not by interpolation.** Video time does not map
   linearly to wall clock — `PTBV` cuts, and video 00:34:58 → 00:44:58 spans 2h37m. Read the
   TradingView clock (`HH:MM:SS AM|PM UTC-4`, EDT) off the **nearest keyframe**, at
   `y ∈ [1032, 1062]`, scanning `x ∈ [1100, 1900]` — **its x shifts with the right-hand order
   panel**, and a fixed crop reads a present clock as absent. Floor to the 5m frame for the bar.
   That is `provenance: exact`. A crosshair label (`Thu 30 Jul '26 02:05 PM`) names the bar he is
   pointing AT, which is the other exact handle when the mouse is over the chart.
5. **Update `docs/STATE.md` and `docs/CONSTRAINTS.md`.**

## 5. Exit gate

Report the label count **per class and per session**, and the count of fixtures that would not date.
`docs/PLAN.md` forbids setting a target count in advance, and `CLAUDE.md` forbids reading the count
as evidence of anything on its own. Small *n* applies to every fixture here — each is one session.

## What this phase does not do

- **No engine run against the labels.** That is Phase 6, and doing it here would let the labels be
  fitted to the output.
- **No matching rule or tolerance.** Also Phase 6. A tolerance invented inside the measurement layer
  is the failure `claude_memories/audit-hard-rules-not-in-material.md` names.
- **No edits to `docs/RULEBOOK.md` §1–§9**, and no new D-rows. A label is an observation of the
  material, not a decision about it.
- **No SLM.** `docs/PLAN.md` Phase 4 lists label proposals as its work; it is not on this path and
  is not blocking.
