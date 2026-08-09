# Phase 2a — the invented-rule audit

**Opened and closed 2026-08-08. This is a record of a finished phase — nothing in it is outstanding.**
Every finding below is verified against source, every disposition is applied, and the carry-over list
at the end was discharged in the two commits that followed. `docs/STATE.md` holds what is true now and
deliberately does not summarise this file. Read it for *why* a rule in §1–§9 says what it says.

`docs/PLAN.md` Phase 2a defines the job: sweep `docs/RULEBOOK.md` §1–§9 and class every rule as
*cited* / *human decision* / *invented*, and get the third class out of the spec before Phase 5
compiles it. The standing rule behind it is
`claude_memories/audit-hard-rules-not-in-material.md`.

## Method

A mechanical citation sweep ran first: for each numbered rule, retrieve the **actual text** of every
cited source and record whether the rule says more than the source says. Four Sonnet agents — three
by band, then `sweep_D` for the rules Coverage found missing — quoting verbatim and forbidden from
consulting `docs/PLAN.md`, `docs/STATE.md`, `claude_memories/` or each other's output, so that nothing
about what a rule *should* say could leak into what its source *does* say.

Raw evidence, one row per rule, in `.artifacts/` — **gitignored, does not travel between machines,
regenerate rather than trust a stale copy**:

| File | Scope | Rows |
|---|---|---|
| `sweep_A_sections_1_to_4.md` | §1, §2, §3, §4 | 55 |
| `sweep_B_sections_5_to_6.md` | §5 (minus the D-23 rows), §6 | 40 |
| `sweep_C_sections_7_to_9.md` | §7, §8, §9 | 37 |
| `sweep_D_missed_rules.md` | the 11 rules Coverage names | 11 |

## Coverage — the sweep's 132 is not §1–§9's 132

**Checked 2026-08-08 by diffing the swept row IDs against the rule IDs in `docs/RULEBOOK.md`.** The
two sets are the same size and are not the same set. This nearly hid a gap.

| | Count |
|---|---|
| Numbered rules in §1–§9 (`1.1` … `7.5.4`) | 118 |
| Term rows in §7.3 and §8 (`HCOM`, `Break & retest`, …) | 14 |
| **Definitional rows in §1–§9** | **132** |

| What the three sweeps actually covered | Count |
|---|---|
| Numbered rules | 107 |
| Term rows (§7.3, §8) | 14 |
| Prose and paragraph claims — 7 decomposed out of §5.1, the §7.3 lookback note, and 3 from §9 | 11 |
| **Swept rows** | **132** |

**Eleven numbered rules carry no sweep evidence:** `5.2.8`, `5.2.8a`, `5.3.3`, `5.3.3a`, `5.3.3b`,
`5.3.3c`, `5.3.4`, `5.3.5`, `5.4.7a`, `5.4.7b`, `5.4.7c`.

They were not a random miss. Four are the **D-23 rows** `sweep_B` was deliberately told to skip while
D-23 was being rewritten under it. Three are **D-24's** invalidation rows, which landed on the same
day the audit opened. And two of them are load-bearing here:

- **`5.3.4`** is one of the two rules **F-1** says was promoted to **M** partly on a corroboration
  that does not exist — named in F-1's own disposition, and never swept.
- **`5.4.7c`** is stated **M** on a condition that **D-24 itself says was not found anywhere in the
  corpus**. That is the exact shape this phase exists to find, and it sat outside the sweep.

**`sweep_D` has now covered these 11 by the same method — coverage is complete.** Every numbered rule
and every term row in §1–§9 carries sweep evidence: 143 rows in total (132 definitional + 11 prose).

It returned **0 YES and 0 BROKEN**, but **8 of 11 rows are DECISION** — they lean on **D-17**, **D-23**
or **D-24** to supply specificity the `edu/` material does not state. That is not a clean bill of
health, it is a concentration: the rules the first sweeps missed are precisely the cluster where the
human did the most interpretive work. Two were re-verified by the lead:

- **`5.3.4`** — `PTBQ` §1 **contradicts itself** and the rule picks a side. It says the PTB *"must be
  the latest correction bar **within the three-bar window**"* and then, two sentences later, *"The 3
  bar window is not defintite."* Both clauses are verbatim in the file. §5.3.4's *"There is no bar
  cap"* is **D-17 resolving that contradiction**, not `PTBQ` stating a rule — yet the row cites
  `PTBQ` §1 first and stands as **M**. The §5.3 quote block does reproduce both clauses honestly, so
  nothing is hidden; the citation order is what implies the source settled it.
- **`5.4.7c`** — the corpus really is silent. The lead ran an independent search over all transcripts,
  `concepts/`, `entry_technique/` and `discussion/` for a close-beyond-a-boundary exit and got
  **zero hits**, matching both the agent and **D-24**'s own admission. The rule is stated **M** and is
  entirely the human's. It cites D-24, so it is visible — but see ruling 2 below for why the status
  tag is not the thing to change.

## Totals

| | NO | YES | DECISION | BROKEN |
|---|---|---|---|---|
| §1–§4 | 49 | 1 | 5 | 0 |
| §5–§6 | 27 | 6 | 7 | 0 |
| §7–§9 | 29 | 3 | 5 | 0 |
| the 11 missed rules (`sweep_D`) | 3 | 0 | 8 | 0 |
| **All** | **108** | **10** | **25** | **0** |

`YES` = the rule contains a predicate, threshold, count, comparison or mechanism that no cited source
states. It is the audit's candidate-*invented* list, **not** a verdict — a `YES` may still turn out
to be a legitimate human decision that was never written up as one.

These are counts over the **143 swept rows** — the 132 definitional rows plus 11 prose claims. Do not
read the `All` row as "143 rules": see Coverage for what the denominator actually contains.

**No citation in §1–§9 is broken.** Every timestamp and file resolved to real, on-topic material.
That is worth recording: the problem this audit found is not fabricated sources, it is rules that
outran real ones.

## Verification status — all twelve verified

`CLAUDE.md` says not to take a subagent's claims at face value. The first pass verified five findings
and left seven agent-reported (the doc said "six" and listed seven). **All twelve are now verified
against the source artifact by the lead**, and the exercise earned its keep: one reported finding did
not survive.

| Finding | How it was verified |
|---|---|
| F-1 · `DIA-P` = `DIA-L` | `md5`, and `diff` returns nothing |
| F-2 · 2.3.10 — "wick" | `grep -i wick` over `M1`: one hit, at `10:03`, about Step 1 |
| F-3 · 7.1.4 — long → any trade | `SCALP @ 23:02` read in full |
| F-4 · 7.5.4 — "no minimum R" | `SSS @ 53:51` read in full |
| F-5 · 7.1.7 — quote not in `edu/` | grep over `edu/`, `discussion/`, `PTB Questions.md`: absent |
| F-6 · 5.3.10 | `docs/RULEBOOK.md` rows 5.3.7 / 5.4.1 / 5.4.2 read against each other — **one of three reported claims rejected** |
| F-7 · 5.4.1 | `PTBQ` read in full (the file is 13 lines) |
| F-8 · 5.4.6 | `PTBQ` §1 read in full |
| F-9 · 6.3b | `OTV` read at `51:45`–`53:07` and at `1:06:41`–`1:07:55` |
| F-10 · 6.3c | `SCALP` read at `04:08`–`07:38` |
| F-11 · 6.6 | `M1` read at `15:56`–`16:44` |
| F-12 · 7.4.4 | §5.4.1, §5.4.4, §5.4.6 and §7.3's status column read directly |

**The one that did not survive is worth naming.** `sweep_B` reported that 5.3.10's *"widens R"* states
a direction its cited rules do not. It does not: 5.3.7 fixes the fill on the far side of the trigger
and 5.4.2 measures R from the PTB extreme, so widening follows. The agent was applying a
citation-completeness test and reporting it as an unsupported predicate. Its other two claims on that
row hold. This is the reason the verification step exists.

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

**Disposition — factual half applied 2026-08-08, judgment half open.**

- **Applied.** §0 now discloses the byte-identity and says never to cite `DIA-P` as corroboration of
  `DIA-L`. §10.3's two false sentences are gone, replaced by what is actually true: the labels are
  real, the corroboration is not. Done because leaving a *verified-false* claim in the binding spec
  across a context reset is worse than leaving it unresolved — the next reader treats §10.3 as source
  of truth.
- **Judgment half — resolved 2026-08-08. Both keep M.**
  - **§3.4** never rested on the corroboration in the first place: its Source column is **D-16**, a
    decision, and a running maximum from a known start bar has **no free parameter**, which is §0's
    test for **M**. The void claim lived in §10.3's prose, not in §3.4's citation. It is independently
    supported by `DIA-S` — which the corpus-wide hash scan confirms **is** a genuinely distinct file
    (F-13) — and by `PTBV @ 00:09:43`–`00:09:59`.
  - **§5.3.4** keeps **M** with a disclosure instead: the row now cites **D-17** first and states that
    `PTBQ` §1 contradicts itself, so no reader can mistake the source for having settled it.
- `DIA-P`'s other citation sites, §5.2.4 and §5.3.6, were checked: both already say in-line that this
  is one drawing under two names. No "two drawings" reasoning survives anywhere.

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

### F-6 — 5.3.10 cites in a circle, and carries a data-model claim as a rule

Three things were reported on this row. **One is rejected, two hold.**

**Rejected — *"widens R"* is derivable.** 5.3.7 says a fill is *"never better than the trigger"*, so
for a long the fill sits at or above the PTB high; 5.4.2 measures `R = |fill − PTB extreme|` against
the stop-side extreme, the PTB low. `|fill − PTB low| ≥ |PTB high − PTB low|` follows. The sweep
called it unsupported because **5.4.1** — which names the stop side — is not in 5.3.10's Source
column. That is a citation-completeness defect, not an invented predicate.

**Holds — the derivation is circular.** 5.3.10's Source is *"derived from 5.3.7 + 5.4.2"*; 5.4.2's is
*"derived from 5.2.3 + 5.4.1 + 5.3.10"*. Each names the other as its parent, so neither bottoms out.

**Holds — *"The signal record stores both the trigger and the fill"* has no counterpart** in either
cited rule. It is also not a rule about trades: it is a data-model requirement, and §1–§9 is where a
reader looks for what decides a trade.

**Disposition.** Re-cite 5.3.10 as *derived from 5.3.7 + 5.4.1* and 5.4.2 as *derived from
5.2.3 + 5.4.1 + 5.3.7*, which breaks the cycle and puts the stop side where the derivation uses it.
Move the signal-record sentence to the engine note under §5.3.

### F-7 — 5.4.1's long/short pairing is not in the citation

`PTBQ` §2, in full — the file is 13 lines and was read whole:

> 2. Where does the stop go?
> PTB low/high

Four words, no directional labels. The rule states *"Stop = the PTB low **(long)** / PTB high
**(short)**"*. The pairing is entailed immediately by §5.2.3 (`ET`: a long's buy stop sits above the
PTB high, so its protective stop is the other side), but §5.2.3 is not in 5.4.1's Source column.

**Not invented** — the material supplies both halves. **Disposition:** add `ET` / §5.2.3 to the
Source column.

### F-8 — 5.4.6's inequality is the rulebook's, and so is its shape

`PTBQ` §1 says exactly one thing about room: *"sufficient room must remain to the Step 3 High/Low."*
5.4.6 renders it as **`TP1 distance ≥ m × R`**. Both the comparison and the multiplier `m` are ours —
and so is the **form**: expressing room as a multiple of *R* rather than as an absolute distance, or
as a fraction of the Step 3 leg, is a modelling choice the source does not make.

The row is already **P** and points at **O-10**, so no judgment is disguised as mechanical here.
**Disposition applied:** kept, with the row now saying the inequality is the rulebook's construction
of `PTBQ`'s qualitative condition. Its second pointer, **O-5**, is gone — see the decision review
below.

### F-9 — 6.3b's citation points at the wrong sentence, and the right one exists

The cited span is verbatim and says nothing about entering:

> `OTV @ 52:22`–`52:28` — *"because we don't know the first pullback might be a fake out, we looking
> for the second pullback. And once the second pullback occurs, then that's more likely that price
> actually reversed."*

The claim 6.3b makes — that `OTV` **enters** on the second pullback — is stated verbatim elsewhere in
the same file, uncited:

> `OTV @ 1:07:26`–`1:07:43` — *"Also fib geometry we measured the first pullback. There is the first
> 100%. **This is your second pullback where we enter.** I didn't measure this but there is probably
> 50% retracement. And then you get the first target 2618 and the second target 423."*

That passage is stronger than the one cited: in seventeen seconds it anchors the extension on the
first pullback, puts the entry on the second, and names 2618 and 423 as first and second target — it
corroborates **D-20** whole. **Disposition:** add `OTV @ 1:07:32` to the Source column. The rule is
right; the citation was aimed one minute short of the sentence that proves it.

### F-10 — 6.3c translates into 1-2-3 vocabulary without citing the decision that licenses it

`SCALP @ 06:35`, verbatim: *"is 200 sma we want to measure the first lower high right so 2618 this is
the target here."* Read `04:08`–`07:38` in full: the words *Step 1*, *Step 2* and *bounce* do not
appear anywhere in that trade's narration.

So *"the first lower high after the reversal is the Step 2 bounce"* is the rulebook's translation, not
`SCALP`'s. The translation is exactly what **D-20** decides — and 6.3b cites D-20 for it while **6.3c
does not**, though it makes the same move. The timing claim checks out: `06:35` precedes the short at
`07:06`.

**Disposition:** cite **D-20** in 6.3c, as 6.3b already does.

### F-11 — 6.6's "only" is contradicted by the sentence before the citation

6.6 reads *"Climax is the **only** other sanctioned management cue."* `M1 @ 16:08`, one line above the
cited timestamp:

> *"The 50 and 200 SMA climax conditions, additional entries, partial profits may appear as **optional
> management context**."*

Four items in that category, not one. The claim of exclusivity is false.

**Nothing needs adding to the spec** — two of the other three are already in it (additional entries
are §2.5's continuation entries, partial profits are §6.1). **Disposition:** drop *"only"*, state what
`M1` states, and cite `16:08` alongside `16:19`. The binding constraint is unaffected: §4.3 still says
management choices never create a signal or change the technical state.

### F-12 — 7.4.4 calls two open rules mechanical, and points at the wrong one

7.4.4 claims *"Three of 7.4.2's instances are already mechanical under this rulebook."* Checked against
the rulebook's own status column:

| Claim | Points at | Status there | Holds? |
|---|---|---|---|
| no clean invalidation → no PTB stop | §5.4.1 | **M**, unconditional | **Yes** |
| no realistic target → the room condition | cited as §5.4.4 — but the room condition is **§5.4.6** | both **P**, both open on O-5 / O-10 | **No** |
| no trap side → §7.3 | §7.3 *Trapped side* | **J** | **No** |

One of three. The row even concedes it mid-sentence — *"(§5.4.4, open)"* — while the lead clause says
all three are already mechanical. §0's own legend settles it: **P** means a number the material does
not give, **J** means the material refuses to quantify it; neither is **M**.

7.4.4's own status is **—**, so this is not the M-on-a-judgment failure in the status column. It is
the same failure in prose, which no status column catches.

**Disposition:** rewrite to say one instance is mechanical and two are not, and fix the §5.4.4 →
§5.4.6 pointer.

### F-13 — three marked-up charts in the main source directory have never been read

`docs/CONSTRAINTS.md` now carries a row saying to check `md5` before calling two sources independent.
Running that check across **every** image asset in `edu/123sequence/` — not just the pair F-1 caught —
produced one good result and one bad one.

**The good result: F-1 is the only independence violation in the corpus.** Fifteen assets, exactly one
duplicated hash — the known `DIA-L` / `DIA-P` / `step-1-2-3.svg` triple. `DIA-S` (`5329ee2c…`),
`PC`, `IBD`, `LT`, `NQ3`, `T1` and `MAS` are all byte-distinct. So `DIA-S` **is** a genuine second
drawing and `IBD` **is** genuinely independent of the `TPA` transcript. F-1's damage is contained to
the one triple.

**The bad result: the scan enumerated three marked charts that nothing in `docs/` references** —
`stoic_trade2.png`, `entry_technique/stoic_live_trade3.png`, `entry_technique/stoic_live_trade4.png`.
No citation key in §0, no worked example in §10, no mention in any doc. They entered in the restart
commit `8e07409`, meaning they **survived the cull that removed off-scope material** — they were
judged on-scope 1-2-3 material and then never opened. Read by the lead 2026-08-08:

| File | What is literally drawn on it |
|---|---|
| `stoic_trade2.png` | MNQ 5m. **Two complete 1-2-3 counts on one chart — one bearish, then one bullish** — plus a third `1` above them. **Two `ptb` levels**, one per count. Six executions, marked **−1R**, **+1R**, **+2.5R**. Both **261.80%** and **423.60%** extensions drawn. `Jun LCOM` 28,473.81, `PLOW`. |
| `stoic_live_trade3.png` | MNQ 5m. A bullish 1-2-3 with a drawn `ptb` at ~28,245. **`BE` marked on the chart** — stop moved to break-even. `sbs` / `SBS` levels. **+2.8R**, open position 13 @ 28244.42. `PWC` 28,306.75, `PLOW`, `PDH`. |
| `stoic_live_trade4.png` | The **same trade, later**: same entry 13 @ 28244.42, same `ptb`, same `BE`. Exit 13 @ 28417.50, **+4.5R**, held past the NY session into Asia. |

**Why this belongs in *this* audit.** Phase 2a exists because a rule can be recorded as a human
decision *on the belief that the material is silent*. **D-23 is the precedent** — it was rewritten
because `TPA` turned out not to be silent at all. An unread file in the main source directory is
where that belief goes wrong, and the sweeps could not have caught it: they check whether a rule
outran its **cited** sources, never whether an uncited source exists.

**Three things it changes.**

1. **§10.7's claim is false.** It calls `NQ3` *"the first fully-marked example with real prices, and
   the closest thing in the corpus to a test fixture."* `stoic_trade2.png` is fully marked with real
   prices, predates `NQ3` in the repo, and is **denser** — two counts and two PTBs against `NQ3`'s
   one. It is also a later snapshot of the **same session as `T1`**: §10.2's own execution list
   (7 @ 28231.75, 9 @ 28286.67) appears on it.
2. **A live-marked reset now exists as a fixture.** §2.4's reset is currently sourced only from
   narration (`SCALP`, `DISC` + `Q1.png`). `stoic_trade2.png` shows a bearish count completing and a
   bullish count starting, on one chart, with real prices — which is what Phase 3 needs.
3. **`BE` is drawn on a live chart** — at the time, §6 had no break-even rule at all and §6.1 only
   quoted `ET`'s *"put stop to break even"* at TP1. **Superseded:** the rule is now §5.4.5 / **D-25**,
   and reading the chart closely showed this claim overreached — `BE` records *where* the stop went,
   never *which event* moved it, so it corroborates the practice but **not** the trigger. See §10.9.

**And two level types the material uses but §7.3 does not define.** `PWC` (previous weekly close) and
`PLOW` (previous low of the week) are drawn on these charts and taught in the corpus — `PTBV @
00:25:54`: *"this line is the previous weekly close, that previous weekly close is my target right
now"*; `PTBV @ 00:04:02`; and `CST` teaches previous-week levels throughout. §7.3 defines
`PDH`/`PDL`/`PDC` and `HCOM`/`LCOM` and stops there, while §10.1/§10.2 already mention `PLOW` in
passing without a definition. This is a **missing** rule, not an invented one — the opposite of what
the sweeps hunt.

**Disposition.** Give the three files citation keys in §0 and worked examples in §10; correct §10.7;
open a row for the previous-week levels. **None of it is Phase 2a's job to write** — the audit's
output here is the finding. What Phase 2a must do is stop claiming a silence it has not tested.

---

## What the audit has already produced

**D-23 was rewritten before the sweep finished** — the decision itself is `docs/RULEBOOK.md` §11, and
`git log -- docs/RULEBOOK.md` has the rewrite. It is the model for what a
Phase 2a disposition looks like: a predicate that had been recorded as a human decision on the belief
that the material was silent, found contradicted, put back to the human, and returned to **J** with
an open row (**O-14**). It also cost the spec a blocker it did not previously know it had.

**F-13 is the second instance of the same failure**, caught one step earlier — a silence assumed over
files nobody had opened, found before any rule was written on it.

### The decision review, 2026-08-08

The sweeps' 25 `DECISION` rows were put to the user as a list: *which of these were your calls, and
which were guesses that should go to the SLM?* That is the audit doing its job — the sweep cannot
tell a decision from a guess, only that a rule leans on one. Five outcomes, none of which went to the
SLM:

| | Outcome |
|---|---|
| **D-18 / O-5** — the `k × ATR(n)` stop floor | **Deleted.** *"Stop after entry is the opposite extreme of the PTB."* ATR is never mentioned in the corpus; the mechanism was ours and its three constants were the open row. **O-5 closed by removing what needed it**, which unblocks L4 |
| **D-24** — *strong* close beyond the 10/20 | **Quantified: 10% of the candle's own high-low range.** 5.4.7b moves **J → P** |
| **D-24** — the Step 2 boundary exit | **Affirmed.** The user re-read it and kept it, knowing the corpus is silent. It stays a decision, not a citation |
| **D-17** — no bar cap | **Affirmed, and completed.** The walk ends *"either we hit an entry or it invalidates without an entry"* — a termination condition the rule did not have. New row §5.3.4a; §5.4.7 now cancels pending orders too |
| **D-25** — break-even | **New.** Stop to break-even when price trades beyond the Step 3 High/Low. Lands on `ET`'s own sentence at §6.1, so it is **cited**, not invented |

**Two things this changes about the audit's own findings.** F-8's second pointer (O-5) is gone. And
the biggest single piece of invented machinery in the spec — the ATR floor, which the sweeps had
classed a legitimate `DECISION` because it cited D-18 — **was removed by asking rather than by
sweeping**. No mechanical check would have caught it: it cited a real decision, in a real §11 row,
with a real open row for its constants. Only *"where did this predicate come from?"* catches that,
which is the question `claude_memories/audit-hard-rules-not-in-material.md` exists to force.

---

## Two rulings on the audit's own machinery

Both are the lead's, both were forced by the work, and the second departs from `docs/PLAN.md`'s
literal wording — so it is written down here rather than acted on quietly.

**1. The class table lives in this file, not in `docs/RULEBOOK.md` and not in `.artifacts/`.**
`docs/PLAN.md` asks the *audit output* to name the class per rule, so the rulebook needs no fifth
column. And `.artifacts/` is gitignored: it does not travel to the Windows box and does not survive a
regenerate. A classification kept only there would have to be redone by whoever opens the repo next,
which is how the first sweep's coverage gap survived. `docs/` is tracked; the class goes here.

**2. Status and class are different axes, and the status column stays as it is.**
`docs/PLAN.md`'s disposition table says a *human decision* rule "must be a D-row in §11 and marked
**P**, not **M**". Read literally that demotes all 17 decision-backed rows. It should not, because
§0's legend defines status as **computability** — *"M: computable from bars alone, no free
parameter"* — not as provenance. D-16's running extreme is a human decision **and** has no free
parameter; calling it **P** would assert the engine needs a number it does not need, and would make
**P** mean two different things in one column.

So: **status answers "can Phase 5 compile it?", class answers "where did the predicate come from?"**
The intent behind PLAN's rule — that a judgment must not hide inside a mechanical-looking rule — is
met by the Source column naming the D-row (it already does) plus the class table below. What the exit
gate is actually protecting is unchanged and unweakened: **no rule classed *invented* may stand as a
rule at all**, whatever its status tag.

The one place this needs care is the reverse case, which the status column *does* catch and which
F-12 shows the prose does not: a rule whose **source** is a decision, whose **status** is M, and whose
decision was never written down. `5.4.7c` is that shape and is checked in `sweep_D`.

## The classification — all 132 definitional rows

**The rule applied.** A row's class follows from its evidence: a `NO` verdict against a material
citation is ***cited***; a `DECISION` verdict is ***human decision***; a `YES` is a *candidate* and
was judged one at a time. Eleven of the 143 swept rows are prose, not rules, and are excluded here —
4 of those were `DECISION`, 7 were `NO`.

| Class | Count | Which |
|---|---|---|
| **Cited** | **109** | The 101 `NO` rows, plus 8 of the 10 `YES` after correction |
| **Human decision** | **23** | The 21 `DECISION` rows, plus 5.4.6 and 6.3c |
| **Invented** | **0** | — after dispositions; see the caveat below |

**The 10 candidates, one line each.** Seven were corrected to say what their source says; two were
decisions all along and now cite one; one was already right.

| Rule | Resolution | Class |
|---|---|---|
| 2.3.10 | *"swept by a wick"* → *"barely swept"*, matching `M1`; status **M → J** | cited |
| 5.3.10 | circular citation broken; the signal-record clause moved to an engine note | cited |
| 5.4.1 | `ET` via §5.2.3 added — it supplies the long/short pairing `PTBQ` §2 omits | cited |
| 5.4.6 | the `≥ m × R` inequality is ours; row now says so, `m` open on **O-10** | human decision |
| 6.3b | `OTV @ 1:07:32` added — the sentence that actually says *"where we enter"* | cited |
| 6.3c | now cites **D-20**, which owns the translation into 1-2-3 vocabulary | human decision |
| 6.6 | *"only"* dropped; `M1 @ 16:08` lists four management items, not one | cited |
| 7.1.4 | narrowed back to **long-only**, as `SCALP` states it | cited |
| 7.4.4 | *"three are mechanical"* → **one is**; §5.4.4 pointer corrected to §5.4.6 | cited |
| 7.5.4 | the false universal replaced; `SSS @ 53:51` cited and put in context | cited |

**The caveat, stated plainly: "0 invented" is not a clean bill of health.** The single largest
invented mechanism in the spec — the `k × ATR(n)` stop floor — was classed **`DECISION`** by the
sweep, correctly, because it cited a real D-row with a real open row for its constants. It was
removed on 2026-08-08 by **asking the human where the predicate came from**, not by any mechanical
check. Had that conversation not happened it would have passed this classification untouched. The
count below reports it.

## What moved out — the count, not minimised

| | |
|---|---|
| Rules **deleted** from §1–§9 | **2** — the ATR stop floor (old §5.4.4) and its constants row (old §5.4.5) |
| Open rows **closed by deletion** | **1** — **O-5**, closed by removing the mechanism that needed it, not by setting its three constants |
| Open rows **reframed to an SLM question** | **1** — **O-14**, from an unsourceable distance threshold to *"where does the expansion leg end"* |
| Rules **corrected** for saying more than their source | **10** |
| Rules **added** because the material or the human supplied them | **4** — §5.3.4a, §5.3.5a, §5.4.5 (break-even), and the split of §5.4.7 onto pending orders |
| Rules still classed **invented** | **0** |
| Source files found **unread** | **3** (F-13) |

**Net effect on Phase 5:** L4 unblocked (O-5 gone), L1 and L3 still gated on O-14.

## Exit gate — met, with one carry-over

`docs/PLAN.md` requires: every rule in §1–§9 carries a class; no rule classed *invented* is still
stated as **M**; the count moved to §12 or to the SLM is reported and not minimised.

All six items are done:

1. **Verify the findings.** All twelve verified against source; one reported claim rejected.
2. **`sweep_D`.** Coverage complete at 143 rows — 0 broken, 0 YES, 8 of 11 DECISION.
3. **Class all 132 definitional rows.** 109 cited, 23 human decision, 0 invented — above.
4. **Apply dispositions.** F-1 … F-12 all applied to `docs/RULEBOOK.md`.
5. **Re-check status tags.** 2.3.10 **M → J**, 5.4.7b **J → P**, 5.3.4 keeps **M** with the `PTBQ`
   contradiction disclosed, 5.4.7c keeps **M** and was re-affirmed by the user, §3.4 keeps **M** on
   grounds that never depended on the void corroboration.
6. **Report the count moved out.** Above, un-minimised, including the caveat that the largest
   invented mechanism was caught by asking rather than by sweeping.

**Carried out of this audit — all discharged 2026-08-08, in the two commits after it.** F-13's
disposition was about the corpus, not §1–§9, so it never gated this exit. Where each landed:

- The three charts → keys `T2` / `LT3` / `LT4` in §0, worked examples §10.8–§10.9, §10.7 corrected.
- The previous-week levels → **defined** in §7.3 as `PWC` / `PWH` / `PLOW`, all cited, with **O-16**
  opened for the one part the material does not pin (a weekly analogue of HCOM/LCOM).
- `TPA`'s management content → **D-26** (lower high is a cue, not an invalidation), **D-27** (HTF
  alignment is a confidence input, not a gate), and the **D-7 amendment** dropping 1m execution.

**Nothing in this file is outstanding.** It is a record of a closed phase; `docs/STATE.md` holds what
is true now and does not summarise it.
