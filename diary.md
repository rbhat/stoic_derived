# Stoic Derived — Diary

A live log of building a multi-timeframe futures day trading system based on the Stoic method. This is a passive journal of work in progress; it is not a decision log or architectural document.

**Scope:** NQ and ES futures, signals-only (no execution), multi-timeframe price action using the Stoic Traders method as the rulebook.

## Format

New entries appear at the top, dated. Each entry contains:
- **Status line** — one-line summary of what changed
- **What changed** — brief description of the work
- **Why** — one-sentence reasoning
- **Metrics/constraints** — measured costs, blockers, entry points if relevant

Entries are terse but complete; a reader unfamiliar with the project should understand the work and its reasoning. Avoid narrative, architectural discussion, and internal trade-offs (those belong in memory or CLAUDE.md). Add entries only for major phase completions or status changes, not every commit or debug session.

---

## 2026-07-26

**Status: SLM retrain decided**

The visual harvest phase (WP-V §3.1) is complete. The extraction yielded 10,120 distinct visual states with full-resolution keyframes and passed all six hard audit checks. This material had never been used in training before—the transcripts don't contain on-screen text, and slide definitions are visual-only. A model cannot learn what it was never shown.

Decision: retrain the SLM using the newly extracted visual material. The training corpus will now include both transcripts and the 10,120 visual states extracted via VLM.

**Why retrain now:** The prior "do not retrain" verdict was measured against a corpus that lacked this visual signal entirely. That corpus is now outdated. The new material answers open questions in the rulebook (`unresolved_decisions` in `strategy/rulebook.yaml`) and will produce fixtures that a signal generator can be validated against.

**The pipeline spans two machines** (forced by hardware, not preference):
- **Mac (stage A):** VLM extraction of 10,120 visual states using `qwen3-vl-30b-a3b-instruct-mlx` at 4-bit precision. Model needs ~17 GB unified memory; the Windows RTX 5070 Ti has only 16 GB VRAM and cannot run the full model. Measured cost: 50–75 hours wall time (chart frames cost 2–3× more than slides due to token volume; includes 30% thermal duty cycle).
- **WSL (stage B):** QLoRA retrain on the rebuilt training corpus. Starts after stage A completes and is pushed.

**Extraction rules** (verbatim, not paraphrased):
- OCR text is exact. Unreadable lines marked `unreadable`, never guessed.
- Chart numbers are proposals checked against measured bars, never ground truth.
- Axis furniture (repeating price/time ticks) is stripped—rules live in titles, labels, and called-out prices. A measured 94% of chart-frame tokens were noise.
- Every record cites `video` and `t_start`. Uncited claims are dropped.
- Process is resumable per state; crashes or thermal throttling do not force restart.

**Entry point:** `scripts/extract.sh` (start/resume/status/stop). Runs detached with `caffeinate` holding the Mac awake for exactly as long as the job lives.

---

## Prior work

### 2026-07-26

**WP-V §3.1 — visual harvest (complete)**  
Extracted 10,120 distinct visual states from 16 Stoic Traders education videos with full-resolution keyframes. All six hard audit checks passed: bars reproduce the instructor's drawn HCOM/LCOM to the tick; counts re-derived match harvested counts; dHash alone underperformed (dropped in favor of multi-method ensemble). This material is the input to the VLM extraction pass now starting.

### 2026-07-25

**Edge measurement — first probe (NQ, measured)**  
Implemented and ran a full edge test on NQ price data using a subset of rules. Result: the proxy was too narrow to yield a conclusion, but the measurement infrastructure (run-dir artifacts, failure buckets, eval tooling, comparison dashboards) is production-ready and will be reused for full-signal validation. Code lives in `research/` on the main branch.

**Case study fixture track (seeded)**  
Extracted 25 in-scope NQ trading sessions from Stoic Traders Vol 1–7 PDFs (which have searchable text layers). Confirmed our bar reproduction matches the instructor's exact highs and lows. Page titles are trade days (open/close), not signal days; canonical five-day Red Day example is 2026-01-26..30. This is the ground truth for validating full signal chains.

**Red day definition (settled)**  
Formally defined: Red = close < open. The signal cascade is Day1–3 establish new highs (HCOM) → Day4 closes red → Day5 is the actionable signal day to trade. This pattern repeats and is the focus of fixture validation work.

**Training infrastructure (WP1–WP6, 2026-07-24 completed)**  
- **WP1–WP2:** Built run-dir artifact structure, failure buckets, and eval comparison tooling. Eval streams predictions to disk for resumable runs.
- **WP3–WP5:** Implemented deterministic dev/holdout split by video, ledger unsealing for label access during development, and calibration tooling for accuracy/coverage trade-off tuning.
- **WP6:** Added Tier-2 advisory judge and k-fold-by-video runner for cross-validation.
- **WP (CUDA):** Built reproducible Windows QLoRA training package for Qwen3-8B fine-tuning; validated in WSL with all config, venv, and dependency traps documented.

**Eval and model analysis (2026-07-25)**  
Recorded why the first baseline run was invalid (incorrect corpus), designed honest eval comparisons, and finalized generation settings (thinking-off, fixed random seeds, prompt variants). Current objective: use SLM as a specification-extraction tool, not a benchmark scorer.

### 2026-07-24

**System architecture (SP0–SP6, core signals path)**  
- **SP0:** Fail-closed strategy rulebook with 12 unresolved decisions awaiting visual signal input.
- **SP1:** Deterministic market data layer (historical + live Databento feed).
- **SP2:** Fail-closed signal engine generating multi-timeframe signals (Scalp/Day/Swing/Position types).
- **SP3:** Observational validation track (no execution gate; runs in parallel).
- **SP4:** Deterministic Google Drive-backed trade ledger (append-only to prevent data loss under concurrent writers).
- **SP5:** Secure static operations dashboard (user management, API key rotation, system health).
- **SP6 (pending):** Automated execution relay (after signals are validated).

**Environment and tooling (2026-07-24)**  
- Codified two-machine architecture: Mac (VLM inference, education mining) + Windows WSL (CUDA training).
- Built portable Python environment (3.14 in `.venv`, 3.12 CUDA in `.artifacts/training/venv`).
- Verified Windows WSL setup with complete CUDA training pipeline.
- Documented video restore and cross-machine artifact sync via Google Drive.

**Initial commit (2026-07-24)**  
Set up education pipeline, transcripts, and strategy source material. Roadmap: signals-only v1 (no execution), then add observational validation, then live trading.
