# SLM Evaluation: Learnings and Distance to Goal

Date: 2026-07-25. Status: handoff note, written for a reader with no prior
context. Companions: `docs/superpowers/specs/2026-07-24-eval-comparison-design.md`
(the protocol), `docs/superpowers/specs/2026-07-25-baseline-redo-decision.md`
(why the first baseline was scrapped), `docs/architecture/adr/0021-adversarial-audit-of-derived-numbers.md`
(the reporting rule this note is written under).

---

## 1. What the SLM is for

Per VISION.md the SLM is an **offline research assistant only**. It never sits
in the live signal path. Its job is to read the Stoic Traders education corpus
and propose *rule candidates with citations*, which a human then converts into
deterministic Python predicates. The eval design (§3) makes the handoff
concrete and it matters for reading every number below:

1. The SLM proposes a concept's semantics **with a `video_id:hms` citation**.
2. A human turns the proposal into a parameterized predicate,
   `is_base(bars, n_min, atr_frac, band_ticks) -> bool`.
3. **The citation is used to pull the matching historical bars** from
   `data/historical/` and build a fixture that anchors the predicate to the
   source.

Step 3 is why citation correctness is the whole ballgame. A proposal with a
wrong citation is not "partially useful" — it anchors a golden test case to the
wrong moment in the tape, which is worse than producing nothing.

## 2. The measurement, stated honestly

Eval set: 699 held-out examples = **349 `rule_candidate` + 349 `cited_qa` + 1
`conflict_check`**. Corpus: 2233 records across 16 videos (55–277 segments per
video). Scorer: `scoring_version` "1", exact `(video_id, hms)` corpus lookup,
token-overlap threshold 0.30. Generation: `max_new_tokens=256`,
`enable_thinking=False`, `do_sample=False` (greedy).

### Fine-tuned run `adb3c96ab6020c23`

`citation_fidelity = 0.209` (146/699). **This pooled number should not be
used.** It averages two tasks with disjoint failure modes:

| task | n | pass | dominant failure |
|---|---|---|---|
| `rule_candidate` | 349 | **0.395** | `weak_overlap` 211 (.605) — and *nothing else*: 0 not-in-corpus, 0 no-citation, 0 schema |
| `cited_qa` | 349 | **0.023** | `citation_not_in_corpus` 224 (.642), `no_citation` 109 (.312) |
| `conflict_check` | **1** | 1.0 | n=1; `conflict_handling = 1.0` is not a metric |

Per category: case_study 0.116 (n=138), concept 0.236 (n=373), live_session
0.229 (n=188). Generation health clean: 0 truncated reasoning, 0 empty
predictions.

### Naive baseline `baseline-d7ffd44e388deb0d` (stock prompt)

`citation_fidelity = 0.000`. Buckets: `schema_violation` 349 + `no_citation`
349. Legitimate despite looking identical to the *invalid* first baseline —
health is clean and raw outputs are coherent, substantive prose. The split is
structural: `rule_candidate` is gated on schema, `cited_qa` on the trailing
citation line, and the stock prompt states neither contract.

`compare baseline-d7ffd44e388deb0d adb3c96ab6020c23`: delta +0.209, paired
flips **fixed=147, broke=0, unchanged_pass=0**, McNemar p=1.1e-44.
Overwhelming and **near-tautological** — `unchanged_pass=0` means the floor
passed nothing, by construction. Per ADR-0021 §E this is a formatting delta,
not a capability measurement.

### Instructed baseline `baseline-5175d80ffdbad8c7`

Running at time of writing (ETA ~01:26 UTC 2026-07-26). This is the
**meaningful zero point**: base model, same contract stated in the prompt. The
number that matters is `fine-tuned − format_instructed`, not
`fine-tuned − naive`.

## 3. What the fine-tune actually bought

Decomposed per ADR-0021 §F. All three are real; only the first two are large.

**Format acquisition — complete.** `schema_violation` 349 → 0. The model
learned the output contract perfectly. This is genuine but cheap: it is also
what a prompt can buy, which is exactly what baseline #3 will price.

**Grounding — complete and underrated.** The naive baseline invents
identifiers (it emitted *"in video_id 123"*). The fine-tuned model **never
invented one: 0 of 224** non-resolving citations used a fabricated `video_id`;
every one named a real corpus video. The headline metric cannot see this,
because an invented id and a real-but-wrong id land in the same bucket. This is
the most valuable thing the fine-tune taught and it is currently unmeasured
(WP7 splits the bucket to fix that).

**Selection — did not happen.** See below. This is the capability the project
actually needs.

## 4. Why `cited_qa` fails, and why it is not a training problem

This is the central finding. The two tasks are not two difficulties of one
skill; they are different skills, and only one of them was ever being tested.

**`rule_candidate` hands the model the answer.** The prompt literally opens:

> `Narration window (video concept_simple_stoic_setups_sss, around 00:01:55): "…"`

The `video_id` and `hms` are *in the prompt*. Emitting the citation is a copy,
not a retrieval. This is why 349/349 of its citations resolve to a real,
exact corpus key and its only failure mode is `weak_overlap` — the body text it
generates does not lexically overlap the narration at ≥0.30.

**`cited_qa` gives it nothing.** The whole prompt is:

> `What does the course say about "Breakout at Previous Daily High"?`

No corpus, no candidates, no retrieval mechanism. The model must recover the
correct `(video_id, hms)` out of 2233 segments from parametric memory alone.
It cannot, and the failure is unambiguous:

- **cited `video_id` == gold `video_id` in 0 of 224 cases.**
- Output is degenerate: `concept_the_only_trading_video…` receives timestamp
  `00:58:24` in 71% of its citations; 8 distinct timestamps stand against 232
  real segments in that video.

A caution about a statistic that looks reassuring and is not: the cited
timestamps sit a median of 3 seconds from *some* real segment. That is an
artifact of segment density (any timestamp is seconds from some segment), not
evidence of near-misses. Distance to **gold** is the only meaningful measure,
and by it the model is wrong every single time.

**Conclusion: closed-book retrieval over the corpus is not a capability
fine-tuning was going to deliver, and `cited_qa` as constructed measures a task
the system has no mechanism to perform.** The fix is architectural — retrieval
that supplies candidate segments — not another training run.

## 5. Why `no_citation` (109) is a decoding bug, not a model verdict

Median length 1123 chars against 262 for passing rows; **105 of 109 end
mid-word**. The `Citation:` line is last in the format, so hitting the
256-token cap deletes precisely it. But the long outputs are degenerate
repetition loops:

> "…the trade that you take on the day one of the month and this is the trade
> that you take on the day two of the month and this is the trade that you take
> on the day three…"

Decoding is `do_sample=False` greedy with no `repetition_penalty` and no
`no_repeat_ngram_size` — the classic recipe for loops in an 8B model. So
raising `max_new_tokens` alone would likely buy a longer loop, not a citation.
WP8 (approved, queued behind the chain) settles this in ~15 GPU minutes by
re-running only these 109 ids across three decoding arms.

Until WP8 lands, **109 of 699 rows (15.6%) are scored against a decoding
artifact**, and `citation_fidelity = 0.209` is therefore a lower bound of
unknown tightness.

## 6. Methodology learnings

The reporting rule is ADR-0021; it exists because of these. In order of how
much damage each did:

1. **A confident, clean number is a symptom, not a result.** The first baseline
   read `0.00` across the board with an exact 349/349 split and had measured
   nothing — 639/699 generations truncated mid-`<think>`. Read raw model output
   before trusting any metric.
2. **Bucket names are hypotheses.** `citation_not_in_corpus` is documented as
   "(hallucinated)". Zero of 224 were hallucinations. The name drove the
   analysis for hours before anyone checked it against raw data.
3. **Pooled metrics over heterogeneous strata are actively misleading.** 0.209
   is the average of a copy task at 0.395 and an impossible retrieval task at
   0.023. No decision should ever have been made on it.
4. **Code semantics beat doc semantics.** Tier 0 of the design specifies
   "timestamp within ± tolerance"; the scorer does an exact dict lookup. Any
   near-miss timestamp is therefore scored as not-in-corpus.
5. **Reference-class discipline.** "3 seconds from a real segment" felt like
   precision and was noise; the null was never computed.
6. **Test stubs stricter than the real API hide the worst bugs.** The
   `apply_chat_template` stubs had fixed signatures instead of `**kwargs`, so
   nothing caught the missing `enable_thinking` flag that produced the invalid
   baseline.
7. **Operational numbers are derived numbers.** A 3-hour host suspend made a
   healthy job look 2.4× slower (`CLOCK_MONOTONIC` excludes suspend, UTC does
   not), and a 93-second throughput sample read 5.8 s/step against a true 9.5.

## 7. Distance to the goal

The goal is not a metric target. It is: **can a human sit down with this
model's output and build deterministic predicates anchored to correct source
citations?**

**Where we are:**

- *Proposing a rule from a supplied segment*: **usable now, with review.**
  Every citation resolves to a real exact corpus record; 39.5% clear the
  overlap bar outright. The failures are lexical-overlap misses, and given the
  scorer's known bias (§Accepted risk in the design doc) an unknown share of
  the 211 `weak_overlap` rows are substantively fine. **This is the workflow to
  use today.**
- *Answering a question and finding its support*: **not usable, and not close.**
  0/224 correct video. This needs retrieval, not training.
- *Conflict surfacing*: **unmeasured.** n=1 in the eval set.

**What is genuinely blocking, in order:**

1. **No retrieval layer.** The single largest gap. Until candidate segments are
   supplied at inference, `cited_qa` cannot work at any training budget.
2. **The eval set cannot price what we care about.** 1 `conflict_check`
   example; two tasks pooled into one headline; a metric blind to
   "wrong pointer, right content."
3. **Metric calibration never done.** WP5's 50-example human audit is still
   outstanding. Every rate in this document has an unmeasured error bar. This
   is the cheapest high-value item on the list.
4. **15.6% of rows contaminated by a decoding artifact** (WP8, ~15 min).
5. **Corpus scale.** 16 videos, 2233 segments. Split geometry is coarse and no
   amount of protocol fixes that.

**What is not blocking:** the fine-tune itself. It did its job — format and
grounding are solved. More epochs, more LoRA rank, or a bigger base model
address none of the five items above.

## 8. Next actions

| # | action | why | cost |
|---|---|---|---|
| 1 | Let the chain finish; compare fine-tuned vs `baseline-5175d80ffdbad8c7` | the only honest capability delta | running |
| 2 | WP5 human calibration, 50 examples | puts an error bar on every number here | human hour |
| 3 | WP8 decoding probe | de-contaminates 15.6% of rows | 15 GPU min |
| 4 | WP7 `audit` command + bucket split under `scoring_version` "2" | makes ADR-0021 mechanical; separates invented from misresolved | M |
| 5 | Tier-2 judge (WP6) on the 224 misresolved citations | answers "wrong pointer, right content?" — unanswerable by the exact-key scorer | M |
| 6 | Design a retrieval path for `cited_qa`, or retire the task as constructed | the real blocker | design first |

Item 6 deserves a design discussion before any code. The honest options are
supplying candidates at inference (RAG), reframing `cited_qa` as open-book, or
accepting that closed-book retrieval is out of scope and scoring only
`rule_candidate`. Choosing by measurement rather than by preference requires
item 2 first.

## 9. Artifact map

- Runs: `.artifacts/training/runs/{adb3c96ab6020c23, baseline-d7ffd44e388deb0d,
  baseline-5175d80ffdbad8c7}/evaluation/{scores.json, predictions.jsonl}`
- Invalid, retained as a record: `baseline-211b3f1a05efed81` (do not cite)
- Index: `.artifacts/training/runs/index.jsonl`; chain log
  `.artifacts/training/logs/chain3-20260725T094144.log`
- Corpus: `edu/derived/dataset.jsonl`; eval set
  `.artifacts/training/datasets/v1/eval.jsonl`
- Env trap: `uv run` **must** run with cwd `training/win_cuda`, and never while
  a GPU job is live (it resyncs the venv). Use
  `.artifacts/training/venv/bin/python3 -m stoic_training.<cmd>` directly instead.
