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
previous-bar). The material never defines it. The user's response: *"why are you encoding the rules?
You just have to set it up for the SLM to figure it out — dont put in hard rules like this."*

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
- Status **J** already exists for terms the material *refuses* to quantify. Reach for **J** or an
  O-row before inventing an **M**. §0 says a proposed number for a **J** term needs the human.
- Watch for the shape: a rule that is more specific than every sentence backing it. §5.2.8's
  inside-bar exclusion is cited; a definition of *inside* would not have been.
- The audit itself is a plan item — see `docs/PLAN.md`, Phase 2a. It sweeps §1–§9 and classifies
  every rule as *cited* / *human decision* / *invented*, and the third class gets removed, demoted
  to §12, or converted into an SLM question.

Related: [[opus-expanded-role]] for who runs the audit; [[two-systems-in-the-corpus]] for the other
way a rule sneaks in that the 1-2-3 material never taught.
