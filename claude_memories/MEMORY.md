# Memory Index

**Before this index, read `docs/STATE.md` (what is running) and `docs/CONSTRAINTS.md` (what binds
the next step, indexed by when it bites). This file is the third stop, not the first.**


This directory is the single source of truth for this project's agent memory, version-controlled so
it travels between machines. Write new memories here — not to `~/.claude/projects/<slug>/memory/`,
which has been retired for this project. See `CLAUDE.md` for the contract.

- [Signal fidelity, not edge revalidation](signal-fidelity-over-edge-revalidation.md) — **START HERE.** User directive: Stoic's method is a proven given; learn it from the education, build a signal generator, measure fidelity — never re-litigate the edge or conclude from small samples
- [Case-study fixture track](case-study-fixture-track.md) — **active work.** Vol 1-7 PDFs have a text layer (25 in-scope NQ sessions, all inside data coverage); our bars reproduce the instructor's HCOM/LCOM exactly; page-title dates are TRADE days, not signal days
- [Red day definition](red-day-definition.md) — **strategy decision.** Red = `close < open`; Day1-3 new HCOM → Day4 red = signal → trade Day 5; canonical fixture is 2026-01-26..30. Do not re-derive from data
- [WP-V §3.1 visual harvest status](visual-harvest-31-status.md) — **active work.** 10,120 visual states harvested; all six HARD audit checks green and every count re-derived; dHash alone under-splits, so the split rule needs more than a 64-bit hash
- [WP-V §3.2 extraction — ops](wpv-32-extraction-ops.md) — **how to run it.** `scripts/extract.sh`, the durability contract, pid-liveness stage ownership, the two-tier thermal cycle, the token/context trap and the four constants that move together, the rate bracket, and the 2–3 h sanity check. Live status is in `docs/STATE.md`
- [WP-V §3.2 extraction — findings](wpv-32-extraction-findings.md) — **what the output says.** STOP AUDITING `drawn_levels` (the disagreements are the instructor live-editing, not the model); `ocr_text` is verbatim and healthy; level values are advisory and labels are the signal; what Stage B may train on
- [WP-V §3.3 OCR gate](wpv-33-ocr-gate.md) — **run it with `edu/pipeline/ocr_gate.py`.** First pass: rule text is verbatim everywhere; the failure modes are dropped diagram labels, misread printed prices, and `HCOW` returned as `HCOM` on 12/32 frames. Open the JPEG before calling anything an error
- [Slide text is not in the transcripts](slide-text-not-in-transcripts.md) — rule definitions live on screen, never spoken; existing keyframe labels are unverified and one is a hallucinated caption. Check keyframes before concluding the material is silent
- [Bars match the education, not TradingView](bars-match-education-not-tradingview.md) — `NQ.c.0` reproduces the instructor's drawn levels to the tick; a stock TV chart ran ~+506.5. Never read a bars file mid-build
- [Edge measurement: first probe](edge-measurement-first-probe.md) — the 2026-07-26 NQ probe: measured a thin proxy, conclusion retired, infrastructure worth reusing. Code is on `main` under `research/`
- [Eval-comparison WP progress](eval-comparison-wp-progress.md) — WP1-WP8 state, GPU chain COMPLETE, fine-tune verdict; its objective is now specification extraction, not benchmark scores
- [SLM model artifacts](slm-model-artifacts.md) — where the fine-tuned Qwen3-8B lives (on the Mac it is under `artifacts/`, no dot, no runner installed); **retrain DECIDED 2026-07-26** — Mac does the VLM extraction, WSL does the training, the split is forced by the 16 GB card
- [Audit every derived number](audit-derived-numbers.md) — user directive: adversarially audit any number that comes out of a test before reporting it (ADR-0021)
- [Check, don't relaunch detached jobs](check-dont-relaunch-detached-jobs.md) — user directive: check before launching GPU work — never start a second copy of a detached job
- [Win CUDA training package](win-cuda-training-package.md) — DONE; kept for the venv/uv/wslconfig traps and two open audit warts
- [Artifact locality](artifact-locality.md) — user directive: all run artifacts under <repo>/.artifacts/, never ~ or other drives
- [Always ruff --fix](ruff-always-fix.md) — user directive: never bare `ruff check`; use `uvx ruff check --fix`
- [Opus expanded role](opus-expanded-role.md) — user directive: Opus subagents orchestrate+verify+audit whole phases, not just final audits
