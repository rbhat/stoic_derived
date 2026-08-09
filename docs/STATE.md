# Current state — what is true right now

**Phases 0, 1, 2 and 2a are complete. `docs/RULEBOOK.md` has closed its register, and nothing in §12
blocks Phase 5.** Every rule carries a citation. The last blocker — **O-14**, where the post-Step-3
expansion leg ends — closed on 2026-08-08 as **D-28**, so **L1, L3 and L4** all compile.

The decision register is `docs/RULEBOOK.md` **§11** (closed) and **§12** (open) — nowhere else. The
table in `docs/PLAN.md` is the superseded intake form.

## What is still live from Phase 2a

Phase 2a is closed and **is not summarised here** — `docs/AUDIT-2a.md` is its record, `docs/RULEBOOK.md`
§11 holds every decision it produced, and `git log` holds the rest. Two things it left behind are
current rather than historical:

- **`.artifacts/ptb_atr_distribution.md` is now almost entirely inert.** O-5 closed by deleting the
  ATR stop floor (**D-18**), so nothing in the spec reads its percentiles, and its `BODY` / `EXTREME`
  columns describe two readings **D-23** rejected. **One number in it still matters:** those two
  readings pick a different anchor bar on **62.8%** of candidates (NQ 5m RTH 2019–2026), which is why
  neither could be adopted quietly and why D-23 stands. `.artifacts/` is gitignored, so this file does
  not travel between machines.
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

1. **Phase 5 — the rulebook engine.** The spec is closed and the layer boundaries are settled, so
   this is the next build. L0 → L5 per the `docs/PLAN.md` layer table, pure functions over bars,
   no network and no model, each layer unit-tested against hand-built fixtures with a negative
   control per `coding_rules.md`.
2. **Phase 3 (labelled reference set) is deferred by the user's call on 2026-08-08** — *"we will
   backtest once the system is on."* It is **not cancelled**: Phase 6 cannot report fidelity without
   it, and it is the evidence that would confirm or overturn **D-28**. It simply does not gate the
   engine. When it starts: **`T2` (§10.8) is the densest fixture** — two counts, a live-marked reset,
   two PTBs, six executions — with `NQ3` (§10.7) the cleanest single-sequence one and `LT3`/`LT4`
   (§10.9) the only trade held past the session. All are single instances, so small-*n* rules apply.
   `PTBV` is the richer source: a full session in which the trader marks every PTB entry on one
   1-2-3. **§10.10 recovers the stop from any of them** — none draws one, but the R labels are
   normalised against a ~$1,000 risk unit, so `stop distance = P&L points ÷ R multiple`.
3. **Phase 4 (the SLM) has no blocking question left.** O-14 was the one thing routed to it; the
   human decided it instead. What remains for it is **O-9** (the no-edge zone, per **D-9**) and
   Phase 3 label proposals — both off the critical path.

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
| `tests/` | 25 tests, hermetic |

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
