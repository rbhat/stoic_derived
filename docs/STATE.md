# Current state — what is true right now

**Phases 0, 1 and 2a are complete. Phase 2's deliverable — `docs/RULEBOOK.md` — is written and its
register is closed: nothing in §12 blocks Phase 5.** The last blocker, **O-14** (where the
post-Step-3 expansion leg ends), closed on 2026-08-08 as **D-28**, so **L1, L3 and L4** all compile.
Phase 2's exit gate names a *two-reader* test that has never actually been run — the register being
closed is not the same claim, so do not report that gate as met.

**Phase 5 is under way: L0, L1 and L2 are built.** Baseline as at 2026-08-09: `pytest`
**122 passed**, `scripts/verify_citations.py` **205 citations across 8 sources, all resolve**,
negative control PASS.

**Next step: L2's four terms go to Phase 4's SLM — the user's call, 2026-08-09.** L2's machine is
built with them injected, so nothing runs end to end until they are filled in. They are the four
terms the spec deliberately leaves unquantified: *"meaningful"* for the Step 1 break and close
(§2.1.1 **P**, §2.1.4 **J**, **D-2** sets no threshold), *"meaningful close"* for Confirmed Step 3
(§2.3.4 **P**), an **obvious base** (§2.2.5 **J**, **D-3** qualitative), and **boundary selection**
(§2.2.6–§2.2.9 **J**, under the §2.2.8 no-hindsight constraint). None is an open §12 row.

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

1. **Phase 5 — the rulebook engine.** L0 and L1 are built (table below). **L2 is next and needs the
   four decisions named at the top of this file first.** L3 → L5 follow per the `docs/PLAN.md`
   layer table, pure functions over bars, no network and no model, each layer unit-tested against
   hand-built fixtures with a negative control per `coding_rules.md`.
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

## What Phase 5 L0 and L1 built

Pure functions over bars — no disk I/O, no network, no clock, no model. Tests are hermetic and
hand-built; the suite is 76.

| | |
|---|---|
| `stoic/indicators.py` | 10/20 (sequence) and 50/200 (trend) SMAs of the close, on the frame given. Warm-up stays NaN — never `min_periods=1` |
| `stoic/candles.py` | `candle_structure` — inside-bar flags and **parent-bar** positions (§5.2.8a, **D-23**). A run of inside bars shares one parent; for a non-inside bar the parent is the nearest preceding non-inside bar, which is the reference **D-28** requires |
| `stoic/structure.py` | **L1.** `opens_pullback` / `find_pullback_start` / `leg_phases` — **D-28** (§5.2.1a): the pullback opens at the first completed candle whose **both** extremes move against the direction, measured against the parent bar. Never reads `open` or `close` (§5.3.3c) |
| `stoic/levels.py` | PDH/PDL/PDC, PWC/PWH/PLOW, HCOM/LCOM (§7.3, **D-8**). HCOM/LCOM are highest/lowest daily **close** — *"not the highest wick"* |
| `stoic/sequence.py` | **L2.** The Step 1 → Step 2 → Step 3 machine, the reset (**D-15**), the directional state (**D-21**), the running Step 3 High/Low (**D-16**, not frozen here), the Step 2 swing (**D-20**), and the three §5.4.7 invalidation events |

**L2's four unquantified terms are injected, not implemented.** `Judgment` is a frozen dataclass of
four predicates with **no defaults** — *"meaningful"* break, obvious base, boundary selection,
*"meaningful close"*. L2 enforces every mechanical clause itself and asks a predicate only about the
unquantified adjective; a predicate is not even called when a mechanical precondition fails. §2.2.8
is enforced structurally: `select_boundary` receives bars truncated at the base's last bar, so it
cannot see the break. **Nothing runs end to end until the four are decided.**

**Invalidation scope outlives the directional state, and that is the rulebook, not a convenience.**
An L2 count dies at the 10/20 reset (§2.5.8, **D-21**); the §5.4.7 conditions attach to a position
or a pending order, which does not (§6.5). Gating them on the count's stage made §5.4.7a
unreachable — the bullish reset predicate is character-identical to the bearish Step 1 predicate, so
the opposite Step 1 always resets us before its Step 3 can confirm. The §5.4.7 engine note settles
it: they *"fire before the opposite sequence completes — 5.4.7a can be many bars away."*

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
