# Run Comparison & Evaluation Objectivity — Design

Date: 2026-07-24. Status: draft for review (formalizes the comparison design
discussed after run `adb3c96ab6020c23`). Companion to
`2026-07-24-win-cuda-training-package-plan.md`.

Guardrails inherited unchanged from VISION.md: the SLM is an offline research
assistant; no model output touches the live signal path; education sources are
immutable and outrank model output (ADR 0004). Nothing in this design turns an
evaluation score into a production gate — the only live gate remains a
human-approved, signed SP0 release.

## 1. Problem

Run `adb3c96ab6020c23` produced citation_fidelity=0.20 on 699 held-out
examples. Three questions must be answered before iterating:

1. **Comparability** — how do we know run B is better than run A, beyond
   noise? (Today `scores.json` is even overwritten per run.)
2. **Objectivity** — the scoring proxy (token overlap vs cited narration) and
   the trading concepts themselves ("base", "consolidation", "choppy") are
   partly subjective. How do we iterate against subjective targets without
   fooling ourselves, and which risks do we accept explicitly?
3. **Blindness** — if every run is blind to the eval data, where does eval
   overfitting come from, and how should the split evolve?

## 2. Metric architecture: tiers of objectivity

Layer the metric so the objective parts gate mechanically and the subjective
parts are *measured proxies with a known error bar*, never silent judgment.

| Tier | Check | Nature |
|---|---|---|
| 0 | citation present; `video_id:hms` exists in corpus; timestamp within ± tolerance of a real record; output parses into the structured schema (setup/entry/stop/target/invalidation) | fully objective, deterministic |
| 1 | claim↔narration support via token/fuzzy overlap at a fixed threshold | deterministic **proxy** — biased, but *stably* biased |
| 2 (optional, later) | local pinned LLM judge (temp 0, pinned prompt+model+revision) scoring semantic support | advisory only; never gates, never compared across judge versions |
| H | human calibration audit (see below) | ground truth, sampled |

Rules:

- **`scoring_version`** is stamped into every `scores.json` together with the
  overlap threshold and tolerance parameters. Comparisons across different
  `scoring_version`s are refused by tooling. Changing the metric is allowed —
  it just starts a new comparison lineage.
- **Failure-mode buckets are first-class metrics**, not just one pass rate:
  (a) no citation, (b) citation not in corpus, (c) citation in
  corpus but weak overlap, (d) schema violation. Run-over-run movement of the
  hallucination bucket is more informative than the headline rate.

  **Correction (2026-07-25, empirical):** bucket (b) was named and reasoned
  about as "hallucinated". It is not. In run `adb3c96ab6020c23` all 224
  members cited a **real** corpus `video_id`; none was invented. The bucket
  conflates *invented identifier* with *real identifier, wrong record* —
  opposite failures with opposite fixes. Splitting it requires a
  `scoring_version` bump (WP7). Until then, every use of this bucket carries
  the correction. Note also that Tier 0 above specifies "timestamp within ±
  tolerance"; the shipped scorer does an **exact `(video_id, hms)` lookup**
  with no tolerance, so near-miss timestamps fall into (b) as well. See
  ADR-0021.
- **Human calibration audit**: per `scoring_version`, sample ~50 scored
  examples (stratified pass/fail), human-label "supported / not supported",
  record Tier-1 agreement (precision/recall vs human) in
  `evaluation/calibration/<scoring_version>.json`. This converts "the metric
  is subjective" into "the metric has a measured 12% false-fail rate" —
  a known error bar we accept. If agreement degrades, revise the metric and
  bump `scoring_version`.

**Accepted risk (explicit):** Tier 1 will fail some genuinely-supported
paraphrases and pass some coincidental overlaps. That is tolerable because
(a) the bias is constant across runs, so *deltas* remain meaningful;
(b) calibration quantifies it; (c) every surviving candidate still passes a
human before the rulebook. We optimize a proxy, we ship on human review.

## 3. Subjective concepts → deterministic predicates

Example: "price built a base / consolidated, then broke out." No datafeed
column says "base". The resolution path (this is the core VISION handoff, made
concrete):

1. **The SLM never detects the concept from the datafeed.** It only proposes
   the concept's *semantics* with citations ("educator calls this a base:
   ~12+ bars, range under ~0.5× ATR, at prior day high" + `video_id:hms`).
2. **A human turns the proposal into a parameterized deterministic predicate**
   in ordinary Python, e.g.
   `is_base(bars, n_min, atr_frac, band_ticks) -> bool` — pure function of
   the feed, unit-tested, parameters explicit and versioned in the rulebook.
3. **Fixtures anchor the predicate to the education source.** For each cited
   segment, pull the matching historical bars (Databento feed is already in
   `data/historical/`) and assert: predicate fires on the moments the educator
   called a base, and does not fire on nearby counterexamples. The video
   citation becomes a *golden test case*, which is exactly what makes the
   subjective term auditable.
4. **Irreducible ambiguity goes to the decision queue**, not into parameters:
   if a human cannot extract parameters the sources support, the concept is
   logged as an open question (the pipeline's conflict-surfacing task exists
   for this), and no rule ships until resolved.

**Accepted risk (explicit):** the predicate will disagree with the educator's
eye on edge cases. Acceptable because the rulebook is versioned and signed,
backtests price the disagreement, and the banned alternative — model judgment
in the live path — is a VISION non-goal. We prefer a slightly-wrong rule we
can measure over an unmeasurable "feel".

## 4. Comparison protocol

### 4.1 Per-run artifacts (fixes current gaps)

- `scores.json`, `predictions.jsonl` move into `runs/<run_id>/evaluation/`
  (**bug**: today they land in `datasets/v1/` and are clobbered per run).
- Run manifest gains an `evaluation` section: scores path + sha256, headline
  metrics, `scoring_version`, eval-set digest.
- Every prediction row keys on a **stable example id**
  (`sha256(task || video_id || hms || prompt)[:16]`), enabling paired
  comparison.
- Manifest gains an optional **`hypothesis` field, written before launch**
  ("1 epoch instead of 2 will cut hallucinated citations"). Pre-registration
  keeps iteration honest — a run whose gain wasn't predicted is treated as a
  lead, not a result.

### 4.2 Baseline

Score the **un-fine-tuned base model** (pinned Qwen3-8B revision) once per
eval-set/scoring version, stored as run `baseline-<digest>`. Without the zero
point we cannot claim the fine-tune helps at all.

### 4.3 `compare` command

`uv run python -m stoic_training.compare <run_a> <run_b>`:

- **refuses** unless corpus digest, eval digest, and `scoring_version` match;
- headline deltas per task and per failure bucket;
- **paired flips** on stable example ids: fixed / broke / unchanged, with a
  McNemar exact p-value — on 699 examples an aggregate +3% is noise, but
  "fixed 41, broke 6" is a real signal;
- lists the flipped example ids so regressions are inspectable one by one.

### 4.4 Runs index

Append-only `runs/index.jsonl`: run_id, date, config hash + the knobs that
differ from the previous run, hypothesis, headline metrics, scoring_version.
One line per run; the experiment history reads at a glance.

## 5. Split protocol v2 and why blind runs still overfit

### 5.1 Where the leak is

Individual runs never see eval data. The leak is **us**: we read the score,
pick the next hyperparameter/template because it raised the score, and repeat.
Selection pressure transmits information about the fixed 699 examples through
our choices — adaptive overfitting (the Kaggle public-leaderboard effect).
Each choice banks a little noise; after ~20 iterations against ±3% noise you
can "gain" 5–10% that generalizes to nothing. Blindness of the *model* does
not make the *process* blind, because the process's objective function is a
fixed finite sample.

### 5.2 Countermeasures

- **Two-tier eval**: split the current eval videos into
  **dev-eval** (iterate freely, read scores every run) and
  **sealed holdout** (scored only when promoting a release candidate).
  Unsealing is logged in a committed `splits/unseal-ledger.md` (run id, date,
  reason). Budget: single-digit unsealings per split version.
- **Paired significance** (4.3): accept an improvement only when flips beat
  noise, not when the headline moves.
- **Pre-registration** (4.1): decide the next change before seeing where it
  helps.
- **Refresh path**: newly mined videos are quarantined into the holdout pool
  by default (they are the truly-unseen future), and a split-v2 can retire an
  over-exposed eval set. Split versions are immutable and never mixed.

### 5.3 Split geometry (the "non-contiguous" question)

- **The video stays the atomic split unit.** Within-video splits (records or
  time slices) leak hard: adjacent keyframes share narration, context, and
  the educator's phrasing, so a record-level split scores generalization we
  don't have. This is non-negotiable.
- Videos have no meaningful "contiguity" between them, and assignment is
  already seeded-random (seed 20260724), stratified 1× concept / 1×
  case_study / 1× live_session. So the split is already non-contiguous in the
  only sense that applies; the useful upgrade is **stratified dev/holdout
  partitioning of eval videos** (and of future videos), not finer granularity.
- **k-fold by video** is affordable (a run is ~45 min ⇒ 5-fold ≈ 4 GPU-hours)
  and is the recommended tool when a config decision looks split-sensitive:
  it yields a variance estimate across folds instead of trusting one 3-video
  sample. Not the default loop — a checkpoint before big decisions.
- Known limit to accept: with 16 videos, any split is coarse. Fold variance
  tells us how coarse; more mined videos are the real fix.

## 6. Work packages

| WP | Scope | Size |
|---|---|---|
| WP1 | scores/predictions → run dir; manifest `evaluation` section; `scoring_version` + params stamped; stable example ids | S |
| WP2 | `compare.py` (guards, buckets, paired flips + McNemar); `runs/index.jsonl` writer; `hypothesis` field | M |
| WP3 | baseline scoring run of pinned base model (one ~2 h GPU pass) | S + GPU |
| WP4 | split v2: dev/holdout partition, unseal ledger + tooling refusal without `--unseal`, new-video quarantine rule | S |
| WP5 | calibration audit tooling + first 50-example human audit; failure-bucket metrics in `scores.json` | M |
| WP6 (later) | Tier-2 advisory judge; k-fold runner | M |
| WP7 | `audit` command implementing the mechanical checks of ADR-0021 (per-stratum re-derivation, n<20 flagging, degenerate-distribution detection, raw-sample dump per bucket); split bucket (b) into `citation_id_invented` / `citation_record_not_found` under `scoring_version` "2" | M |
| WP8 | decoding probe on the 109 `no_citation` example_ids of `adb3c96ab6020c23` (details below) | S + GPU (~15 min) |

### WP8 — decoding probe (approved 2026-07-25, run AFTER the chain completes)

`no_citation` (109 rows) is truncation: median 1123 chars vs 262 for passing
rows, and 105 of 109 end mid-word. The trailing `Citation:` line is last in the
format, so hitting the cap deletes exactly it. But the long outputs are
degenerate repetition loops under `do_sample=False` greedy decoding with no
`repetition_penalty` and no `no_repeat_ngram_size`, so raising the budget alone
may only buy a longer loop.

The probe re-runs **only those 109 example_ids** in three arms — (i) 1024
tokens, decoding unchanged; (ii) 256 tokens + `repetition_penalty`;
(iii) 1024 tokens + `repetition_penalty` — and reports how many emit a trailing
citation in each. This separates "needed room" from "loops forever" for ~15 GPU
minutes instead of a 2-hour full pass.

Constraints: it is a **diagnostic, not a run of record**. Generation config is
hashed into `baseline_run_id`, so changing it mid-chain would fork the
comparison lineage; probe output lands under `runs/<id>/evaluation/probes/` and
never overwrites `scores.json`. Do not change the main chain's decoding config
on the strength of the probe without a fresh full run under a stated
hypothesis.

Order: WP1 → WP2 → WP3 (WP4/WP5 parallel). Execution per VISION: Sonnet
subagents implement, Opus audits, top-level closes the loop. All artifacts
stay under `<repo>/.artifacts/`; all code/config/ledger changes are committed.
Unit tests stay CPU-only and must skip cleanly off the GPU box; **any code
path that touches transformers generation APIs gets a stub-based regression
test** (lesson from the `apply_chat_template` BatchEncoding crash of
2026-07-25).

## 7. Non-goals

- No eval score ever gates a live release; that gate is human + signed SP0.
- No LLM judge as a blocking metric.
- No within-video splits, whatever they'd do for the numbers.
- No metric chasing: a run that improves the headline but grows the
  hallucinated-citation bucket is a regression by definition.
- No reporting a derived number without the ADR-0021 audit, and no
  "the fine-tune helps" claim that does not name which of
  format / grounding / selection it refers to.
