# Phase 6 — fidelity measurement

**Design, agreed 2026-08-11.** `docs/PLAN.md` Phase 6 is the charter; this file is how it gets
built. It does not restate a rule from `docs/RULEBOOK.md` — open the section it names.

The question is `CLAUDE.md`'s and only `CLAUDE.md`'s: **does our implementation generate the trades
the method calls for.** Never whether the method has an edge. A divergence is a specification bug in
the engine or a missing rule in `docs/RULEBOOK.md`, and this phase's job is to find which — not to
score the strategy.

`docs/PHASE3.md` deferred two things to here by name: **the matching rule and any tolerance.** Both
are settled below, and the settlement is that there is no tolerance.

## 1. What the label set actually looks like

Read the four files before the code. Two properties of them shape everything here, and both were
measured off the files rather than assumed.

**The labels are not one schema.** `docs/PHASE3.md` §2 shows a specimen, not a contract. In the
labelled set:

| | |
|---|---|
| `ptb: null` | `LT34-M1`, `LT34-M2`, `T-A1` — no trigger exists to compare against |
| `ptb.trigger.bars` | `LT-A1`, `NQ3-A1`, `T-A2`, `T-B1` |
| `ptb.by_rule.trigger` | `LT34-A1` — and a second, disagreeing `ptb.drawn_level` beside it |
| `tp1: null` | five of the eight `taken` labels |
| `stop.by_ptb_extreme` absent | `T-A1`, `LT34-M1`, `LT34-M2` — only `by_r_label` is present |

A reconciler that assumes a shape scores nothing and reports success. §2 is the answer.

**Two comparisons look available and are not.**

- **R is not R.** The engine's `r` is a **point distance**, `|fill − stop|` fixed at fill (§5.4.2,
  **D-18**). A label's `r_label` is an **outcome multiple** off the printed chart text. They are
  different quantities. The comparable thing is the **stop distance in points**, and the R multiple
  is scored nowhere.
- **Fill price is unscoreable across this set.** Every fixture but `NQ3` is **MNQ**
  (`chart_instrument`), and `docs/PHASE3.md` §2 says a few points of MNQ-against-NQ disagreement is
  the contract, not the engine. `NQ3` is the one E-mini fixture and its `entry.price` is `null`. So
  fill price is reported as informational and never as a delta anyone reasons from. The **bar** is
  the comparable object; the label's own `entry.bar` OHLC is already our NQ bar.

## 2. Label preparation — additive, and committed before any run

Each label gains one `phase6_scope` block. It does two jobs: it names what may be scored, and it
**points at which existing field is the reference**. It adds no reading — the reading stays in the
Phase 3 field it already lives in, and `from:` names that field's path.

```yaml
phase6_scope:                       # T-A2
  entry_bar: {ts: 2026-07-31T14:55:00Z, from: entry.pos_ts, provenance: exact}
  trigger:   {price: 28289.75, from: ptb.trigger.bars, provenance: read}
  stop:      {price: 28345.50, from: stop.by_ptb_extreme.price, provenance: derived}
  tp1:       null                   # count numerals do not resolve to bars — see count_numerals
  never:     [exit, outcome]
  why: "the +1R exit is a discretionary stop move (PTBV @ 01:26:50), not §5.4.5 / D-25"
```

Rules for the block, and each has a reason outside this file:

- **Additive only.** No existing field is edited, reordered or removed. A `phase6_scope` that
  disagrees with the field it points at is a bug in the block, never a correction to the label.
- **Committed before the first engine run, as its own commit.** The diff then proves the scope
  predates the output. `docs/PHASE3.md` forbids labels fitted to the engine; this is the mechanism
  that keeps that true in the phase that runs the engine.
- **`stop.by_r_label` is never a reference.** `docs/CONSTRAINTS.md` — the dollar recovery is a
  suggestion and a `by_r_label` distance may never contradict §5.4.1 / **D-18**. It rides along as
  an informational column so the report keeps both readings visible, exactly as the labels do.
  Where a label carries **only** `by_r_label`, `stop:` in the block is `null` and the stop is
  **unscoreable**, which is a limit of the artifact and not a divergence.
- **A `null` entry means unscoreable, and the report says so.** Absent is not passing.
- **`never:` is transcribed from the label's own prose**, which already carries it: `LT3`/`LT4`'s
  `type.note` (*"do NOT score the exit"*), `2026-07-31_T1_T2.yaml`'s
  `ptbv_narration.management_observed.disposition`, `NQ3-A1`'s `outcome.note`. The block moves it
  from prose to a field; it does not decide anything new.

## 3. The run

One continuous pass. `docs/STATE.md` records the engine has no session awareness — `stoic/sequence.py`
never resets at a session boundary — so the bars fed in are a real parameter and a per-session run
would start the state machine cold in a way live never is.

| | |
|---|---|
| Instrument / frame | `NQ`, `5m` |
| Window | `2026-06-22` → `2026-08-04` — **8,784 bars** |
| Type | `SignalType.SCALP` — `setup_tf="5m"`, `fast_chart=True` (§9, **D-7**) |
| HTF | `htf=None` |
| Judgment | `decided_judgment()` — every predicate at its **D-29** / **D-30** / **D-34** default |

**Why that window starts on 2026-06-22.** The `2026-06-11` → `2026-06-19` hole (`docs/STATE.md`
Open) sits immediately before it, at as low as 9 bars of 1,380. Starting after it means the run
never crosses a known hole and needs no exclusion rule. It also clears L4's warm-up with room —
`stoic/gating.py` needs 50 bars before any signal passes and 200 before any long does on a fast
chart, and the window opens more than 20 sessions before the first label.

**Why Scalp for all four sessions.** Every fixture is a 5m chart. `LT3`/`LT4`'s label records
`type.reproducible_as: null` — §9's table has no Type that is both 5m and held past the 13:58 PT
flatten — so Scalp is the Type that instantiates the sequence, and the exit that no Type reproduces
is excluded by that label's `never:` list rather than by choosing a Type to accommodate it.

**Why `htf=None`.** No `HtfAlignment` implementation exists. Building one is L5 work — running L2 on
the 15m — and it changes nothing this phase measures: confluence **scores and never gates**
(§7.5.5, **D-27**), so it cannot change whether a signal fires, and no label carries a confidence
value to reconcile against. The consequence is stated in the report preamble rather than hidden:
every emitted signal tops out at **2 of 3**, which is **D-32**'s recorded consequence on a fast
chart, not a finding.

**Both replays run over the same frame.** `replay_signals` emits only on a fill, so a `named` or
`no_opportunity` label — where the correct engine behaviour may be *no emission at all* — has
nothing to pair with. `replay_entries` carries the L3 lifecycle (`PTB_ANCHORED`, `ENTRY_FILLED`,
`ORDER_CANCELLED`, `ORDER_VOIDED`) that those two classes need. Two passes over 8,784 bars, both
deterministic, neither modifying `stoic/entry.py`.

## 4. The matching rule

**Exact bar. No tolerance anywhere.** The user's call, 2026-08-11. A tolerance invented inside the
measurement layer is the failure `claude_memories/audit-hard-rules-not-in-material.md` names, and
`docs/PHASE3.md` forbids one by name. An off-by-one is therefore a divergence — and it is
*characterised* rather than merely counted, per the last row below.

| Class | Pairs on | What a divergence is |
|---|---|---|
| `taken` | `SIGNAL` or `SUPPRESSED`, same direction, emission `ts` **==** `phase6_scope.entry_bar` | no emission on that bar |
| `named` | L3 `PTB_ANCHORED`, same direction, anchor bar **==** `ptb.pos_ts` | the engine never saw the setup |
| `no_opportunity` | the L3 order lifecycle from its anchor bar | **any fill** while that order is live |

`replay_signals` puts the fill bar in `ts` on both `SIGNAL` and `SUPPRESSED`, so `ts` is the bar
compared.

- **`SUPPRESSED` counts as a match.** It is a fill L4 gated away, so the engine *did* generate the
  trade and then blocked it. That is a different finding from not generating it, and collapsing the
  two hides which rule is at fault. The report keeps `blocked_by` on the row.
- **A `SUPPRESSED` row carries no prices**, by design: `stoic/emission.py` builds no `SignalRecord`
  for one, so `trigger`, `fill`, `stop`, `r` and `tp1` are all null on it. The harness recovers them
  by joining to L3's `ENTRY_FILLED` record at the same bar and direction — which is the second
  reason both replays run, and the reason a suppressed match still produces a full row of deltas
  rather than a bar and nothing else.
- **An engine fill against a `named` label is correct-but-not-taken, never a false positive** —
  `docs/PHASE3.md` §2. `LT-B1` carries `would_trigger_on`, so a fill there is expected.
- **`PTBV30-N1` is the one class where absence is the right answer and the bars can settle it.** Its
  own `phase_6_expectation` field states it: identify the setup, emit no fill. Scoring it needs no
  window — the order's own lifetime, anchor to cancellation, is the interval.
- **An unmatched `taken` label is reported with its nearest same-direction emission in the session
  and the signed Δ in bars.** A miss by one bar and a miss by forty are different facts, and the
  triage in §2 of the report cannot be written without knowing which.

**One pairing is circular and is flagged as such.** `NQ3-A1`'s `entry.pos_ts` is
`provenance: derived`, computed by the labeller as *"first bar trading above the 28,597.50
trigger"* — §5.2.4, the same rule the engine applies. A match there tests the labeller's
arithmetic, not the engine. The report marks the row **circular** and draws nothing from it.

## 5. Architecture

`stoic/` holds pure functions with hermetic tests; `scripts/` holds I/O. The pairing rule is the
measurement instrument, so it is the part that must be tested — which is what puts it in `stoic/`.

| | |
|---|---|
| `stoic/fidelity.py` | Pure. Loads nothing. Pairs labels to records per §4 and computes signed deltas on scoped fields only. **Holds no threshold and no tolerance** — exact bar equality needs no number. Never imported by L0–L5 |
| `scripts/reconcile_labels.py` | The driver. Reads the four label YAMLs and the bars, runs both replays, writes the report and the raw rows. Follows `scripts/check_bar_spine.py`'s contract: literal output, per-stage timings |
| `tests/test_fidelity.py` | Hand-built label and record fixtures, one per class; a negative control; the import-direction test |

**`stoic/fidelity.py` is measurement, not signal.** `VISION.md` puts the deterministic signal path
in `stoic/`, and a measurement module living beside it must never be reachable from it. A test
parses the imports of every other `stoic/*.py` and asserts none names `fidelity`. That is the
structural equivalent of the negative control `coding_rules.md` asks of a gate: it fails loudly if
the direction of dependence ever inverts.

## 6. The report

`docs/evidence/phase6_reconciliation.md`, **tracked** — Phase 6 cites it, so it is evidence, not a
run artifact (`claude_memories/artifact-locality.md`). Raw rows go to `.artifacts/`, gitignored.

**Preamble.** The run parameters of §3 as literals, the `htf=None` 2-of-3 cap, the two known data
holes and why the window avoids them, and L4's warm-up cost.

**§1 — per-label reconciliation.** One row per label. Matched or unmatched, then signed deltas on
the scoped fields only: Δbars, Δtrigger, Δstop, Δstop-distance, ΔTP1. An unscoreable field prints
as unscoreable with its reason, never as a blank that reads like agreement. `NQ3-A1` carries its
**circular** flag. `SUPPRESSED` rows carry `blocked_by`.

**§2 — divergences.** One entry each, **hand-written**. The harness never triages; `docs/PLAN.md`'s
exit gate asks for divergences *explained*, and an explanation is a reading of the artifact.
Each is one of: a **specification bug in the engine**, a **missing rule in `docs/RULEBOOK.md`**, or
**out of v1 scope** — and the third names the row that already put it out of scope, so it cannot
become a place to file inconvenient results.

**§3 — unlabelled emissions.** Every emission inside a label session that no label pairs with:
count, bar, direction, trigger, fill, stop, R. Carrying, in the section heading, the statement that
**the label set is not exhaustive, so none of these is a false positive.** The four charts record
what the trader took and named, never every setup the session offered. The list is what a later
exhaustive labelling pass would be checked against; it is not a rate and no rate is computed from
it.

## 7. Exit gate

Divergences are **explained, not counted** (`docs/PLAN.md`). Report counts, never verdicts; never
project direction; never conclude from small *n* — every fixture here is one session, and there are
four.

## What this phase does not do

- **No tolerance, no threshold, no rate, no verdict.** §4 is exact-bar by decision. `stoic/judgment.py`
  remains the only module in the repo holding a number (`docs/CONSTRAINTS.md`).
- **No edits to `docs/RULEBOOK.md`.** Not §1–§9, not §10, not a new D-row. A divergence is an
  observation; what to do about it is the user's call, and §10 in particular takes no reasoning of
  ours (`docs/CONSTRAINTS.md`).
- **No change to any Phase 3 reading.** `phase6_scope` is additive and points at readings that
  already exist. A label that turns out to be wrong is reported as a divergence and fixed by the
  user, not silently re-read to make the engine agree.
- **No HTF aligner, no TP2, no outcome or exit scoring** where a label's `never:` list forbids it —
  which is `LT3`/`LT4`'s exit, `T-A2`'s +1R stop move, and `NQ3-A1`'s open position.
- **No engine change.** If a divergence is a spec bug, this phase reports it. Fixing it is a
  separate change against a rulebook section, with the register entry that requires.
- **No ledger, no flatten, no outcome tracking.** That is Phase 7.
