# Phase 2a — the invented-rule audit

**Opened 2026-08-08. Findings below; the sweep is done, the dispositions are not.**

`docs/PLAN.md` Phase 2a defines the job: sweep `docs/RULEBOOK.md` §1–§9 and class every rule as
*cited* / *human decision* / *invented*, and get the third class out of the spec before Phase 5
compiles it. The standing rule behind it is
`claude_memories/audit-hard-rules-not-in-material.md`.

## Method

A mechanical citation sweep ran first: for each numbered rule, retrieve the **actual text** of every
cited source and record whether the rule says more than the source says. Three Sonnet agents, one per
band, quoting verbatim and forbidden from consulting `docs/PLAN.md`, `docs/STATE.md` or
`claude_memories/` — so that nothing about what a rule *should* say could leak into what its source
*does* say.

Raw evidence, one row per rule, in `.artifacts/` — **gitignored, does not travel between machines,
regenerate rather than trust a stale copy**:

| File | Scope | Rows |
|---|---|---|
| `sweep_A_sections_1_to_4.md` | §1, §2, §3, §4 | 55 |
| `sweep_B_sections_5_to_6.md` | §5 (minus the D-23 rows), §6 | 40 |
| `sweep_C_sections_7_to_9.md` | §7, §8, §9 | 37 |

## Totals

| | NO | YES | DECISION | BROKEN |
|---|---|---|---|---|
| §1–§4 | 49 | 1 | 5 | 0 |
| §5–§6 | 27 | 6 | 7 | 0 |
| §7–§9 | 29 | 3 | 5 | 0 |
| **All** | **105** | **10** | **17** | **0** |

`YES` = the rule contains a predicate, threshold, count, comparison or mechanism that no cited source
states. It is the audit's candidate-*invented* list, **not** a verdict — a `YES` may still turn out
to be a legitimate human decision that was never written up as one.

**No citation in §1–§9 is broken.** Every timestamp and file resolved to real, on-topic material.
That is worth recording: the problem this audit found is not fabricated sources, it is rules that
outran real ones.

## Verification status — read this before acting on any row

`CLAUDE.md` says not to take a subagent's claims at face value. **Five findings were re-checked
against the source artifact by the lead; six were not.** Do not treat the two groups alike.

| Finding | Verified by the lead? |
|---|---|
| 2.3.10 — "wick" | **Yes** — `grep -i wick` over `M1`: one hit, at `10:03`, about Step 1 |
| `DIA-P` = `DIA-L` | **Yes** — `md5`, and `diff` returns nothing |
| 7.1.4 — long → any trade | **Yes** — `SCALP @ 23:02` read in full |
| 7.5.4 — "no minimum R" | **Yes** — `SSS @ 53:51` read in full |
| 7.1.7 — quote not in `edu/` | **Yes** — grep over `edu/`, `discussion/`, `PTB Questions.md`: absent |
| 5.3.10, 5.4.1, 5.4.6, 6.3b, 6.3c, 6.6, 7.4.4 | **No** — agent-reported, unverified |

---

## Verified findings

### F-1 — `DIA-P`, `DIA-L` and `step-1-2-3.svg` are one file, not three

All three paths hold md5 `5db99292665d2f688ee34531688444ad`; `diff` is empty. Found independently by
two of the three sweeps, then verified directly.

**What breaks.** §10.3 concludes: *"Two independent drawings agreeing bar for bar is why §3.4 and
§5.3.4 could be stated mechanically"*, and calls `DIA-P`'s entry line *"the independent confirmation
of D-12"*. **There is no independent confirmation.** It is one drawing cited twice, and two rules
were promoted to **M** partly on the strength of a corroboration that does not exist.

**What does not break.** The file genuinely contains the `Step 3 High`, `PTB` and `Entry` labels
(grep confirms two of each), so §3.6 and §5.2.4 are reading real content. Sweep A traced the SVG
coordinates and reports 3.2 and 3.6 geometrically correct. The claims are fine; the *corroboration
argument* is void.

**Disposition (not yet applied).** §0 must disclose that `DIA-P` is the same bytes as `DIA-L`, the
way it already discloses `step-1-2-3.svg`. §10.3's "two independent drawings" sentence must go. Then
§3.4 and §5.3.4 need re-justifying on what is actually left, or demoting.

### F-2 — 2.3.10 imports "wick"

The rule: *"A boundary that is merely **swept by a wick** is not a Step 3."* The cited passage
(`M1 @ 19:18`–`19:46`) says *"the step three would be the breakout at least like this and
continuation but we just **barely swept** that high as you can see it and continues lower."*

*Barely swept* is about **magnitude**; *swept by a wick* is about **wick vs body**. They are
different predicates and they disagree on a real case: a bar closing one tick beyond the boundary has
barely swept it but has not wicked it. The word "wick" appears exactly once in all of `M1`, at
`10:03`, about Step 1 — and §2.1.2 already carries it correctly there.

### F-3 — 7.1.4 generalizes a bullish-only instruction

The rule: *"Do not take a **trade** into the 200 SMA on fast charts."* The source
(`SCALP @ 23:02`): *"on one minute especially on one minute chart five minute chart **do not long**
into the 200 sma."* The mirror for shorts is the rulebook's, not the material's. It may well be
right — the method is broadly symmetric — but symmetry was assumed, not taught.

### F-4 — 7.5.4 is false as written

The rule: *"No minimum R is stated anywhere in the corpus."* `SSS @ 53:51` states a number: *"the
risk to reward is absolutely ridiculous **five to one at minimum** it's very typical for the trade to
go more than 5r."*

**Read the passage before using it.** In context it describes the R:R that the chop-zone setup
*offers* when the target is far and the stop is tight — it is the geometry of a setup, not a gate a
setup must clear. So it does not hand O-10 a threshold. But the rule's universal claim is wrong, and
`SSS` counts as "the corpus" by the rulebook's own usage — §7.4.3, two rows up, cites the same §13
layer as a source.

### F-5 — 7.1.7 quotes something that is not in the material

7.1.7 contains *"if candles keep sticking up and down the 50, it's choppy … practically it could mean
that we count/reset continuously."* Typeset as a quotation. It does not appear anywhere under
`edu/`, nor in `discussion/`, nor in `PTB Questions.md`.

Its Source column points only at decision **D-19**, which came from the user's answers — so the
provenance is almost certainly legitimate (the user's own words in conversation). **The bug is
presentation, not honesty:** in a file where every other italic quotation is material, one that is
not reads as material. Same class of failure as `CLAUDE.md`'s own pointer rule.

**Disposition.** Mark user-sourced quotations distinctly, or drop the quotation marks and state it as
the decision it is. Then sweep §1–§9 for others of the same shape.

---

## Reported but unverified — check before acting

From `sweep_B`: **5.3.10** ("widens R" — direction not stated by the rules it derives from; "signal
record stores both" has no counterpart; possible circular derivation with 5.4.2) · **5.4.1**
(`PTBQ` §2 says only "PTB low/high", the long/short pairing is the rulebook's) · **5.4.6** (`PTBQ`
says "sufficient room must remain", the `TP1 ≥ m × R` inequality is the rulebook's construction) ·
**6.3b** (cited span supports "second pullback confirms reversal" but not "we enter"; the actual
quote is reportedly uncited at `OTV @ ~1:07:32`) · **6.3c** (mapping "first lower high" to "the Step 2
bounce" is the rulebook's translation, with no decision backing it) · **6.6** (`M1 @ 16:08`
reportedly lists four optional management items, not climax alone, so "only" is unsupported).

From `sweep_C`: **7.4.4** (claims three no-edge-zone instances are "already mechanical", but the room
condition is status **P** and open, the trapped-side term is status **J**, and the room condition
lives at §5.4.6 not §5.4.4 as cited — so at most one of the three is mechanical).

---

## What the audit has already produced

**D-23 was rewritten before the sweep finished** — see `docs/STATE.md`. It is the model for what a
Phase 2a disposition looks like: a predicate that had been recorded as a human decision on the belief
that the material was silent, found contradicted, put back to the human, and returned to **J** with
an open row (**O-14**). It also cost the spec a blocker it did not previously know it had.

## Exit gate — not met

`docs/PLAN.md` requires: every rule in §1–§9 carries a class; no rule classed *invented* is still
stated as **M**; the count moved to §12 or to the SLM is reported and not minimised.

**Remaining work, in order:**

1. Verify the six unverified findings against source.
2. Class all 132 rows *cited* / *human decision* / *invented*. The sweep gives the evidence; the
   class is a judgment and is the lead's, not a subagent's.
3. Apply dispositions. F-1 is the one with reach — it touches §0, §3.4, §5.3.4 and §10.3.
4. Re-check status tags: an **M** on a rule whose source is a judgment call is the signature failure
   `docs/PLAN.md` names.
5. Report the count moved out. Do not minimise it.
