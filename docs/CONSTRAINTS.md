# Constraints register — what binds the next step

**Read this before starting work. It is an index of triggers, not a summary of rules.**

Each row names an obligation and points at the document that defines it. **The row is not the rule.**
Open the source before acting on anything here — every source in this table is short (the ADRs
average 39 lines; ADR-0004 is 27). Compressing them is how we get things wrong: a paraphrase of
ADR-0004 in `CLAUDE.md` conflated it with the no-grid-search directive and cost a full work cycle on
2026-07-27.

Organised by **when it bites**, because the failures here have not been ignorance of a rule — they
have been a rule that existed, was written down, and was not surfaced at the moment it applied.

---

## When you author a rule, or derive any parameter

| obligation | source |
|---|---|
| Primary Stoic media/PDF is the normative evidence. Model-derived artifacts (VLM, SLM, transcripts, dataset labels) may aid **discovery** but cannot be the sole normative source; the validator rejects model-only evidence and requires a primary record with digests and locators. | `docs/architecture/adr/0004-strategy-source-authority.md` |
| A rule reaches `validated` only when every evidence record it cites carries a **signed** human review of the cited range. An agent can never write one — that is the point. The first ten were signed 2026-07-27 (decision 12 closed, ADR-0022 *Accepted*); **any new cited range needs its own review.** `stoic-rulebook review-queue` shows what is outstanding. | `docs/architecture/adr/0022-primary-evidence-review-gate.md` |
| Editing a `claim`, `locator`, `observed` or asset **invalidates the review** and drops the record back to unreviewed. Rewrite first, then review — never the reverse. | same |
| `review-queue` and `validate` check review *structure*, not signatures; only `publish` verifies against the pinned key. A rulebook can report "every cited range carries a supported human review" while none of them verify. | same, § Compliance |
| No parameter grid searches for "the best cell". Where the material genuinely underdetermines a number, **the human decides** and it is recorded as a strategy decision. **This is a standing directive, NOT ADR-0004** — do not cite the ADR for it. | `CLAUDE.md`, `claude_memories/signal-fidelity-over-edge-revalidation.md` |

## When you report any derived number

| obligation | source |
|---|---|
| Every derived number is presumed invalid until adversarially audited. Audit before reporting, not after. | `docs/architecture/adr/0021-adversarial-audit-of-derived-numbers.md`, `claude_memories/audit-derived-numbers.md` |
| Never conclude from small n. Report **counts, not verdicts**, and never project direction. | `claude_memories/signal-fidelity-over-edge-revalidation.md` |
| Never frame work as "does the strategy have an edge". The method is a premise, not a hypothesis. Divergence from `edu/derived/` is a **specification bug**. | same |
| Backtests are observational and **do not gate**. | `docs/architecture/adr/0011-observational-non-gating-backtests.md` |

## When you look at VLM output (`ocr_text`, `chart.*`)

| obligation | source |
|---|---|
| **Do not build another check against `chart.drawn_levels`.** Two have been built and retired; the disagreements are the instructor editing a live chart, not model error. | `claude_memories/wpv-32-extraction-findings.md` § "STOP AUDITING `drawn_levels`" |
| **Open the JPEG before claiming anything is wrong**, and crop at full resolution before asserting a single character or digit is misread. `BLL`, `PHCOM` and `HCOW` all looked like errors and were verbatim correct. | `claude_memories/wpv-33-ocr-gate.md` |
| `prompt_sha` defines what `ocr_text` means. Two shas in one corpus is a mixed corpus — never blend them, re-extract instead. | `claude_memories/wpv-32-extraction-ops.md` |

## When you rebuild `edu/derived/dataset.jsonl` (Stage B)

| obligation | source |
|---|---|
| Read `chart.drawn_levels[].label` and `chart.annotations`, **not `ocr_text` alone**. Capped records (8 % and rising) lose most of `ocr_text` but keep their method-term labels in the chart block. | `claude_memories/wpv-33-ocr-gate.md` § capped frames |
| **Do not filter on `frame_class`.** It flips on slides the instructor drew over, so rule-bearing slides land in the chart bucket. Filter on content. | same |
| Do not train on any OCR'd price. Level **labels** are the signal; values are derived in Python from our own bars. | `claude_memories/wpv-32-extraction-findings.md` § Stage B |
| When picking one frame per repeated slide, prefer the one with the most lines — diagram labels (`SFP`, `B&R`, the `DAY` row) drop off some frames while rule text never does. | `claude_memories/wpv-33-ocr-gate.md` |

## When you join a frame to market data

| obligation | source |
|---|---|
| Our bars reproduce the instructor's drawn levels to the tick. A stock TradingView chart does not. Never read a bars file mid-build. | `claude_memories/bars-match-education-not-tradingview.md` |
| A frame's OHLC header joins to a bar on **3-of-4 fields (H/L/C)**, not 4-of-4 — OCR misreads one field about as often as the gate measured. | `docs/notes/2026-07-27-spec-coverage-probe.md` §0 |
| `.artifacts/research/bars/` holds **NQ only** (`1m`, `5m`, `15m`, `60m`, `D`). Gold, AUD/USD, RTY, GBP/JPY, CL and BTC frames have no bars to join to. | same |

## When you launch or touch a long-running job

| obligation | source |
|---|---|
| Check before launching. Never start a second copy of a detached job. | `claude_memories/check-dont-relaunch-detached-jobs.md` |
| The user kills the extraction when the laptop runs hot. That is expected and safe; re-running resumes it. No LaunchAgent — nothing auto-starts on this machine. | `claude_memories/wpv-32-extraction-ops.md` |

## Environment (bites constantly)

| obligation | source |
|---|---|
| `.venv` (3.14) for all repo work. The training venv is separate and `uv run` **must** have cwd `training/win_cuda` or it destroys it. | `CLAUDE.md` |
| Lint with `uvx ruff check --fix`, never bare `ruff check`. Line length 100. | `claude_memories/ruff-always-fix.md` |
| All run artifacts under `<repo>/.artifacts/`, never `~` or another drive. | `claude_memories/artifact-locality.md` |
| Deterministic signal code must never call an LLM/SLM. | `CLAUDE.md`, `VISION.md` |
