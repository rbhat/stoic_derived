# Evaluating models against subjective targets — engineering notes

Personal education notes (Rajeev), 2026-07-24. General ML engineering
lessons distilled from the stoic_derived SLM evaluation work; not a project
spec. The project-binding version is
`docs/superpowers/specs/2026-07-24-eval-comparison-design.md`.

## 1. You don't need an objective metric — you need a stably biased one

When the true target is subjective ("is this claim supported by the cited
source?"), any automatic metric is a proxy with errors. The mistake is
treating the proxy as truth; the fix is treating it as an instrument with a
known error bar:

- Keep the proxy **deterministic and versioned** (same inputs → same score,
  forever, per `scoring_version`). A biased-but-stable metric still orders
  *runs* correctly, because the bias cancels in the delta.
- **Calibrate it against humans**: periodically sample ~50 scored examples,
  human-label them, and record the proxy's precision/recall vs the human.
  "Subjective" becomes "measured 12% false-fail rate" — a risk you can
  accept in writing instead of an anxiety.
- If you change the metric, you start a new lineage. Never compare scores
  across metric versions; make the tooling refuse.
- Track **failure-mode buckets** (no citation / hallucinated citation / weak
  support / malformed output), not just a headline rate. Buckets tell you
  *what* to fix; headlines only tell you *whether* to panic.

## 2. Subjective concepts become code via fixtures, not via model judgment

"Price built a base and broke out" has no datafeed column. The wrong fix is
asking a model to judge it at runtime (unauditable, nondeterministic). The
right pipeline:

1. The model only **proposes semantics with citations** — "educator's 'base'
   ≈ 12+ bars, range < 0.5×ATR, at prior day high (video X, 00:14:32)".
2. A human converts the proposal into a **parameterized pure function**:
   `is_base(bars, n_min, atr_frac, band_ticks) -> bool`.
3. The cited video moments become **golden test fixtures**: fetch the
   matching historical bars, assert the predicate fires where the educator
   said "base" and stays quiet on nearby counterexamples. The subjective
   term is now a versioned function plus an auditable fixture set.
4. Ambiguity the sources can't resolve goes to a **decision queue**, not
   into fudge-factor parameters.

Accepted risk: the predicate disagrees with the expert's eye on edge cases.
That's fine — backtests price the disagreement, and a slightly-wrong rule
you can measure beats an unmeasurable "feel" every time.

## 3. Blind models, non-blind process: adaptive overfitting

Every training run can be perfectly blind to the eval set and you will still
overfit it — because *you* read the score, keep the change that raised it,
and discard the one that didn't. Selection pressure leaks information about
the fixed eval sample through your decisions (the Kaggle public-leaderboard
effect). Against ±3% sampling noise (~700 examples), twenty rounds of
pick-the-winner can bank 5–10% of "improvement" that generalizes to nothing.

Countermeasures, in increasing order of discipline:

- **Paired comparison, not aggregate deltas.** On a frozen eval set with
  deterministic decoding, key every example by a stable id and count flips:
  "fixed 41, broke 6" (McNemar) is signal where "+3% overall" is noise.
- **Pre-registration.** Write the hypothesis into the run record *before*
  launching ("1 epoch cuts hallucinated citations"). Unpredicted gains are
  leads to verify, not results to bank.
- **Dev-eval vs sealed holdout.** Iterate freely against dev; score the
  sealed set only at release candidates, and log every unsealing. The
  holdout's statistical power is a budget you spend, not a free resource.
- **Refresh.** Newly collected data is the only truly unseen future —
  quarantine it into the holdout pool by default, and retire over-exposed
  eval sets by version.

## 4. Split geometry: leakage beats sample size

Choose the split unit by asking "what shares hidden state?" Adjacent
keyframes of one video share narration, context, and phrasing — a
record-level split lets the model score "generalization" by memorizing the
video. So the video is the atomic unit, even though that leaves only 16
units. Corollaries:

- Coarse honest splits beat fine leaky ones. A leaky split doesn't inflate
  your score a little — it changes what the number *means*.
- With few units, use **k-fold over units** when a decision looks
  split-sensitive; fold variance tells you how much your one split is lying
  to you. (Cheap here: 45 min/run × 5 folds ≈ 4 GPU-hours.)
- "Non-contiguous" only matters where contiguity encodes correlation
  (time-series records). Between whole videos, random+stratified assignment
  is already the right blindness; finer granularity would *reduce* honesty.

## 5. Ops lesson of the day: monitors need monitors

Two failure patterns from this run worth internalizing:

- `pgrep -f <pattern>` **matches the shell that runs it** if the pattern
  appears in the command line — write it as `pgrep -f "[s]tring"` so the
  bracket breaks self-matching. Our watcher spun 2.5 h on its own
  reflection.
- Wake-on-exit monitoring must be paired with **stall detection** (progress
  file / log mtime older than N minutes while the process is "alive", or a
  traceback signature in the log). "Process exists" is not "work is
  happening", and "no news" must never mean "wait forever".
