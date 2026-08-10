# Current state — what is true right now

**Phases 0, 1 and 2a are complete. Phase 2's deliverable — `docs/RULEBOOK.md` — is written and its
register is closed: nothing in §12 blocks Phase 5.** The last blocker, **O-14** (where the
post-Step-3 expansion leg ends), closed on 2026-08-08 as **D-28**, so **L1, L3 and L4** all compile.
Phase 2's exit gate names a *two-reader* test that has never actually been run — the register being
closed is not the same claim, so do not report that gate as met.

**Phase 5's engine is built end to end as code: L0, L1, L2, L3, L4 and L5 all exist — and as of
2026-08-09 it runs.** Baseline: `pytest` **240 passed**, `scripts/verify_citations.py` **222
citations across 8 sources, all resolve**, negative control PASS.

**The engine has now produced signals from market data.** `find_base` — L2's last injected
predicate — was decided on 2026-08-09 as **D-34**, which filled the last seam and made
`decided_judgment()` complete. First run over **NQ 5m, 2026-05-01 → 2026-06-10** (7,785 bars,
Scalp, `htf=None`): **389 emission rows — 210 `SIGNAL`, 43 `SUPPRESSED`, 136 `BREAK_EVEN`**. An
earlier run of the same window reported 246 signals; **review found a bug the same day** — a run of
inside candles could be a base on its own (96 of 413 selected bases were entirely inside candles),
which is the *"there could be inside bars and then it continues"* case read as a Step 2. D-34's floor
now counts **non-inside** candles. The 246 figure is superseded, not a second measurement.
The split is 131 bullish / 79 bearish. **Reported as counts, not as a verdict**, per `CLAUDE.md`:
nothing here says the signals are the right ones, and Phase 3's labelled set is what would
say so. Every layer's *unit* tests remain hand-built fixtures.

**Phase 3 started on 2026-08-10 and is partly built. `docs/PHASE3.md` is its design — read it
before touching a label.** What is done: the bar spine now reaches **2026-08-10**, all five §10
fixtures are **dated**, and **all four marked-chart fixtures** are **labelled** — `LT`, `NQ3`,
`T1`/`T2` and `LT3`/`LT4`. **8 `taken` labels and 1 `named` across 4 sessions.** What is not: the
`PTBV` class-`named` pass, and this file's own sibling `docs/CONSTRAINTS.md` rows for the rest.

**`LT3`/`LT4` is labelled, and it carries more than §10.9 lists.** §10.9 describes one trade; `LT3`
carries four further execution marks — the morning round trips — so the fixture holds **three**
`taken` labels. Three findings came out of it, none of them a decision:

- **The drawn boundary is the base's `high`, not its highest close, and that bears on D-30.** The
  unlabelled line spanning 13:15 → 15:00 measures **28,208.51** / **28,208.59** on the two
  snapshots; the base's highest **high** is 28,208.50 and its highest **close** is 28,203.00. The
  fit resolves levels to ~0.5 points here (`PLOW` 0.00, `PWC` 0.31, `PDH` 0.54), so a 5.5-point
  miss is outside it. The `ptb` line reads the same way. **One session** — an observation for
  D-30, not a change to it.
- **The fixture is reproducible under *no* v1 Type, which is stronger than §10.9's reading.** §10.9
  offers *"Swing or Position ... or not at all"*; §9's own table makes it *not at all*, because
  Swing sets up on the 60m and Position on the Daily, so neither runs a 5m sequence, while Scalp
  and Day both flatten at 13:58 PT — six hours before the exit. **The label records this so Phase 6
  scores entry, trigger and R here and never the exit or the +4.5R outcome.**
- **`LT34-M1` is only the second §10.10 row that needs no division.** 229.00 pts × 6 lots × $2 =
  **$2,748** = 2.75R, which *is* the printed **+2.8R**. It corroborates the $1,000 unit rather than
  assuming it. And on the +4.5R trade §10.10 and §5.4.1 land **1.04** points apart — second only to
  `T-B1`'s 0.99, against `LT`'s 12.25.

**How a marked chart is now read, and it is not by eye.** `T1`/`T2` was labelled by fitting the
candle comb and the price axis off the artifact itself — candle bodies are flat exact colours, so
the comb and a least-squares fit of body ends against our bars recover both axes. On `T2` that
reproduces our NQ bars to **0.92 points sd** over 146 body ends, and the fitted gridlines land on
TradingView's own printed labels. **The two snapshots were fitted independently at different zooms
and put all six executions on the same bars**, which checks the method rather than the data. It is
`scripts/fit_marked_chart.py`, and the numbers it produced are in the label file.

**The one fixture that would not fit has been fixed, and the reason it would not was misdiagnosed
for two days.** `LT3`/`LT4` reported 16.95 points sd and this file, `docs/CONSTRAINTS.md` and the
script's own docstring all blamed the **CME maintenance break** the chart spans. That was wrong:
our 5m frame holds no bars between 17:00 and 18:00 ET either, so walking `last_index - k` crosses
the break correctly and never needed changing. The real fault was the comb — **four of `LT4`'s
candles draw no body pixels** (dojis, and candles under the shaded session boxes), each leaving a
two-slot gap the `span / median_gap` seed could not see, so it searched 134–138 slots when the truth
was 139. `fit_comb` now seeds the count by counting the gaps. `LT4` fits to **0.92** pts sd over 272
body ends and `LT3` to **0.69**; **`T1`/`T2` and `NQ3` reproduce unchanged**. The tell was in the
output all along: the comb's own pixel residual was **10.79 px on a 22 px spacing** — half a candle
— and drops to 0.51 at the right slot count. It is a warning and not a gate: `T1` fits cleanly at
10.22 px on a 39 px spacing. **Read the comb residual as a fraction of the spacing, then the price
residual.**

**The finding that reshaped the phase: every §10 marked chart is a 2026-07-27 → 2026-08-03 session,
and our bars ended 2026-06-10.** Phase 3 was never blocked on labelling effort; it was blocked on
data. `scripts/merge_signal_bars.py` fills the gap from the live signal system's `signals.db`
(`~/dev/trading_signal/data/`, overridable with `$STOIC_SIGNALS_DB`) — our parquet stays
authoritative on the overlap, only bars strictly after it are appended, and appended rows carry
`source = signals_db` so provenance survives in the data itself. Gates A–E pass; **two of them
needed a real fix, not a suppression** — see the Open list.

**Two things that run confirmed, both predicted rather than discovered.** All **210** emitted
signals scored **2 of 3** confluence, which is exactly what **D-32** records as its consequence: on
a fast chart a passing gate already implies both §7.1.1 conditions, and `htf=None` leaves the third
absent with the denominator still 3. And `continuation` runs `True` in clusters, which is **D-21**
working. Neither is a finding about the method.

**All four of L2's terms are now decided.** All four were routed to Phase 4's SLM on 2026-08-09;
the human decided all four the same day, with the censuses in hand:

- **D-29 — what makes a break or a close "meaningful."** Covers *both* terms, §2.1.1 and §2.3.4,
  which the user chose to treat as **one question**. The rule: **the close must sit beyond its
  reference by ≥10% of the parent bar's high-low range** — reference being the *further* MA for
  Step 1 and the selected boundary for Step 3. Parent bar per §5.2.8a / **D-23**, not `i-1`.
- **D-30 — how the boundary is selected.** **Choosing the base determines the line:** the boundary
  is the base's **close** extreme on the Step 1 side, §2.3.1 forcing the side. Closes not wicks, on
  the §7.3 / **D-8** precedent. This is a **default, not the whole rule** — §2.2.7's sloping
  boundary is **retained** and deliberately unimplemented (**O-18**).
- **D-34 — what makes a base "obvious."** **The base is the residual state: unless price is
  trending or breaking out, it is basing.** *Trending* is two consecutive **non-inside** candles
  extending the same way against the parent bar; everything else is basing, so a **sweep that
  reverses** stays inside the base. The span is the trailing run of basing candles, it **ends at
  the candle before the one being tested**, its floor is **2 non-inside candles**, and it is
  **cancelled if the leg resumes**. §2.2.5a carries it.

**D-34 carries no number, and that is the whole of its design.** It **dropped D-3's three clauses**
rather than calibrating them — compression because a base's ranges can be about the same, MA
proximity and *breakouts inside* because **D-15**'s reset already ends the count on a close back
through both MAs. **It is not free of numbers, and the first write-up of it wrongly said so:** the
2-candle floor is a literal, and it lives as `MIN_BASE_CANDLES` in `stoic/judgment.py` beside
`MEANINGFUL_FRACTION` — named, not inlined, because an unnamed `2` is as invisible as an unnamed
`0.10`. That is also why §2.2.5a is **P** and not **M**. **Two constants in the engine, both in
`stoic/judgment.py`, both naming their §11 row.**

**D-29 and D-30's numbers are chosen, not measured.** The censuses enumerated every passage on all
four terms and **none quantifies any of them**; D-30 in particular decides a **6-to-5 split** in the
corpus that no passage addresses directly. D-34 is the same kind of choice one step further out —
it picks among rival *constructions* rather than rival numbers, and the rejected ones are named in
its §11 row so a later measurement knows what it is testing against.

**Everything decided lives in `stoic/judgment.py`, never in `stoic/sequence.py`** — the machine stays
threshold-free, and each predicate names the §11 row that authorised it.

**Three open rows, all non-blocking, all noticed rather than decided.** **O-17**: D-29 uses 10%
of the **parent** bar's range while **D-24**/§5.4.7b uses 10% of the **candle's own** — same number,
different denominator, same shape as **O-15**. **O-18**: when is a base edge a *trend line* rather
than a level? D-30's horizontal default is always available, so an implementation never has to guess
— but it may not pick the sloping case silently. **O-20**: §2.2.9's *"if two boundaries look equally
valid there is no clean step three yet"* — wait — **has no counterpart in the engine**, because a
residual base yields exactly one span per bar and two candidates can never tie. Whether that
satisfies the tie-break or silently drops it is undecided; **do not add a selector to fill it**.

**The first deliverable is a passage census, not a trained model.** The whole corpus is **66,463
words** across 9 transcripts — small enough to read whole, so fine-tuning on it would memorise
rather than discover, with no held-out set to check against. So: enumerate every passage bearing on
each of the four terms, with citations, into `docs/evidence/census_meaningful.md` and
`docs/evidence/census_base_boundary.md`. That is both the input the SLM proposes over and the eval
set for what it proposes. It may settle a term outright, or show the material never speaks to it —
which is the answer, and sends that term to the human. **Brief: `.scratch/census_brief.md`**
(gitignored, this machine only — regenerate it from this paragraph if lost).

**Both censuses are written as at 2026-08-09** — 157 citations across 9 sources, all resolve.
**No passage in either one quantifies any of the four terms.** That is what makes **D-29** and
**D-30** decisions rather than derivations. The one term neither census could quantify — the obvious
base — was not guessed either: **D-34** answered it by changing the question from *which number* to
*which construction*, which is why it needed none. Two findings that are not about the four terms: `OTV` and
`edu/derived/concept_the_only_trading_video_that_you_will_ever_need/transcript.md` are the **same
video transcribed twice** (only the first has a §0 key — the `DIA-P`/`DIA-L` failure again), and
`MS` is in `scripts/verify_citations.py`'s `SOURCES` map but missing from §0's key table. Neither is
acted on. `scripts/verify_citations.py` now takes optional paths so `docs/evidence/` can be checked;
with no argument it still scans `docs/RULEBOOK.md` alone, which is the gate and the baseline above.

**Two things that routing does not change.** The SLM **proposes; it never decides** — `VISION.md`
keeps it offline and out of the live path, and §0 says a proposed number for a **J** term *"is a
strategy decision requiring the human"*. So each proposal still lands as a **D-row in §11** with the
human's confirmation on it, exactly as **D-9** already routes the no-edge zone. And the fallback is
the human: **if the SLM cannot ground a term in the material, that term comes back for a decision —
it does not get a default.** An unfilled predicate is the correct state; an invented one is not.

The decision register is `docs/RULEBOOK.md` **§11** (closed) and **§12** (open) — nowhere else. The
table in `docs/PLAN.md` is the superseded intake form.

## What is still live from Phase 2a

Phase 2a is closed and **is not summarised here** — `docs/AUDIT-2a.md` is its record, `docs/RULEBOOK.md`
§11 holds every decision it produced, and `git log` holds the rest. Two things it left behind are
current rather than historical:

- **`docs/evidence/ptb_atr_distribution.md` is now almost entirely inert.** O-5 closed by deleting the
  ATR stop floor (**D-18**), so nothing in the spec reads its percentiles, and its `BODY` / `EXTREME`
  columns describe two readings **D-23** rejected. **One number in it still matters:** those two
  readings pick a different anchor bar on **62.8%** of candidates (NQ 5m RTH 2019–2026), which is why
  neither could be adopted quietly and why D-23 stands. It lived in the gitignored `.artifacts/` and
  did not travel between machines until 2026-08-09; it is now tracked under `docs/evidence/`.
- **The standing rule that came out of it** is `claude_memories/audit-hard-rules-not-in-material.md`,
  not a phase. The ATR floor passed every mechanical sweep because it cited a real D-row with a real
  open row; only asking the human where the predicate came from caught it.

## The material

- **`edu/123sequence/` — the main source.** The 1-2-3 sequence: 4 videos, the entry-technique
  write-up and diagrams, the concepts files, the war map, and the `discussion/` and
  `concepts/PTB Questions.md` notes from the user.
  Also `PTBV` (the `PTB Entries - NQ Live Trading 10R` video, 1h38m — the densest single source on
  §2.5 and §5.3), `TPA` (`Navigating tough price action`, 58:00 — the densest source on what a PTB is
  and is not), and the marked charts `NQ3`, `T2`, `LT3`, `LT4` and `IBD`. **`DIA-P` is byte-identical
  to `DIA-L`** — one drawing at three paths, never two sources (§0).
- **`edu/videos/` — supporting.** 3 concept videos (Candle Swing Theory, HTF Protocol, Simple Stoic
  Setups).
- **`edu/resources/` — 8 case-study PDFs.** Validation material for the rulebook, not training input.
- **`edu/derived/` — 9 complete transcript sets**, one per video, indexed by
  `edu/derived/manifest.json`.

Phase 1 produced **2** new transcript sets, not the 3 its exit gate named: the `Universal 1-2-3
Sequence` file was a byte-identical recording of `Module 1` and was removed 2026-08-01.

## Next

**`docs/PLAN.md` is the plan, end to end.**

**The critical path is Phase 3, and it is in progress. `docs/PHASE3.md` is the design; every
marked chart is labelled and work resumes at `PTBV`.** In order:

1. **`PTBV` — session 2026-07-30, the class-`named` pass.** A 1h38m narrated session where the
   trader talks through setups he does not take. This is the bulk of the remaining reading and the
   part worth delegating; judge that delegation by its **write pattern**, per
   `claude_memories/long-research-tasks-write-incrementally.md`. **It is the same session as
   `LT3`/`LT4`** — reconcile any execution it narrates against `LT34-A1`, `LT34-M1` and `LT34-M2`
   rather than adding a fourth, which is the `DIA-P` double-count in a new place.
2. **`docs/CONSTRAINTS.md`** rows for labelling, and this file's Open list as things close.

**The first question to put to the engine is still not a number, it is the base.** D-34 was chosen
among rival constructions with **no eval set** — the natural one is §10's marked charts, and those
are now dated and partly labelled, so the eval set is finally buildable. Its §11 row names the
constructions it rejected precisely so that measurement has something to test against. Treat the
389 emission rows as **output to be checked, not as evidence of anything.**

1. **Phase 5 — the rulebook engine. Complete as of 2026-08-09: every layer exists and every
   injected predicate is filled.** L0–L5 are built (tables below); **D-29**, **D-30** and **D-34**
   fill all four of L2's injected predicates, and **D-32** / **D-33** settled the two things L5
   needed that nothing had pinned.

   **No layer needed an open term and none introduced one.** `stoic/entry.py`, `stoic/gating.py` and
   `stoic/emission.py` hold no threshold — the separation `docs/CONSTRAINTS.md` names is intact,
   `stoic/judgment.py` is still the only module with a number in it. L3 consumes
   `stoic/structure.py`'s pullback (**D-28**) and `stoic/sequence.py`'s events and derives neither;
   L4 consumes nothing but bars and their SMAs; L5 consumes L3's records and L4's gate and derives
   neither.

   **`replay_entries` and `replay_signals` have now been driven over real bars** as well as
   hand-built fixtures — see the counts at the top of this file. Their **unit** tests are still
   fixtures and a stub judgment, which is the right thing for a unit test and is not a claim about
   the output.

   **L4 came out smaller than its plan row, and that is the finding, not a shortfall.** §7 was read
   end to end on 2026-08-09; read it again rather than trusting this summary. Of the four things
   `docs/PLAN.md` listed for L4, one survived contact with §7 — and **§7.4.3, the corpus's one
   *"mechanical"* no-edge statement, turned out not to be one.** `CST @ 00:22:05` names **PDC** a
   daily level 25 seconds before the rule, and PDC sits inside the PDH/PDL range by construction, so
   *strictly-between-blocks* forbids a trade the same passage licenses. The user's call was to build
   neither reading and open **O-19**. What L4 does build is the **50 SMA gate** (§7.1.2, **D-19**)
   and the **200 SMA rule** (§7.1.4), which the human made **symmetric the same day** — **D-31**, so a
   short is blocked at or above the 200 as a long is blocked at or below it, on fast charts only.
   **L5 must not re-add what L4 declined:** minimum R
   (**O-10** — record it, do not gate on it), trapped side (§7.3, **J**), the rest of §7.4.2
   (**O-9**), and §7.4.3 (**O-19**). **HTF alignment is L5's own work and is not a gate** (§7.5.5,
   **D-27** — it raises the confluence score and never blocks).

   **L5 was the last layer, and both things nothing had pinned are now settled.** §3, §5.3.10,
   §5.4.2, §6, §9 and `VISION.md`'s schema scope it — read those and `stoic/emission.py`'s docstring,
   not this summary. It emits the **signal record** in `VISION.md`'s schema, plus the field that
   schema omits — the §5.3.10 engine note requires storing **both the trigger and the fill**, because
   they differ on a gap and only the fill sets R. **R = |fill − PTB extreme|** (§5.4.2), fixed once
   at fill, no floor (**D-18**); break-even moves the **stop**, not R, so the record carries the
   break-even *event* and never a second R. **TP1 = the Step 3 High/Low frozen at fill** (§6.1,
   **D-6**, **D-16** §3.5) — L3 emits it as `step3_extreme` on `ENTRY_FILLED` and L5 reads it rather
   than re-deriving it. **Type instantiation** (§9, **D-7**) gives the setup timeframe per Type,
   Scalp and Day wholly on the 5m, and that is also what tells L4's `fast_chart` what chart it is on.

   1. **The confluence score is decided: D-33, a plain count.** The user's rule on 2026-08-09 was
      *"the rules should be present for entry"* — the inputs are the rulebook's **own
      already-specified conditions** (§7.1.1's 50 and 200 reads, §7.1.3 on the 200 as HTF trend, and
      §7.5.5 / **D-27**'s HTF confirmed Step 3), and the combination is a **count of those present,
      *k* of 3**, every flag also recorded individually. **Weights were rejected** as invented
      numbers. **Do not confuse §7.1.1 with §7.1.2** — §7.1.2 is the **gate** (**D-19**, L4's);
      §7.1.1 is the **read**, and the rulebook holds them as separate rows.

      **The bar they are read on is D-32: the PTB anchor bar, never the fill bar** — a fill is
      intrabar and the gate is a close read, so a fill-bar read is lookahead. **D-32 also records the
      consequence, which is not a bug:** on a **fast** chart a passing gate already implies both
      §7.1.1 conditions, so on Scalp and Day the score varies only with the HTF input. The three vary
      independently only on **slow** charts, where the 200 gate never fires.
   2. **TP2's fib anchors are still unpinned, and that is unchanged.** §6.2 / **D-6** give the ratio
      (2.618) and **D-20** gives the swing (Step 2, the first pullback), but a trend-extension tool
      takes **three** points and no rule pins them. L2 exposes `step1_pos`, `step2_swing_pos`,
      `step2_swing_price` and `base`, so the geometry is reachable without reaching past a layer —
      what is missing is the *reading*, not the data. **Not blocking: TP1 is fully defined**, and
      `SignalRecord.tp2` is therefore always `None` in v1.

   **What L5 must never grow, and each one is a trap:** no **minimum-R or "sufficient room" gate**
   (§5.4.6, **O-10** — `m` is unset; record R, never gate on it); no **anticipatory entry** (§5.5,
   **D-11** — it appears in the labelled material and the engine must not emit it); **climax** (§4.3)
   and the **lower-high cue** (§6.5a, **D-26**) **annotate only** — §4.3 is a hard constraint that
   neither may fire, suppress or invalidate a signal; **partial sizing** and the TP1/TP2 ordering stay
   open on **O-7**; no new gates (**O-9**, **O-19**, §7.3's **J**); **slippage stays unmodelled beyond
   the gap** (§5.3.7 engine note) and if Phase 6 finds that flattering it must change in **one**
   place; and tracking a signalled trade to its outcome, the flatten and the ledger are **Phase 7**,
   not L5.
2. **Phase 3 (labelled reference set) — started 2026-08-10, design in `docs/PHASE3.md`.** It was
   deferred by the user on 2026-08-08 — *"we will backtest once the system is on"* — and the system
   is now on. It is the evidence that would confirm or overturn **D-28** and **D-34**, and Phase 6
   cannot report fidelity without it. All are single instances, so small-*n* rules apply.

   **Scope is replayable NQ/ES only** (user's call, 2026-08-10): the §10 marked charts plus
   `PTBV`'s full session. The narrated-only examples (`M1`, `SCALP`, `DISC`+`Q1.png`) and the
   non-NQ/ES case-study PDFs are out — see `docs/PHASE3.md` §3 for why each.

   **A label is one of two classes** (user's call, same day): **`taken`**, a trade the trader
   executed, and **`named`**, a setup he names and does not take. An engine signal matching a
   `named` label is **correct-but-not-taken, never a false positive** — without the class, Phase 6
   cannot tell an invented setup from a declined one, and `CLAUDE.md`'s divergence-is-a-spec-bug
   rule would push every such case toward a false alarm.

   **There is no label verifier.** `scripts/verify_labels.py` was designed and cut the same day to
   reach a first labelled set sooner. **Nothing re-checks a label when the bars or a reading
   change**, so a stale label presents in Phase 6 as an engine divergence. The per-field
   `provenance` (`exact` / `read` / `derived`) carries what a verifier would have used.

   **§10.10 recovers the stop from any chart** — none draws one, but the R labels are normalised
   against a ~$1,000 risk unit, so `stop distance = P&L points ÷ R multiple`. **On `LT` this
   disagrees with §5.4.1's PTB extreme by 12.25 points** (85.50 vs 97.75), which is why that
   label records both readings and adopts neither.
3. **Phase 4 (the SLM) is off the critical path again, and the pattern is now three deep.** O-14
   was routed to it and the human decided it as **D-28**; L2's four terms were routed to it on
   2026-08-09 and the human decided all four the same day (**D-29**, **D-30**, **D-34**). Each time
   the routing did its job first — the census established that no passage quantifies the term — and
   what was left was a **choice**, which is the human's. That is exactly what
   `claude_memories/audit-hard-rules-not-in-material.md` says to expect; it is not the routing being
   overridden. Still Phase 4's: **O-9** (the no-edge zone, per **D-9**) and Phase 3 label proposals,
   neither blocking.

`docs/RULEBOOK.md` §13 records how the rest of the corpus is used. Simple Stoic Setups / HTF Protocol
/ Candle Swing Theory / the war map are the **complementary layer the 1-2-3 was distilled from** —
context and targets, never a step of the sequence, and they yield on conflict.

## What Phase 0 and Phase 1 built

| | |
|---|---|
| `stoic/sessions.py` | CME trading day, session phases, the 13:58 PT flatten cutoff. UTC storage, local zones only inside this module |
| `stoic/bars.py` | 1m → 5m/15m/60m/1D/1W. Pure resample, no materialised parquet |
| `scripts/check_bar_spine.py` | Gates A–E, each with literal output and a negative control |
| `scripts/build_corpus.py` | Resumable transcribe + keyframe pipeline, 4 stages, no LLM/VLM |
| `scripts/verify_citations.py` | Every `KEY @ TIMESTAMP` in `RULEBOOK.md` resolves to a real marker, with a negative control. **Its `SOURCES` map is hand-maintained and drifts** — `TPA` was missing from it for the eight days it was the newest source, so 23 real citations reported as *unknown citation key* and nobody noticed. Add the key when you add a source, and run it after editing citations |
| `scripts/measure_ptb_atr.py` | Produced `docs/evidence/ptb_atr_distribution.md`. Now inert except for its 62.8% figure — see above |
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

## Open

- **§10's three `Jun LCOM` numbers are moving-average axis tags, not levels — reported, not
  corrected.** §10.2's *28,482*, §10.8's *28,473.81* and §10.9's *28,471.53* reproduce, to 0.2
  points or better, the **200 SMA** (`T1`, `T2`) and the **10 SMA** (`LT3`/`LT4`) at each chart's own
  last bar. The **drawn** `Jun LCOM` line on `T1`/`T2` measures **28,471.6** against our
  **28,472.00**. This is the fourth instance of the §10.7 trap — a printed number on a §10 chart may
  be an indicator's axis label — and the first found **inside our own evidence**: it had propagated
  into `docs/evidence/fixture_dating.md` as a *contract drift* limit, which is now corrected there.
  **Editing §10 is the user's call.**
- **The count numerals on `T1`/`T2` do not resolve to bars, and that is measured rather than
  assumed.** The italic 1/2/3 are anchored in chart coordinates — each lands on the same bar in both
  snapshots, rendered at different zooms — but their **x-order is not the count order** (bearish:
  `1` 09:40, `3` 09:50, `2` 10:10). They are hand-placed in whitespace. So `step1`/`step2`/`step3`
  and `tp1` are **unlabelled** on all three `T1`/`T2` trades: Phase 6 can score direction, trigger,
  entry bar, R and outcome there, and cannot score the count or TP1. **Check the other fixtures for
  the same thing before trusting a step field** — `LT` and `NQ3` recorded theirs as `read` before
  this test existed. **On `LT3`/`LT4` the test was run and came out the other way:** the x-order
  *is* the count order there, `2` and `3` land on the same bar in both renders, and only `1` slips
  a bar because its glyph centre falls on a slot boundary. So the T1/T2 result is a property of
  that chart, not of the numerals in general — **run the test per fixture, conclude nothing from
  the last one.**
- **`T-B1` is the corpus's one close agreement between §10.10 and §5.4.1**, at **0.99** points
  (41.43 vs 42.42). On `LT` the same two readings disagree by **12.25**. Both fixtures record both
  readings and adopt neither, so nothing rests on this yet — but it is the first evidence that the
  disagreement is not systematic.
- **L5's `continuation` flag resets only on `RESET`, and a §5.4.7 invalidation is not one.** The
  field is False on a directional state's first candidate and True thereafter, cleared on
  `Event.RESET` — which is what **D-21** / §2.5.8 specify, since the directional state dies at the
  10/20 reset. But a §5.4.7 invalidation *also* disarms L3 without emitting a `RESET`, so the first
  entry after one is labelled a continuation. Whether the directional state should survive an
  invalidation is **not stated anywhere** — noticed, not decided, same shape as **O-15** and
  **O-17**. **Nothing depends on it:** `continuation` is a record label, and no entry, stop, R or
  target reads it. Not opened as an O-row because it is a property of the record, not of the rulebook.
- **The `T2` reading that bears on D-23 is now verified, and it holds.** On `T2`'s bullish count the
  PTB candle is **up-bodied (green)** — the 12:45 bar, `o 28,321.50 / c 28,348.00` — which makes it a
  live-marked counterexample to the `close < open` body test **D-23** rejected: evidence *for* the
  decision the user already took. The ambiguity that blocked it is gone. The drawn `ptb` tick
  measures **28,348.9** against that bar's high **28,349.75** (0.85), while the large down candle
  before it (12:40) highs at **28,371.50**, 22 points away; and the fill at **28,350.92** is 1.17
  above the 12:45 high, so a trigger at 28,371.50 could not have filled there. Settled twice over.
  **Not written into §10.8** — editing §10 is the user's call.
- **`LT4` is held past the 1:58pm Pacific flatten, and no v1 Type reproduces it.** Entry **15:55
  ET** (not 04:00 PM — that is §10.9's approximation; the arrow lands on 15:55 in both renders),
  exit 22:15 ET into the Asia session at +4.5R (§10.9). §10.9 offers *"Swing or Position ... or not
  at all"*; §9's own table makes it **not at all**, because Swing sets up on the 60m and Position on
  the Daily, so neither runs a 5m sequence, while Scalp and Day run wholly on the 5m (**D-7**) and
  both flatten at the cutoff. `docs/evidence/labels/2026-07-30_LT3_LT4.yaml` records it under
  `type:` with the consequence spelled out: **Phase 6 scores entry, trigger and R here, never the
  exit or the outcome.** Whether `VISION.md`'s Type table should carry a 5m Type that survives the
  session is the **user's call** — `VISION.md` is not ours to modify.
- **§10.7's stop for `NQ3` is in doubt, and it is not edited.** §10.7 reads *"Stop 28,540.75, the
  PTB low (§5.4.1) — box bottom"*. That value is within **0.04** of the same chart's **20 SMA**
  (28,540.70, whose right-axis label reads `28,540.74`), and the PTB bar's low is **28,529.50**. So
  the number is an indicator's axis label, and the box bottom is a pixel read. §10.10's *"no chart
  in §10 draws a stop"* is consistent with this and was the safer reading. Measured in
  `docs/evidence/fixture_dating.md`; the label file adopts no stop. **Reported, not corrected** —
  editing §10 is the user's call.
- **`2026-06-11` → `2026-06-19` is a second known data hole**, and unlike 2025-11-28 it is ours:
  those sessions come from `signals.db` while that capture was being brought up, at 12%–65% per
  session (06-19 caught **9 bars of 1,380**). From 2026-06-22 the same source runs essentially
  complete. Named in Gate E. **No §10 fixture falls in it.** Any Phase 5 replay spanning it must
  exclude or flag it, exactly as for 2025-11-28.
- **Bars after 2026-06-10 come from a live capture, not from Databento's own OHLCV.** In the
  overlap, 25 of 3,240 NQ bars disagree — a ±1-trade boundary attribution
  (`claude_memories/databento-ohlcv-buckets-by-ts-recv.md`) and outright feed dropouts, e.g.
  2026-06-08 15:29 holding volume 1,936 in ours against 84 in the capture. **All 25 sit inside the
  bring-up window.** The merge reports them rather than absorbing them; `source = signals_db` marks
  every affected row. Databento's historical API is **not** available here — the key on this
  machine is live-feed only.
- **Session `2025-11-28` has a ~645-minute hole in `data/historical/{NQ,ES}_1m.parquet`** — the whole
  Asia/London portion, both instruments. Real missing data, not a holiday early close. Any Phase 3
  label or Phase 5 replay touching that date must exclude or flag it. See
  `claude_memories/historical-bars-2025-11-28-outage.md`; Gate E reports it every run.
- **L2 has had one audit pass; the review was capped there by the user on 2026-08-09.** Everything
  that pass found is fixed. Two things it decided rather than found, recorded so they are not
  re-litigated silently: a re-break of a still-pending base emits `STEP_3_BREAK` **again** (§2.3.3,
  §2.3.7 — the sticky reading discarded all but the first), and the base may not be broken on the
  bar its own boundary was selected (§2.2.5, *"markable before the break"*), though a
  late-recognised base may.
- **`stoic/levels.py` reports a leading partial month as if it were complete.** ES/NQ daily history
  begins 2019-06-10, so June 2019 holds 15 sessions; **45 sessions per symbol** then read
  `hcom_m1`/`hcom_m2` off that truncated month with no NaN and no flag. Same class as the
  2025-11-28 hole, and the same disposition — the caller excludes or flags it, the function cannot
  detect it. A frame starting mid-week does the same to `pwc`/`pwh`/`plow`. Documented in the
  module docstring.
- `past_flatten` is 0 for every 5m bar by construction — the cutoff sits in a 2-minute window no 5m
  bar can start in. Phase 7 will need the bar *containing* the cutoff, not bars after it.

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
