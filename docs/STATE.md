# Current state — what is true right now

**Phases 0, 1 and 2a are complete. Phase 2's deliverable — `docs/RULEBOOK.md` — is written and its
register is closed: nothing in §12 blocks Phase 5.** The last blocker, **O-14** (where the
post-Step-3 expansion leg ends), closed on 2026-08-08 as **D-28**, so **L1, L3 and L4** all compile.
Phase 2's exit gate names a *two-reader* test that has never actually been run — the register being
closed is not the same claim, so do not report that gate as met.

**Phase 5 is under way: L0, L1, L2 and L3 are built.** Baseline as at 2026-08-09: `pytest`
**172 passed**, `scripts/verify_citations.py` **210 citations across 8 sources, all resolve**,
negative control PASS.

**Three of L2's four terms are decided. One is left: the obvious base.** All four were routed to
Phase 4's SLM on 2026-08-09; the human then decided three of them the same day, with the census in
hand. The split as at 2026-08-09:

- **D-29 — what makes a break or a close "meaningful."** Covers *both* terms, §2.1.1 and §2.3.4,
  which the user chose to treat as **one question**. The rule: **the close must sit beyond its
  reference by ≥10% of the parent bar's high-low range** — reference being the *further* MA for
  Step 1 and the selected boundary for Step 3. Parent bar per §5.2.8a / **D-23**, not `i-1`.
- **D-30 — how the boundary is selected.** **Choosing the base determines the line:** the boundary
  is the base's **close** extreme on the Step 1 side, §2.3.1 forcing the side. Closes not wicks, on
  the §7.3 / **D-8** precedent. This is a **default, not the whole rule** — §2.2.7's sloping
  boundary is **retained** and deliberately unimplemented (**O-18**).
- **Still open: the obvious base** (§2.2.5 **J**, **D-3** qualitative). `decided_judgment()`
  requires `find_base` as an argument and supplies no default, which is the correct state.
  **Nothing runs end to end until it is filled in.**

**Both numbers are chosen, not measured.** The censuses enumerated every passage on all four terms
and **none quantifies any of them**; D-30 in particular decides a **6-to-5 split** in the corpus that
no passage addresses directly. That is what makes them decisions rather than derivations.

**Everything decided lives in `stoic/judgment.py`, never in `stoic/sequence.py`** — the machine stays
threshold-free, and each predicate names the §11 row that authorised it.

**Two new open rows, both non-blocking, both noticed rather than decided.** **O-17**: D-29 uses 10%
of the **parent** bar's range while **D-24**/§5.4.7b uses 10% of the **candle's own** — same number,
different denominator, same shape as **O-15**. **O-18**: when is a base edge a *trend line* rather
than a level? D-30's horizontal default is always available, so an implementation never has to guess
— but it may not pick the sloping case silently.

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
**D-30** decisions rather than derivations, and it is why the one term neither covers — the obvious
base — is still unfilled rather than guessed. Two findings that are not about the four terms: `OTV` and
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

1. **Phase 5 — the rulebook engine. L3 was built on 2026-08-09 — the user's call, taken over
   deciding the obvious base first. L4 (gating) is next.** L0–L3 are built (tables below); **D-29**
   and **D-30** fill three of L2's four injected predicates.

   **L3 needed none of the open terms and introduced none.** `stoic/entry.py` holds no threshold —
   the separation `docs/CONSTRAINTS.md` names is intact, `stoic/judgment.py` is still the only module
   with a number in it. L3 consumes `stoic/structure.py`'s pullback (**D-28**) and
   `stoic/sequence.py`'s events and derives neither, per the `docs/PLAN.md` layer table.

   **What L3 does *not* unblock:** running the engine end to end still needs the **obvious base**
   (`find_base`), the last unquantified term. `replay_entries` exists and is tested, but only against
   a stub judgment; it cannot be driven over real bars until `find_base` is decided. L4 → L5 follow
   per the `docs/PLAN.md` layer table, pure functions over bars, no network and no model, each layer
   unit-tested against hand-built fixtures with a negative control per `coding_rules.md`. **L4's
   inputs are already decided** — `D-18` removed the mechanism **O-5** was blocking on, and **O-9**
   (the no-edge zone) is a filter, not a signal.
2. **Phase 3 (labelled reference set) is deferred by the user's call on 2026-08-08** — *"we will
   backtest once the system is on."* It is **not cancelled**: Phase 6 cannot report fidelity without
   it, and it is the evidence that would confirm or overturn **D-28**. It simply does not gate the
   engine. When it starts: **`T2` (§10.8) is the densest fixture** — two counts, a live-marked reset,
   two PTBs, six executions — with `NQ3` (§10.7) the cleanest single-sequence one and `LT3`/`LT4`
   (§10.9) the only trade held past the session. All are single instances, so small-*n* rules apply.
   `PTBV` is the richer source: a full session in which the trader marks every PTB entry on one
   1-2-3. **§10.10 recovers the stop from any of them** — none draws one, but the R labels are
   normalised against a ~$1,000 risk unit, so `stop distance = P&L points ÷ R multiple`.
3. **Phase 4 (the SLM) is back on the critical path.** It briefly had no blocking question — O-14
   was routed to it and the human decided it instead as **D-28**. Then **L2's four terms went to it
   on 2026-08-09**, and they gate the engine running end to end, so Phase 4 now sits between L2 and
   L3 rather than beside them. Also still its: **O-9** (the no-edge zone, per **D-9**) and Phase 3
   label proposals, both still off the critical path.

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

## What Phase 5 L0–L3 built

Pure functions over bars — no disk I/O, no network, no clock, no model. Tests are hermetic and
hand-built; the suite is 172. L2's decided predicates add 27 in `tests/test_judgment.py`, L3 adds 23
in `tests/test_entry.py`.

| | |
|---|---|
| `stoic/indicators.py` | 10/20 (sequence) and 50/200 (trend) SMAs of the close, on the frame given. Warm-up stays NaN — never `min_periods=1` |
| `stoic/candles.py` | `candle_structure` — inside-bar flags and **parent-bar** positions (§5.2.8a, **D-23**). A run of inside bars shares one parent; for a non-inside bar the parent is the nearest preceding non-inside bar, which is the reference **D-28** requires |
| `stoic/structure.py` | **L1.** `opens_pullback` / `find_pullback_start` / `leg_phases` — **D-28** (§5.2.1a): the pullback opens at the first completed candle whose **both** extremes move against the direction, measured against the parent bar. Never reads `open` or `close` (§5.3.3c) |
| `stoic/levels.py` | PDH/PDL/PDC, PWC/PWH/PLOW, HCOM/LCOM (§7.3, **D-8**). HCOM/LCOM are highest/lowest daily **close** — *"not the highest wick"* |
| `stoic/sequence.py` | **L2.** The Step 1 → Step 2 → Step 3 machine, the reset (**D-15**), the directional state (**D-21**), the running Step 3 High/Low (**D-16**, not frozen here), the Step 2 swing (**D-20**), and the three §5.4.7 invalidation events |
| `stoic/entry.py` | **L3.** The PTB walk — anchor, re-anchor per non-inside candle (**D-17**), inside-candle skip (**D-23**/§5.3.5a), the stop-market fill including the gap case (**D-22**), the stop at the opposite PTB extreme (**D-18**, no floor), and the break-even trigger (**D-25**) against the Step 3 extreme **frozen at fill** (**D-16**). Consumes L1's pullback and L2's events; derives neither |

**L2's four unquantified terms are injected, not implemented — and that has not changed now that
three are decided.** `Judgment` is a frozen dataclass of four predicates with **no defaults** —
*"meaningful"* break, obvious base, boundary selection, *"meaningful close"*. L2 enforces every
mechanical clause itself and asks a predicate only about the unquantified adjective; a predicate is
not even called when a mechanical precondition fails. §2.2.8 is enforced structurally:
`select_boundary` receives bars truncated at the base's last bar, so it cannot see the break.
**Nothing runs end to end until the obvious base is decided.**

**`stoic/judgment.py` is where a decided predicate lives — never `stoic/sequence.py`.** It holds the
two **D-29** predicates, **D-30**'s `select_boundary_from_base`, and the single constant
`MEANINGFUL_FRACTION = 0.10`, each naming the §11 row that authorised it. It fixes two conventions in its docstring rather than in `docs/RULEBOOK.md`,
the same disposition `candles.py` took for its inside-bar tie-break: **no parent bar means not
confirmed** (head of frame — no yardstick, so `False`, never a pass), and **a non-finite parent range
means not confirmed**, while a parent range of exactly zero is left to the literal arithmetic.
`attach_parent_pos(bars)` must be called once per frame; the predicates raise rather than guess if
the column is absent.

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

**Two orderings inside L3's bar are the design, not accidents.** The **fill is checked before L2's
events** because a fill is intrabar while all three §5.4.7 conditions are close-based (the §5.4.7
engine note), so on a bar that both fills and invalidates, the fill happened first. And a **`RESET`
does not cancel a working order** — it only disarms, so no *new* pullback is scanned. §5.3.4a says
there is *"no third outcome and no timeout"*: only a fill or §5.4.7a–c ends the walk. That is
**O-15** implemented exactly as the rulebook is written, not reconciled, and a test pins it.

**L1 is only the pullback boundary.** Base detection, boundary selection and climax are **not**
built: §2.2.5–§2.2.9 and §4 are **J**, so building them would invent the thresholds `CLAUDE.md`
forbids. Swing-point detection is not built either — no rulebook definition exists, any pivot needs
an invented lookback, and nothing consumes one.

**Two unpinned choices are documented as conventions in their module docstrings, and deliberately
not written into `docs/RULEBOOK.md`:** a bar whose high *and* low exactly equal its parent's counts
as **inside** (`<=`/`>=`), and the SMA input series is the **close** (§1.1 names neither).

## Open

- **A `T2` reading that would bear on D-23, not yet verified.** On `T2`'s bullish count the last
  pullback candle before the entry looks **up-bodied (green)**, which would make it a live-marked
  counterexample to the `close < open` body test D-23 rejected — evidence *for* the decision the user
  already took. It is **not** written into §10.8, because at the available zoom the `ptb` level's
  anchor bar cannot be told apart from the large down candle before it (~14 points, inside the ±10
  pixel error). Worth one pass at full resolution; nothing depends on it.
- **`LT4` is held past the 1:58pm Pacific flatten** — entry 04:00 PM ET, exit into the Asia session
  at +4.5R (§10.9). Under `VISION.md` a Scalp or Day trade is marked closed at the cutoff, so this
  fixture is only reproducible as a **Swing or Position** Type. Phase 3 must record the Type it
  labels it as; Phase 6 will otherwise report a divergence that is the harness's, not the engine's.
- **Session `2025-11-28` has a ~645-minute hole in `data/historical/{NQ,ES}_1m.parquet`** — the whole
  Asia/London portion, both instruments. Real missing data, not a holiday early close. Any Phase 3
  label or Phase 5 replay touching that date must exclude or flag it. See
  `claude_memories/historical-bars-2025-11-28-outage.md`; Gate E reports it every run.
- **The source videos exist only on this disk.** They are gitignored (`*.mp4`) and `videos.zip`
  predates the 1-2-3 material, so it does not contain the Marker Study, the Scalping Example, the
  `PTB Entries` video (the one the newest 34 citations rest on), or `Navigating tough price action`
  added 2026-08-08. Nothing
  restores them if the disk is lost. They need to go to Google Drive and into `videos.zip`.
  The transcripts and keyframe manifests are in git; the keyframe **images** are gitignored
  (`edu/derived/**/keyframes/`) and are regenerable from the videos — which is only true while the
  videos survive.
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
