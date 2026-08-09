---
name: audit-hard-rules-not-in-material
description: user directive — every hard rule in RULEBOOK.md that the material did not specify must be audited, because each one pre-decides what the SLM was supposed to discover
metadata:
  type: feedback
---

**Do not invent a hard rule to close a gap the material left open.** Where the material is silent or
vague, the job is to *set the question up for the SLM to work on*, not to write a crisp predicate and
move on. Every such rule has to be audited and justified before Phase 5 compiles it.

The trigger was `docs/RULEBOOK.md` §5.2.8, *"an inside candle is not a PTB"* — cited, so the rule
itself is sound — followed by a proposal to also define *inside-ness* (parent-bar reference vs
previous-bar). The user's response: *"why are you encoding the rules? You just have to set it up for
the SLM to figure it out — dont put in hard rules like this."*

**Update 2026-08-08 — the trigger example resolved, the rule did not change.** `insidebar.png`
(`IBD`) turned up in the material and *does* define inside-ness: one labelled Parent Bar with a run
of two Inside Bars referenced to it, so the reference is the **parent bar** — the nearest preceding
bar not itself inside. §5.2.8a is now cited, not invented. Read that as the rule working, not as it
being unnecessary: the predicate stayed out of the spec for five days until a source appeared, which
is the whole point. **The corpus is not finished, so "the material is silent" is always provisional.**

**The better worked example is now D-23.** A predicate that *did* get written — *a correction bar is
one whose body opposes the sequence direction, `close < open` for a long* — recorded as a decision on
the belief the material was silent. It was not: the ninth transcript (`TPA`) states a rival reading
in five distinct passages, and D-23's sole citation discriminated neither. The two readings pick different anchor
bars on 62.8% of candidates, so the invented predicate was silently setting the entry, the stop and R
on most pullbacks. Put to the user, **both** mechanical readings were rejected as over-specification
and the term went back to **J** with an open row (**O-14**). Note the shape: it was labelled a human
decision, which made it look settled, and only reading the whole corpus caught it.

**Update 2026-08-08 — the rule fires on conflicting abundance, not only on silence.** Working **O-14**
(where the expansion leg ends and the pullback begins), the corpus turned out to be loud: seven
passages across `TPA` and `PTBV`, both directions, two bar-by-bar walkthroughs. They settle the
*concept* — no pullback while price keeps making new extremes — but operationalize *"the first candle
that goes the other way"* **three different ways**, which disagree on inside and outside bars. So:
*the material having spoken is not sufficient*. When it speaks in rival operationalizations, the
agent still does not get to pick — enumerate them, attach the passages, and put them to the human.

**What the human then did with it — and the correction that matters.** The first answer was *"leave
O-14 open for the Phase 4 SLM"*; the second, later the same day, was to **pick the two-clause
reading** outright (**D-28**). Both times the choice was the human's, which is the part that
generalises. What does *not* generalise is the intermediate step this file previously recorded as
the lesson: **routing a rival-readings question to the SLM is not automatically right.** Once the
readings are enumerated with citations, Phase 4's stated deliverable — *"propose candidate
formalizations with the supporting passages attached"* — has already been produced by hand, and what
is left is a **choice**, which is a human decision under `CLAUDE.md`, not a model's output. Offer the
human the decision before parking it in a phase.

**Why:** a hard rule written to fill a silence is a **hypothesis wearing a spec's clothes**. It reads
as settled, it compiles, it never gets revisited — and it forecloses exactly the question Phase 4
exists to answer. `docs/PLAN.md` Phase 4 charters the SLM to *"propose candidate formalizations of the
fuzzy terms … with the supporting passages attached"*; a predicate already in the rulebook means the
SLM is scored against our guess instead of the material. It also inverts the standing directive in
`CLAUDE.md`: divergence from the labelled material is a **specification bug**, and a bug is much
harder to see when the spec asserts something the source never said.

**How to apply:**

- Before writing any rule, ask **where the number or predicate came from**. Material → cite it.
  Human → it is a **D-row in §11**, labelled a strategy decision. Neither → it does not go in;
  it becomes an **O-row in §12** or an SLM question.
- **"Material → cite it" needs the sources to agree.** If two or more passages support *rival*
  predicates, you do not get to pick the best-evidenced one. Count the readings, attach every
  passage, and put the choice to the human — that is a **D-row**, not an O-row parked in a later
  phase. **D-28** is the worked example.
- Status **J** already exists for terms the material *refuses* to quantify. Reach for **J** or an
  O-row before inventing an **M**. §0 says a proposed number for a **J** term needs the human.
- Watch for the shape: a rule that is more specific than every sentence backing it. §5.2.8's
  inside-bar exclusion is cited; a definition of *inside* would not have been.
- The audit itself is a plan item — see `docs/PLAN.md`, Phase 2a. It sweeps §1–§9 and classifies
  every rule as *cited* / *human decision* / *invented*, and the third class gets removed, demoted
  to §12, or converted into an SLM question.

Related: [[opus-expanded-role]] for who runs the audit; [[two-systems-in-the-corpus]] for the other
way a rule sneaks in that the 1-2-3 material never taught.
