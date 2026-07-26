---
name: eval-comparison-wp-progress
description: WP1-WP8 execution state for the eval-comparison work (resume point after context reset)
metadata:
  node_type: memory
  type: project
  originSessionId: 018c805a-3b25-4f21-8ef3-54ce567a23ba
  modified: 2026-07-26T03:45:43.883Z
---

Executing `docs/superpowers/specs/2026-07-24-eval-comparison-design.md` (started 2026-07-25).
Related: [[win-cuda-training-package]], [[check-dont-relaunch-detached-jobs]], [[opus-expanded-role]].

## READ THESE FIRST — the detail now lives in the repo, not here

- `docs/notes/2026-07-25-slm-eval-learnings-and-gap-to-goal.md` — **start here.** All results,
  the failure analysis, methodology learnings, distance to goal, ordered next actions.
- `docs/architecture/adr/0021-adversarial-audit-of-derived-numbers.md` — the standing rule: every
  derived number is presumed invalid until adversarially audited. Ten checks, each from a real
  incident here. Applies to reporting, not to gating.
- `docs/superpowers/specs/2026-07-24-eval-comparison-design.md` — protocol; now carries WP7 (audit
  command + bucket split) and WP8 (decoding probe, user-approved 2026-07-25).

## Live GPU chain (chain pid 2036, `chain_all_v3.sh`, code rev `0e3971b`)

| # | run id | status |
|---|---|---|
| 1 | `adb3c96ab6020c23` (fine-tuned) | DONE 21:36 UTC, fidelity .209 |
| 2 | `baseline-d7ffd44e388deb0d` (naive/stock) | DONE 23:39 UTC, fidelity .000 |
| 3 | `baseline-5175d80ffdbad8c7` (format_instructed) | DONE 00:38 UTC 2026-07-26, rc=0 |

**CHAIN COMPLETE — GPU is free.** All three health-clean (0 truncated, 0 empty), same corpus +
eval digests, `scoring_version` 1. Independent re-derivation from `predictions.jsonl` reproduces
every `scores.json` bucket exactly for all three.

## Verdict: what the fine-tune bought (audited 2026-07-26, ADR-0021 §F)

- **Format — nothing.** Prompt buys it outright: `schema_violation` 0/699 in *both* the
  fine-tuned and the instructed-base run; trailing citation 349/349 on `rule_candidate` in both.
- **Grounding — the one real win.** `cited_qa` (identifier must come from memory, not the
  prompt): fine-tuned 240/240 emitted citations name a real corpus video, 0 invented; instructed
  base 0/297, i.e. 297/297 invented (`COURSE_MATERIAL` ×54, `C1`, `101`). Paired +0.688,
  fixed=240 broke=0, McNemar p=1.1e-72. On `rule_candidate` (a copy) the delta is trivial:
  349/349 vs 346/349, p=0.25.
- **Selection — nothing. Both models 0/349** on gold video for `cited_qa`.
- **Cost:** `rule_candidate` instructed 220/349 (.630) vs fine-tuned 138/349 (.395), delta −.235,
  fixed=38 broke=120 **unchanged_pass=100** → a real capability comparison, not a floor artifact.
  Mechanism: citations correct in both, so it is body text only — the scorer rewards lexical echo
  of the source narration and the fine-tune writes shorter/more abstractive bodies (median overlap
  .273 vs .333; 217 vs 309 chars; prompt-echo .190 vs .328).

## Two corrections to the learnings note (both make things worse, not better)

1. `cited_qa = 0.023` is **8 false positives, not 8 correct answers** — 0 of the 8 passing rows
   cite the gold video. True `cited_qa` accuracy is **0/349** for every run.
2. `rule_candidate = 0.395` is a **threshold artifact**. All 349 citations are correct by
   construction, so the metric varies only on body overlap, whose median (.273) sits just under
   the .30 cut. Pass rate moves .84 → .15 as the threshold moves .20 → .40.

## The one thing to carry in your head

`citation_fidelity = 0.209` is a **pooled average of two different skills** and must not be used.
`rule_candidate` (.395) hands the model the video_id+hms in the prompt — citing is a *copy*, and
349/349 citations resolve to real exact corpus keys. `cited_qa` (.023) is a bare question with no
corpus — *closed-book retrieval* over 2233 segments, which the system has no mechanism for; cited
video == gold video in **0 of 224**. The blocker is architectural (retrieval), not more training.

## Gotchas

- `uv run` MUST have cwd = `training/win_cuda` (root pyproject is 3.14 and destroys the 3.12 CUDA
  venv), and MUST NOT run while a GPU job is live (it resyncs the venv). Use
  `.artifacts/training/venv/bin/python3 -m stoic_training.<cmd>` directly instead — that is how
  `compare` was run safely mid-chain.
- `ruff` is not a declared dev dep; use `uvx ruff check --fix` ([[ruff-always-fix]]).
- `pgrep -f "stoic_training"` matches your own shell wrapper — match `venv/bin/python3 -m stoic_training`.
- Bash tool cwd persists across calls; an earlier `cd training/win_cuda` silently broke later
  `.artifacts/...` relative paths. Use absolute paths.

## PRIORITY, corrected 2026-07-26 — read [[signal-fidelity-over-edge-revalidation]] first

An earlier revision of this memory said a price-data probe showed "no edge" and that **none** of
the SLM items were on the critical path. **Both claims are retired.** The probe measured a thin
proxy with invented parameters, not the taught method ([[edge-measurement-first-probe]]), and this
project does not test whether Stoic's method works — that is a premise, not a hypothesis.

The SLM side is **back on the critical path with a changed objective.** The bottleneck is
*specification*: mining it out of the education is exactly what this path is for. Its target is no
longer a citation-fidelity score. It is (a) resolving the 12 `unresolved_decisions` in
`strategy/rulebook.yaml` from the material with evidence citations, and (b) turning the labeled
material in `edu/derived/` (`cs_vol1..7`, `live_3_5r_on_nq`, `live_4_14r_on_nq`, `live_4_2r_on_nq`,
`live_4_3r_on_cl`) into fixtures a signal generator can be validated against.

Judge the tooling below by whether it serves those two, not by benchmark scores.

## Decision 2026-07-25: do not retrain or rebuild — see [[slm-model-artifacts]]

The fine-tune's one win is *closed-book* grounding; both new objectives are *open-book* (source
goes in the prompt), which is the regime where it is neutral-to-worse. And the new objective's
training signal — labelled fixtures — does not exist yet. Build those first
([[case-study-fixture-track]]). The items below are therefore **not** queued work; judge each by
whether it serves specification extraction.

## Remaining (SLM side)

1. Run 3 compare + audit (above).
2. WP5 human calibration, 50 examples — **cheapest high-value item**; every rate currently has an
   unmeasured error bar. `calibrate sample --run-dir <run> --size 50` → hand-label → `calibrate ingest`.
3. WP8 decoding probe (~15 GPU min, approved, spec'd in the design doc §WP8).
4. WP7 audit command + split `citation_not_in_corpus` under `scoring_version` "2".
5. WP6 Tier-2 judge on the 224 misresolved citations ("wrong pointer, right content?").
6. Design discussion: retrieval path for `cited_qa`, or retire the task as constructed. Note the
   0/349 closed-book retrieval result is about *this eval task*, not about the extraction work
   above — extraction is open-book over a corpus you control.

The 2026-07-25 docs (learnings note, ADR-0021, eval-comparison design) are **committed** in
`a977f53`; verified 2026-07-26.
