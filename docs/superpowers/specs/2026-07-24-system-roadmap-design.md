# Stoic Derived — System Roadmap (Decomposition)

*Design doc · 2026-07-24 · derived from VISION.md v0.3*

This is the **overall plan**: it carves the VISION into sub-projects, fixes the
build order, and sets the cross-machine strategy. It is a roadmap, not an
implementation plan. **Each sub-project gets its own brainstorm → spec → plan →
implementation cycle.** SP0 (the rulebook) is next.

VISION.md is the source of truth and is agent-immutable. Where this doc and
VISION disagree, VISION wins.

---

## 1. Guardrails (from VISION, non-negotiable)

- **Signals only.** The system generates and tracks signals; it does **not**
  place orders. No broker/execution API in v1.
- **No LLM in the live signal path.** Live signals are deterministic rules:
  same inputs → same signal, every time, fully auditable.
- **The SLM is offline research only.** It helps mine the education and codify
  the rulebook. It never sits in the live path.
- **Do not change the strategy.** The edge is Stoic Traders' strategy; the code
  executes it consistently. No "optimizing" the strategy or the education.
- **Scope v1: NQ and ES only.** GC/CL/BTC/FX come later.

---

## 2. Current state (what already exists)

- **`edu/` education pipeline — DONE.** Resumable video → transcript → keyframe
  → `dataset.jsonl` (2233 rows) pipeline over 16 videos. This is the offline
  research substrate.
- **`edu/concepts`, `edu/resources`** — Stoic source material: 10 Commandments,
  concept glossary, "A Setups" PDFs (Vol 1–8), war map.
- **`data/historical/`** — NQ and ES Databento DBN trades (gitignored; local /
  Drive).
- **Missing:** everything downstream — rulebook, data layer, signal engine,
  backtest, ledger, dashboard, infra.

---

## 3. Subsystem decomposition

| # | Subsystem | Purpose | Depends on |
|---|-----------|---------|------------|
| **SP0** | **Strategy Spec / Rulebook** | The one distilled, plain-language source-of-truth doc encoding the rules: B&R, SFP, SBS, PDH/PDL/PDC, HCOM/LCOM, Fib geometry, 20+200 SMA, HTF/trapped-trader context, and the deterministic **confluence score**. Rulebook state is *hybrid* — named setups known; exact entry/stop/target/confluence must be **mined from the videos (SLM-assisted) and human-validated**. | edu pipeline (done); SLM (research aid) |
| **SP1** | **Market Data Layer** | Databento DBN historical loader (NQ/ES) + live feed adapter; aggregation into the 6 timeframes (1m/5m/15m/60m/D/W). One bar interface consumed by engine + backtest. | — |
| **SP2** | **Signal Engine** | Deterministic rules over bars → full **signal records** (schema below), across the 4 Types and their HTF→LTF→exec maps. **No LLM.** The hard core; everything else consumes it. | SP0, SP1 |
| **SP3** | **Backtest / Walk-forward / Paper** | Run SP2 over historical NQ/ES → expectancy, win rate, avg R, max drawdown **per timeframe and per instrument**. Validation track — measures whether the edge holds; not a blocker on the live-signals milestone. | SP1, SP2 |
| **SP4** | **Trade Ledger + Lifecycle** | One ledger per Type (Scalp/Day/Swing/Position). Append-only / per-source, reconciled — **never one shared live-edited file**. Drive as source of truth. Tracks each signal to close (TP/SL). **1:58pm Pacific flatten watchdog** with heartbeat that fires even if a process died. | SP2 |
| **SP5** | **Dashboard** | Web UI (simple, UX-led). Ledger (open vs closed, P/L, time held, charts), operational status, system management (key rotation, connection tests, Drive sync), user management, **Google auth (invite-only whitelist)**. Primary admin `rajeevmbhat@gmail.com` is immutable. | SP4 |
| **SP6** | **Deployment / Infra** | Cross-machine portability, secrets & API-key rotation, GCP deployment, GitHub + Drive sync. Cross-cutting. | — |

### Signal-record schema (SP2 output)

Every signal is one record with **at least**: `instrument`, `type`
(Scalp/Day/Swing/Position), `direction` (long/short), `entry`, `stop`,
`target`, `r_multiple`, `setup_type`, `confidence` (deterministic confluence
score — *not* a model output), `signal_ts` (UTC), `source` (which system
produced it). If any are unfillable, it is **not a signal yet**.

### Timeframe maps (from VISION)

Format — *Type: HTF → LTF → Execute TF; manage at TF*:

- **Scalp:** 15m → 5m → 1m; manage 5m
- **Day:** 60m → 5m → 1m; manage 5m
- **Swing:** Daily → 60m → 15m; manage 60m
- **Position:** Weekly → Daily → 60m; manage Daily

### Time handling (from VISION)

Everything viewed in Pacific, **stored in UTC**, converted at the edges only.
The flatten cutoff uses current Pacific wall-clock time so DST is automatic —
no fixed UTC offset. Only Position-type trades may stay open past NY hours;
all other Types flatten at **1:58pm Pacific**.

---

## 4. Build order & phasing

**v1 milestone (chosen):** *Live signals + dashboard* — watch the engine
produce signals in real time. v1 is **signals-only/observational** (no
execution), so there is no live-capital gate. The backtest (SP3) runs as a
**parallel validation track** off the same engine — it measures whether the
edge holds, but does **not** block the live-signals milestone.

Key insight: **SP2 (signal engine) is the shared core.** Once it exists, both
the backtest (SP3) and the live dashboard (SP4+SP5) are thin consumers — so
validation and the live-view milestone land almost together.

```
Phase A  (critical path, sequential)
  SP0 Rulebook ──► SP1 Data Layer ──► SP2 Signal Engine

Phase B  (two parallel tracks off SP2)
  Track B1 (milestone):  live feed → SP2 → thin SP4 ledger + flatten watchdog → SP5 dashboard + Google auth
  Track B2 (validation): SP2 over historical NQ/ES → SP3 backtest / walk-forward

Phase C  (harden & operationalize)
  SP4-full  Drive-backed, concurrency-safe, no-loss ledger
  SP6       GCP deploy, key rotation, secrets, cross-machine portability
```

---

## 5. Environment strategy (cross-cutting)

Core idea: **Mac mines & infers, Windows trains, both develop deterministic
code, GCP runs production.** Every task in every sub-project plan carries an
environment tag.

| Tag | Machine | Runs here | Why |
|-----|---------|-----------|-----|
| **`mac-metal`** | Mac M4 Pro, 48GB unified | VLM/LLM **inference**: SP0 rulebook mining, transcription, any big-model call | Unified memory fits 30B+ vision models; MLX/Metal. Edu pipeline already here. |
| **`win-cuda`** | RTX 5070 Ti 16GB, WSL | Model **training/fine-tuning**: research SLM (QLoRA on `dataset.jsonl`), CUDA numeric work | CUDA ecosystem; 16GB VRAM fits small-model training. |
| **`portable`** | Either box (dev) | SP1 data, SP2 engine, SP3 backtest, SP4 ledger, SP5 dashboard | Pure deterministic Python; dev wherever you sit. |
| **`gcp`** | Free GCP server | Production 24/7: live feed, engine, flatten watchdog, dashboard | Always-on; real home of ledger/dashboard. |

**Parallelism:** the two boxes run concurrently on independent work — e.g. Mac
mines videos for SP0 while Windows fine-tunes the SLM or grinds an SP3 sweep.
Each plan calls out its parallel opportunities.

**Portability contract** (so `portable` code runs on Mac / WSL / GCP alike):
- `pathlib` only — no OS-specific path strings.
- All config via **environment variables** (no hardcoded hosts/paths/devices).
- Device selection (`mac-metal` / `win-cuda` / CPU) behind **one helper**.
- No hardware assumptions in `portable` code.
- **Sync:** GitHub for code; Google Drive for large artifacts (videos, data,
  trained models, ledger).

---

## 6. Per-sub-project cycle

Each SP follows: **brainstorm → spec (`docs/superpowers/specs/…`) → plan → implement → test → audit.**
Top-level agent thinks/designs/plans; Sonnet subagents execute; an Opus subagent
audits before reporting. Tests and audit against VISION guardrails (§1) are
mandatory for each SP. Tasks are environment-tagged (§5).

**Next step:** brainstorm **SP0 — Strategy Spec / Rulebook.**

---

## 7. Open questions (resolve at each SP's brainstorm, not now)

- **SP0:** which local model(s) for mining; how rules are represented (structured
  YAML/JSON vs prose+examples) so SP2 can consume them deterministically.
- **SP1:** bar-build source (trades → bars) and exact session/RTH handling;
  live Databento schema.
- **SP2:** how confluence score is computed from confluences; multi-TF alignment
  mechanics.
- **SP3:** walk-forward window sizing; paper-trading definition of "done."
- **SP4:** append-only vs file-per-source reconciliation; Drive sync mechanism;
  watchdog implementation (systemd/cron/GCP scheduler).
- **SP5:** dashboard stack; GCP web-client OAuth setup.
- **SP6:** GCP service shape (VM vs Cloud Run) under the free tier.
