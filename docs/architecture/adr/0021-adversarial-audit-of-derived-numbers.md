# ADR-0021: Every Derived Number Is Presumed Invalid Until Adversarially Audited

- Status: Accepted
- Date: 2026-07-25

## Context

Within 24 hours, three numbers produced by this repo's own evaluation tooling
were confidently reported and all three were wrong or meaningless:

1. `baseline-211b3f1a05efed81` reported `citation_fidelity = 0.00` over 699
   examples. It measured nothing: 639 of 699 generations were truncated
   mid-`<think>`, so the model never emitted an answer. The number described a
   generation bug, not a model.
2. Run `adb3c96ab6020c23` reported bucket `citation_not_in_corpus = 224`, a
   bucket this repo's own design doc labels "(hallucinated)". Zero of the 224
   were hallucinations — every one cited a **real** corpus `video_id`. The
   label was a hypothesis that had never been checked against raw output.
3. A follow-up statistic, "median 3s from the nearest real segment", was read
   as near-miss precision. It was an artifact: videos hold 55–277 segments, so
   *any* timestamp is seconds from some segment. The meaningful measure,
   distance to the **gold** citation, showed the cited video was wrong in
   224 of 224 cases.

The common factor is not carelessness about arithmetic. Each number was
arithmetically correct and each was reported because it was *available*, not
because anything had tried to break it. A metric pipeline that is trusted by
default converts a silent upstream failure into a confident downstream claim.

This project's stakes make that unacceptable: the SLM's job under VISION.md is
to mine education into rule candidates that a human turns into deterministic
predicates. A wrong eval number does not cost a leaderboard position — it sends
a human to write rules against a capability the model does not have.

## Decision

**A number derived from a test or evaluation run is presumed invalid until it
has survived a documented adversarial audit.** No derived number may be
reported to the user, quoted in a document, or used to justify a decision until
the audit below has been executed and its result recorded alongside the number.

The audit is ten checks. Each exists because it caught a real defect here.

### A. Did the machine produce anything at all?

1. **Generation health first, metric second.** Inspect
   `generation.health` (`truncated_reasoning`, `empty_predictions`,
   `reasoning_blocks`) *before* reading any score. A nonzero truncation count
   invalidates the run; the metric is not "low", it is absent.
2. **Read raw outputs before trusting any aggregate.** Minimum three full
   samples per failure bucket, read end to end, not excerpted by the tool that
   computed the metric.

### B. Is the number too clean to be real?

3. **Suspicious cleanliness is a symptom, not a result.** Exact 50/50 splits,
   `0.00` or `1.00` across every sub-metric, or a bucket count that exactly
   equals a task's cardinality must be *explained structurally* or rejected.
   Both the invalid baseline and the legitimate naive baseline produced an
   exact 349/349 split; only reading raw output distinguished them.

### C. Does the number mean what its name says?

4. **A bucket name is a hypothesis, not evidence.** Verify every label against
   raw data before using the label's connotation in an argument.
   `citation_not_in_corpus` conflates *invented identifier* with *real
   identifier, wrong record* — operationally opposite failures with opposite
   fixes.
5. **Verify the implementation against the spec the number claims to
   implement.** Tier 0 of the eval design specifies "timestamp within ±
   tolerance of a real record"; the scorer performs an exact `(video_id, hms)`
   dict lookup with no tolerance. A number inherits the semantics of the code,
   never of the doc.
6. **State what the number is blind to.** Every reported metric carries an
   explicit "this cannot distinguish X from Y" line. Exact-key citation
   scoring cannot distinguish a wrong pointer to right content from a wrong
   answer.

### D. Is the number an average over things that should not be averaged?

7. **Disaggregate before interpreting.** Any pooled metric over heterogeneous
   strata is reported per stratum. Pooled `citation_fidelity = 0.209` concealed
   `rule_candidate = 0.395` and `cited_qa = 0.023` — two tasks whose failure
   modes are not merely different in degree but disjoint in kind.
8. **Report n per cell and refuse conclusions below threshold.**
   `conflict_handling = 1.0` was one example passing. Cells with n < 20 are
   reported as counts, never as rates.

### E. Is the comparison honest?

9. **Reference-class check on every distance, similarity, or "close to"
   statistic.** Compare against the null the measure would produce by chance
   given the data's density. Without it, "3 seconds away" and "wrong video"
   look identical.
10. **A delta against a floor that is zero by construction is not a measurement
    of capability.** It measures the floor. Where the comparison baseline
    cannot pass by construction, the result is reported as a
    formatting/compliance delta and an additional baseline capable of passing
    is required before any capability claim.

### F. The fine-tuning corollary

Fine-tuning demonstrably helps in this repo — `schema_violation` fell 349 → 0
and hallucinated identifiers fell to zero. **That it helps is not in dispute;
what and how much are, and those must be measured separately.** A single
headline delta against a naive baseline is forbidden as evidence of capability
gain, because it sums at least three distinct effects:

- **format acquisition** (learning the output contract),
- **grounding** (citing real corpus identifiers rather than invented ones),
- **selection** (citing the *correct* record).

Every fine-tuning claim names which of the three it is about, and cites the
per-stratum evidence for that one. "The fine-tune helps" is not a reportable
result.

### G. Operational numbers count

Wall-clock, ETA, and progress figures are derived numbers under this ADR.
`CLOCK_MONOTONIC`-based `elapsed_s` excludes host suspend while UTC does not; a
3-hour suspend on 2026-07-25 made a healthy job look like a 2.4× slowdown, and
a 93-second throughput sample read 5.8 s/step against a true 9.5 s/step.
Short spot samples are not evidence; state the window and the clock source.

## Consequences

- Reporting a number costs more than computing it. This is the intended trade:
  compute is cheap here and a wrong conclusion is expensive.
- Some audits will find nothing, and the audit is still recorded. "Checked,
  clean" is the artifact that makes the next number trustworthy.
- Documents that quote metrics — designs, plans, learnings notes — carry the
  disaggregated form and the blindness statement, not the headline alone.
- Labels already shipped in code and docs may be wrong. `citation_not_in_corpus`
  is known-misleading and is scheduled for a split under a new
  `scoring_version`; until then every use of it carries the correction.
- This ADR does not gate anything live. Consistent with ADR-0011 and VISION.md,
  no evaluation number gates a release; the only live gate remains a
  human-approved signed SP0 release. This rule governs *honesty of reporting*,
  not promotion.

## Compliance

- `scores.json` already stamps `scoring_version`, generation config, and
  `generation.health`; `compare.py` already refuses mismatched digests and
  versions. These satisfy checks 1 and 5 mechanically.
- Checks 3, 4, 7, 8 are implemented as an `audit` command over a scored run
  (WP7 in the eval-comparison design): it re-derives per-stratum rates, flags
  cells with n < 20, flags degenerate distributions, and samples raw
  predictions per bucket for human reading.
- Checks 2, 6, 9, 10 are human judgment and are enforced by review: a
  pull request or report that quotes a derived number without its audit record
  is incomplete.
- Any code path touching transformers generation APIs keeps a stub-based
  regression test with `**kwargs`-tolerant stubs (the `apply_chat_template`
  lesson: stubs stricter than the real API hide exactly the bug class that
  produces confident empty metrics).
