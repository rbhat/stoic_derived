# How much room Phase 4's SLM has left — a count of the J rows

**Asked for by the user on 2026-08-10:** *"a lot of these rules are going to constrain or make the
SLM incoherent."* This is the measurement, not an opinion. **Nothing here is decided.** No row is
closed, no term is filled, and no D-row or O-row is proposed.

Method: every status cell in `docs/RULEBOOK.md` §1–§9 was extracted mechanically and tallied, then
each **J** row was read against §11 and §12 to see what, if anything, now stands on it.

## The tally

| Status | Rows |
|---|---|
| **M** — mechanical | 94 |
| **J** — judgment | 21 |
| **P** — parametric | 6 |
| **—** — context, no engine consequence | 19 |
| §7.1.4 — `M` (bullish) / `P` (mirror) | 1 |

Matches what `docs/STATE.md` carried. **34 D-rows exist and 5 of them land on a J row.**

## The 21 J rows, by what now stands on them

### A. Closed for the engine by a named D-row — 5

The term stays **J** because the *material* still refuses to quantify it. What changed is that the
engine now compiles something, and the D-row says so on the row itself.

| Row | Term | Closed by |
|---|---|---|
| 2.1.4 | *"meaningful"* | **D-29** — 10% of the parent bar's range |
| 2.2.5 | obvious base | **D-34** — the residual state, via §2.2.5a (**P**) |
| 2.2.6 | which boundary | **D-30** — the base's close extreme; sloping case still out (**O-18**) |
| 5.3.3c | no body / lower-high test on a PTB candidate | **D-23** + **D-28** — closed as a *refusal*; the engine implements it by omitting both tests |
| 6.5a | lower-high cue | **D-26** — annotates, never fires |

### B. Neutralised without any D-row naming them — 7

The engine's behaviour at these rows is fixed, but by something else: another rule, a reset, or a
construction that dissolves the question. **No §11 row mentions any of these seven.** They are open
as descriptions and inert as engine questions.

| Row | Term | What actually fixed the behaviour |
|---|---|---|
| 2.2.3 | the return must *visually* retest the 10/20 area | **D-34** dropped MA-proximity as a test outright; §2.2.1 makes the return toward the MAs by construction, and **D-15**'s reset ends the count if it goes too far |
| 2.3.7 | a break closing back inside; the base *"may remain pending while visually intact"* | Under **D-34** the base is re-derived every bar, so *pending vs discard* has no state to hold. **Its engine disposition — a re-break emits `STEP_3_BREAK` again, and the boundary freezes — lives in `docs/STATE.md`'s L2 audit note, not in §11.** See *What this surfaced*, below |
| 2.3.10 | *"barely swept"* | **D-29**: a sweep that does not close beyond the boundary by 10% of the parent range is not a Confirmed Step 3. The row says to read its magnitude as §2.1.4's, and §2.1.4 now has a number |
| 2.4.2 | wrong-way break / destroyed base / replacement structure | **D-15**'s reset is the wrong-way break; **D-34**'s *"cancelled if the leg resumes"* is the destroyed base; a residual base has no *replacement* to recognise |
| 4.1 | climax = *"visibly extended"* | **D-5 deferred it on purpose** (*"keep it till we get more info"*). §4.3 (**M**) and §4's engine note cap the payoff: a climax may never fire, suppress or invalidate |
| 4.2 | the 10 SMA as the climax reference | same |
| 4.4 | capitulation, the live reading of the same thing | same |

### C. Routed to an open §12 row — 4

| Row | Term | Open row |
|---|---|---|
| 2.2.7 | sloping boundary | **O-18** — *an implementation may not pick it silently* |
| 2.2.9 | two equally valid boundaries → wait | **O-20** — *do not add a selector to fill this* |
| 7.4.1 | no-edge zone, definition | **O-9**, and **D-9** routes it to the SLM by name |
| 7.4.2 | no-edge zone, enumerated instances | **O-9**; §7.4.4 already splits the eight — *no clean invalidation* is mechanical, *no realistic target* goes to §5.4.6 / **O-10**, *no trap side* goes to §7.3, which is itself **J** |

### D. Open with nothing routing them — 2

| Row | Term | Where it stands |
|---|---|---|
| §7.3 **Trapped side** | *"where did one side commit very hard … where would they be forced to exit"* | No D-row, **no O-row**. It is an input to 7.4.2 and §7.4.4 points at it, so it is load-bearing for the no-edge zone and has nowhere to land. `docs/CONSTRAINTS.md` marks inventing it as exactly what `claude_memories/audit-hard-rules-not-in-material.md` forbids |
| 7.5.1 | *"the setup has to deserve risk"* — context, asymmetrical R:R, invalidation, a reason to exist | Adjacent to **O-10**, which covers only the minimum-R half. The other three conditions are on no row |

### E. Out of the v1 engine path — 3

`Break & retest`, `Swing failure pattern (SFP)` and `SBS` (§8).

**§8's preamble says these are *"defined here because the signal record and the confluence score
reference them."* That is no longer true.** **D-33** fixed the score to a count of three named
conditions, none of which is a setup type, and `stoic/emission.py` emits `setup_type="123_ptb"` as a
literal — *"v1 emits exactly one setup"*. Nothing in the engine reads these three rows.

## What the corpus holds for the rows still in play

Keyword volume across the 17 text sources, **as an upper bound on where a Phase 4 pass would look —
not as evidence that the material speaks to the term.** Only a passage census settles that, which is
what `docs/evidence/census_meaningful.md` and `census_base_boundary.md` did for the other four terms,
and both of those found **no passage quantifying any of them**.

**`OTV` is counted twice below** — `edu/123sequence/start_here/only_trading_video.md` (13,240 words)
and `edu/derived/concept_the_only_trading_video…/transcript.md` (13,095) are the same video
transcribed twice, per `docs/STATE.md`. Halve any row those two dominate.

| Term | hits | files | densest source |
|---|---|---|---|
| §8's three setups (E) | 297 | 9 | `OTV` ×2, then `PTBV` |
| trapped side (D) | 112 | 8 | `HTF` (39), then `OTV` ×2 |
| no-edge zone (C) | 109 | 7 | `OTV` ×2, then `SSS` |
| deserves risk (D) | 17 | 3 | `OTV` ×2, `CMD` |
| sloping boundary (C) | 16 | 4 | `SCALP` (7) |
| climax / visibly extended (B) | 13 | 4 | `M1` (6), `SCALP` (4) |

Reproduce with `.scratch/j_census.py` (gitignored; the patterns are in the table above).

## What this measures

**The 34 D-rows are not what limits Phase 4.** Only 5 of the 21 J rows carry a D-row at all, and
none of the five sits under the terms Phase 4 would work on — §7.3 and §7.4 are gating and context,
and no decision has ever touched them. The concern that the rulebook would make the SLM incoherent
is not visible in the count.

**What limits Phase 4 is that most of the room closed by other means.** Of 21 J rows: 5 compiled,
7 inert, 3 out of the v1 path. That leaves **7 live** — and of those, **O-20 says outright not to
fill it**, **O-18**'s answer is *when to reach for* a case the horizontal default already covers, and
**7.5.1**'s three non-R conditions have no row to land on.

**Two rows are where a proposal would actually change something:**

- **7.4.1 / 7.4.2, the no-edge zone.** This is Phase 4's charter already — **D-9** assigns it by
  name and **O-9** is open for it. The corpus volume is real and `SSS`, `CST` and `HTF` are the
  dense sources, which is the complementary layer §13 governs — so anything proposed here lands as
  *context*, never as a step of the sequence.
- **§7.3 trapped side.** The densest term measured, and §7.4.4 makes it a prerequisite for one of
  7.4.2's instances. **It has no open row**, so a proposal has nowhere to go until the human opens
  one. Whether to open it is not this audit's call.

## What this surfaced, reported and not acted on

1. **§2.3.7's engine disposition has no §11 row.** *A re-break of a still-pending base emits
   `STEP_3_BREAK` again*, and *a base may not be broken on the bar its own boundary was selected* —
   both were settled in the L2 audit pass and recorded in `docs/STATE.md` so they would not be
   re-litigated. Neither is in §11, which `docs/STATE.md` itself calls the register *"nowhere
   else."*
2. **§8's preamble is stale** — see E above. Editing §1–§9 is the user's call.

Neither is a decision and neither blocks anything.
