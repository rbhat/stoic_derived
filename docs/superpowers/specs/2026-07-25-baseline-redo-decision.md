# Baseline redo: why the first zero point was invalid, and what replaces it

Date: 2026-07-25
Status: accepted, implementation in progress
Supersedes: the baseline described in `2026-07-24-eval-comparison-design.md` section 4.2 (the
run-id derivation and the single-baseline assumption)

## 1. What happened

Run `baseline-211b3f1a05efed81` (un-fine-tuned Qwen3-8B over `datasets/v1/eval.jsonl`, 699
examples, ~2.6 GPU-hours) scored `citation_fidelity 0.00` with a suspiciously exact bucket split:

| bucket | n | rate |
| --- | --- | --- |
| schema_violation | 349 | 0.50 |
| no_citation | 349 | 0.50 |
| citation_not_in_corpus | 0 | 0.00 |
| pass | 0 | 0.00 |

The split is exact because it is a partition by task, not a measurement:
`rule_candidate` (349) all failed the Tier-0 structural gate, `cited_qa` (349) all failed the
trailing-citation gate, `conflict_check` (1) failed on citation count.

## 2. Root cause

All 699 predictions open a `<think>` block; only 60 ever close it. **639 were truncated
mid-reasoning.** The base model never emitted an answer at all, so nothing about citation
ability was tested.

Two contributing defects:

- `infer.py:130` calls `tokenizer.apply_chat_template(...)` without `enable_thinking`, so Qwen3-8B
  defaults to **thinking mode on**.
- `DEFAULT_MAX_NEW_TOKENS = 256` (`evaluate.py:96`, `infer.py:25`) is consumed entirely by
  reasoning prose before any answer is produced.

The fine-tuned run is unaffected: it was LoRA-trained on non-thinking targets and scored
`citation_fidelity 0.20` pre-WP1, which is impossible if its outputs were truncated reasoning
(that scores exactly 0.00, as observed here).

## 3. The deeper problem the redo must address

The eval-set system prompt says only *"You answer only from the cited course material and always
cite video_id + hms."* It never states the actual output contract that scoring enforces:

- the literal `Citation: <video_id> <hms>` trailing line, and
- `rule_candidate`'s three labelled lines (`Rule candidate:` / `Setup / entry condition:` /
  `Invalidation / caveat:`), in order.

That contract exists **only in the fine-tuning targets**. So any baseline prompted with the stock
system prompt floors near zero no matter how it is decoded, and "fine-tune >> baseline" becomes
close to tautological: it measures *the model learned our formatting convention*, not *the model
learned to cite correctly*.

This matters because the pre-registered hypothesis for the fine-tuned run is that training taught
citation **format but not selection**. A floored baseline cannot test that hypothesis.

## 4. Decision

Replace the single baseline with **two**, both at `max_new_tokens=256`, thinking **off**, so each
differs from the fine-tuned run in exactly one controlled way:

1. **Naive baseline** — stock system prompt, thinking off. The honest floor: what an
   off-the-shelf model does when the contract is never stated. Failures here are genuine
   format-ignorance rather than truncation artifacts.
2. **Format-instructed baseline** — same model and budget, but the exact output contract spelled
   out in the system prompt. This is the headline zero point: `schema_violation` and
   `no_citation` largely drop out, so `citation_not_in_corpus` vs `weak_overlap` become directly
   comparable to the fine-tuned run's failure profile.

Together they decompose the fine-tune's gain into **formatting** vs **selection**, which is the
question the project actually cares about.

Thinking-on with a raised budget (~2048 tokens) was considered and **rejected**: the missing
knowledge is an arbitrary output convention that no amount of reasoning can derive, it costs 4-8x
the GPU time, and it confounds two variables so McNemar flips stop being attributable to the
fine-tune.

## 5. Companion fix: baseline run-id identity

`baseline_run_id()` (`evaluate.py:580`) hashes only base model + revision + eval-set digest +
scoring_version. Generation config and prompt variant are **not** in the payload, so the two
baselines above would collide into the same run dir and silently overwrite each other.

The identity payload must additionally include the generation config that affects predictions
(`max_new_tokens`, thinking mode, decode settings) and the prompt-variant identifier. Runs whose
predictions can differ must not share a run id.

## 6. Consequences

- ~2.6 GPU-hours per baseline; both are re-runnable and land in distinct run dirs.
- The fine-tuned re-eval of `adb3c96ab6020c23` is kept and pairs against both baselines. Its
  predictions were never persisted pre-WP1, which is an independent reason it must run regardless
  of baseline choice.
- `scoring_version` is unchanged: scoring rules are not being modified, only generation and
  prompting. Existing scored artifacts remain comparable under version "1".
- The invalid `baseline-211b3f1a05efed81` is retained as a record, not deleted; its hypothesis
  outcome is marked "invalid - generation defect, not a measurement".
