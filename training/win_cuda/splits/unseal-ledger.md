# Unseal ledger

Every scoring run against a **sealed holdout** eval set is appended here,
automatically, by `stoic_training.evaluate --unseal "<reason>"`. Refusing to
score the holdout without that flag -- and writing this file when it is
given -- is the mechanism that keeps the holdout a holdout.

Why (design doc `2026-07-24-eval-comparison-design.md` section 5.2): runs are
blind to eval data, but the iteration loop is not. Reading a score and
choosing the next change because it raised that score transmits information
about the fixed eval sample through our choices -- adaptive overfitting. The
dev set absorbs that pressure; the holdout only stays an honest estimate for
as long as it is rarely looked at.

**Budget: single-digit unsealings per split version.** Not a soft target. If
the count approaches ten, the holdout has been consumed: retire it and cut a
new split version rather than pretending the number still generalizes. Unseal
only to score a release candidate, never to check whether an idea worked.

New rows are appended by tooling; do not rewrite or delete history.

| run_id | date (UTC) | eval set | reason |
|---|---|---|---|
