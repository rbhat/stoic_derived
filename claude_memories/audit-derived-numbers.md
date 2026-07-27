---
name: audit-derived-numbers
description: User directive — adversarially audit every number derived from a test before reporting it
metadata:
  type: feedback
---

Every number that comes out of a test or eval run is presumed invalid until it has survived an
adversarial audit. Do not report, quote, or decide on a derived number before auditing it. The
full rule is committed at `docs/architecture/adr/0021-adversarial-audit-of-derived-numbers.md`
(ten checks, each traceable to a real incident in this repo) — read it, don't reconstruct it.

The four that catch the most: read raw model output before trusting any aggregate; treat a
suspiciously clean number (exact 50/50, 0.00/1.00 everywhere) as a symptom of a broken generator;
disaggregate pooled metrics over heterogeneous strata before interpreting; and check that a bucket
name actually describes what is in the bucket.

Specific to fine-tuning claims: "the fine-tune helps" is not reportable. Name which of **format
acquisition / grounding / selection** the claim is about and cite per-stratum evidence for that
one. A delta against a baseline that cannot pass by construction measures the floor, not capability.

**Why:** three numbers this tooling produced in 24 hours were confidently reported and all three
were wrong or meaningless — a 0.00 that was a truncated-generation bug, a bucket labelled
"hallucinated" of which 0/224 were hallucinations, and a "3 seconds away" that was segment-density
noise. Each was arithmetically correct and none had been attacked.

**How to apply:** the audit costs more than the computation, and that is the intended trade —
compute is cheap here, a wrong conclusion sends a human to write trading rules against a capability
the model does not have. Record "checked, clean" too. See [[eval-comparison-wp-progress]].
