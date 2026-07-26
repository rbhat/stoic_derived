# Memory Index

This directory is the single source of truth for this project's agent memory, version-controlled so
it travels between machines. Write new memories here — not to `~/.claude/projects/<slug>/memory/`,
which has been retired for this project. See `CLAUDE.md` for the contract.

- [Signal fidelity, not edge revalidation](signal-fidelity-over-edge-revalidation.md) — **START HERE.** User directive: Stoic's method is a proven given; learn it from the education, build a signal generator, measure fidelity — never re-litigate the edge or conclude from small samples
- [Case-study fixture track](case-study-fixture-track.md) — **active work.** Vol 1-7 PDFs have a text layer (25 in-scope NQ sessions, all inside data coverage); our bars reproduce the instructor's HCOM/LCOM exactly; page-title dates are TRADE days, not signal days
- [Edge measurement: first probe](edge-measurement-first-probe.md) — the 2026-07-26 NQ probe: measured a thin proxy, conclusion retired, infrastructure worth reusing. Branch `research/edge-measurement-probe`
- [Eval-comparison WP progress](eval-comparison-wp-progress.md) — WP1-WP8 state, GPU chain COMPLETE, fine-tune verdict; its objective is now specification extraction, not benchmark scores
- [SLM model artifacts](slm-model-artifacts.md) — where the fine-tuned Qwen3-8B lives, which file to move to the Mac, and the standing decision **not** to retrain it
- [Audit every derived number](audit-derived-numbers.md) — user directive: adversarially audit any number that comes out of a test before reporting it (ADR-0021)
- [Check, don't relaunch detached jobs](check-dont-relaunch-detached-jobs.md) — user directive: check before launching GPU work; nothing is running as of 2026-07-26
- [Win CUDA training package](win-cuda-training-package.md) — DONE; kept for the venv/uv/wslconfig traps and two open audit warts
- [Artifact locality](artifact-locality.md) — user directive: all run artifacts under <repo>/.artifacts/, never ~ or other drives
- [Always ruff --fix](ruff-always-fix.md) — user directive: never bare `ruff check`; use `uvx ruff check --fix`
- [Opus expanded role](opus-expanded-role.md) — user directive: Opus subagents orchestrate+verify+audit whole phases, not just final audits
