---
name: slm-decides-l2-fuzzy-terms
description: User directive 2026-08-09 — L2's four unquantified terms go to Phase 4's SLM to propose, not to the agent to decide; if it cannot ground one, it comes back to the human and never gets a default
metadata:
  type: feedback
---

**L2's four unquantified terms are routed to Phase 4's SLM.** They are *"meaningful"* for the Step 1
break and close, *"meaningful close"* for Confirmed Step 3, an **obvious base**, and **boundary
selection** — the four injected predicates in `stoic/sequence.py`'s `Judgment`.

**Why:** the user's standing position is that these are exactly what the SLM exists to discover from
the material. Deciding them cold — by the agent, or by asking the human to pick a number with no
bars in front of them — pre-empts that, which is the failure
[[audit-hard-rules-not-in-material]] names. The SLM proposes with passages attached; `VISION.md`
keeps it offline and out of the live path, so it never decides.

**How to apply:** do not offer to define these terms, and do not treat "the human decides" as the
default disposition for a **J** term that the SLM has not been asked about yet. Route it, and say so.
Two things survive the routing: a proposal still lands as a **D-row in §11** with the human's
confirmation (the **D-9** pattern, and §0's rule that a number for a **J** term is a strategy
decision), and **a term the SLM cannot ground comes back to the human rather than receiving a
default**. An unfilled predicate is the correct state — see [[measure-after-the-engine-runs]] for the
adjacent case where the user chose to decide and build rather than gate on measurement first.
