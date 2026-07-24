# SP0 - Strategy Rulebook Design

*Design status: accepted for implementation; rule content remains candidate*

## 1. Objective

SP0 turns the Stoic Traders education corpus into one human-readable,
machine-validatable strategy rulebook without inventing missing strategy
details. It creates the publication boundary between offline research and the
deterministic live signal engine.

SP0 succeeds when:

1. a reviewer can trace every strategy claim to local source evidence;
2. candidate, ambiguous, and unknown rules are clearly separated from
   human-validated executable rules;
3. an unapproved or incomplete rulebook cannot be loaded by SP2 as a live
   strategy;
4. the four timeframe maps and NQ/ES-only v1 scope exactly match `VISION.md`;
5. model output, raw transcripts, and backtest results cannot alter live
   decisions.

## 2. Guardrails

- Signals only. No order placement, broker API, or automated execution.
- No LLM, SLM, VLM, prompt, or network call in the live decision path.
- Do not optimize, infer, or fill gaps in the Stoic strategy.
- NQ and ES are the only v1 runtime instruments.
- Backtesting and walk-forward validation are parallel measurements. They do
  not publish, tune, or gate the live rulebook.
- `VISION.md` is immutable to agents.

## 3. Domain boundary

Strategy Knowledge is the core subdomain. It is one module in the modular
monolith, not a service or database.

- `edu/` owns raw education and derived research material.
- SP0 owns codified strategy semantics, provenance, review, and publication.
- SP1 owns sessions, bars, and market-data normalization.
- SP2 owns deterministic evaluation and signal records.
- SP3 owns empirical measurement.
- SP4 owns signal lifecycle and flattening.

SP0 never parses live bars. SP2 never reads `edu/`, draft YAML, prompts, model
outputs, or the training dataset.

## 4. Source authority and evidence

Primary evidence is Stoic Traders media or a Stoic Traders PDF. Transcripts are
locators into that media and must be human-checked before a rule becomes
`validated`. Keyframe labels, `moments.json`, `dataset.jsonl`, captions, and SLM
output are discovery aids; they cannot be the only normative evidence.

Each evidence record has:

- a stable ID;
- local asset and transcript paths;
- source kind;
- a video time range or PDF page;
- a plain-language claim;
- a SHA-256 digest of each cited local asset.

Evidence from instruments outside NQ/ES may explain a general strategy concept,
but runtime applicability remains NQ/ES only.

## 5. Artifacts and authority

### 5.1 Authoring source

`strategy/rulebook.yaml` is the sole authoring authority. It is strict,
human-readable YAML containing scope, timeframe maps, evidence, qualitative
rules, a source-backed glossary, unresolved decisions, and approvals.

The loader rejects duplicate mapping keys and ambiguous YAML scalar forms.

### 5.2 Review projection

`strategy/RULEBOOK.md` is generated from the YAML. It is a review dossier, not a
second source of truth. Manual edits are overwritten.

### 5.3 Published release

`strategy/releases/<rulebook-version>.json` is canonical JSON generated only by
the publisher. SP2 may load only this artifact.

A release contains:

- schema and rulebook versions;
- source YAML SHA-256;
- normalized strategy rules;
- source snapshot digests;
- human approval bound to the source digest with an Ed25519 signature;
- compiler version.

Canonical JSON uses sorted keys, UTF-8, and fixed separators so repeated builds
produce byte-identical output and hashes.

No release is produced while a required rule is unresolved or unapproved. The
approver public key is pinned outside the rulebook and release. Private approval
keys and secrets are never stored in the repository.

## 6. Rule lifecycle

Rule statuses are deliberately narrow:

- `candidate`: source-backed, but one or more deterministic choices or
  parameters are unresolved;
- `unknown`: the current corpus does not support the required detail;
- `validated`: exact predicate, parameters, units, policy selection, evidence,
  tests, and digest-bound human approval are present.

Rulebook lifecycle:

1. offline research adds or refines candidate evidence;
2. validation checks structure, provenance, and Vision guardrails;
3. a generated dossier presents exact questions and source evidence;
4. a human validates specific executable rules and signs the full candidate
   digest with the separately held approval key;
5. publication compiles the approved digest to canonical JSON;
6. SP2 pins the rulebook version and release SHA on every decision record.

Any semantic YAML change changes the digest and invalidates the approval.
Content addressing proves freshness; the detached signature and externally
pinned public key prove who approved it.

## 7. Strategy model

### 7.1 Fixed v1 scope

| Type | HTF | Setup | Execute | Manage |
|---|---|---|---|---|
| Scalp | 15m | 5m | 1m | 5m |
| Day | 60m | 5m | 1m | 5m |
| Swing | 1d | 60m | 15m | 60m |
| Position | 1w | 1d | 60m | 1d |

Runtime instruments are exactly `NQ` and `ES`.

### 7.2 Vocabulary

- Setup types: `break_and_retest`, `swing_failure_pattern`.
- Entry models: `sbs_model_1`, `sbs_model_2`, plus any future
  human-validated model.
- Context/features: PDH, PDL, PDC, HCOM, LCOM, higher-timeframe alignment,
  trapped-trader context, Fib geometry, and 20/200 SMA session context.

SBS is an entry sequence, not a third setup type. The source explicitly calls
B&R and SFP the two setups.

### 7.3 Candidate findings

The corpus explicitly supports these qualitative claims:

- PDH/PDL/PDC are the previous daily high, low, and cash close and form daily
  points of interest.
- HCOM/LCOM are the highest/lowest daily close of the month.
- B&R is a continuation archetype; SFP is a sweep/failure reversal archetype.
- Setups are considered at mapped points of interest, not automatically or in
  the middle of the prior-day range.
- Context ordering is higher-timeframe map, prior-day level, session
  environment, setup, then entry model.
- Trapped-trader logic asks who is trapped, where stops are, and when forced
  exits may occur.
- Fib geometry is a target/asymmetry tool, not a standalone signal.
- The 20/200 SMA is a five-minute context tool, not a standalone signal.
- A chop/consolidation zone is required by the taught execution process.

The corpus does not yet provide one unambiguous deterministic contract for:

- session boundaries and the anchor-bar calendar;
- swing/pivot detection;
- B&R break, retest tolerance, hold, expiry, and reset;
- SFP sweep depth, wick/close behavior, confirmation, and reset;
- chop-zone width, duration, slope, and MA-tangle thresholds;
- trapped-side inference;
- SBS sequence pivots and move-origin boundaries;
- Fib anchors and target-selection hierarchy;
- entry-model selection;
- stop placement and buffers;
- target selection and management;
- numerical confluence weights, range, and threshold.

These remain candidate or unknown. No defaults are inferred from examples.

### 7.4 Conflicting material

`concept_stoic_edge_system_module_1_is_live` teaches a 10/20 sequence and
50/200 higher-timeframe usage. VISION and the roadmap pin 20/200 SMA. The
alternate material is preserved as an unresolved conflict and is not merged
into the v1 executable profile.

## 8. Executable rule grammar

Validated rules use a small allowlisted declarative grammar:

- typed operands: bar field, derived feature, constant, prior value;
- comparisons: `eq`, `lt`, `lte`, `gt`, `gte`, `crosses_above`,
  `crosses_below`;
- logic: `all`, `any`, `not`;
- bounded temporal operations: `within_bars`, `sequence`, `consecutive`;
- explicit closed-bar semantics and bounded lookbacks.

Each validated executable rule is one complete setup-and-direction profile.
Entry, stop, and target are closed value expressions over a current closed bar,
bounded prior value, finite constant, or allowlisted deterministic feature.
Price fields are OHLC-only; literal NQ/ES prices must align exactly to the
0.25-point tick and are never silently rounded. Each profile selects an
allowlisted entry model, declares the direction-specific orientation guard,
computes R with the fixed `reward_over_risk` operation, and computes confidence
with an allowlisted weighted confluence formula. SP2 must suppress a signal if
evaluated prices fail the orientation guard or market-data tick validation.

Forbidden:

- arbitrary code, `eval`, imports, plugin names, or callbacks;
- network or model calls;
- future-bar/lookahead references;
- unbounded windows;
- binary-float price math;
- order/execution actions.

Prices and R calculations use decimal/tick-aware arithmetic.

The initial SP0 candidate contains no executable predicate because the exact
rules are not yet human-validated.

## 9. Publication gates and fitness functions

The validator and publisher enforce:

1. strict schema, unique IDs, and supported schema major;
2. every evidence reference resolves and every cited file digest matches;
3. source media/transcript or PDF is present for each normative claim;
4. scope is exactly NQ/ES and all timeframe maps match VISION;
5. setup types are B&R/SFP; SBS is modeled separately;
6. every live-required capability is `validated`;
7. entry, stop, target, R, and confidence are complete and directionally valid;
8. every executable clause uses only allowlisted bounded operators;
9. a human approval matches the canonical YAML digest and verifies against the
   externally pinned Ed25519 public key;
10. canonical compilation is reproducible;
11. no execution action, broker integration, model dependency, or SP3-derived
    parameter enters the release.

SP2 must fail closed on draft status, unknown schema, unresolved rule, missing
approval, or release hash mismatch.

## 10. Human-validation dossier

The generated Markdown includes:

- fixed Vision scope and guardrails;
- glossary and evidence matrix;
- candidate strategy claims;
- exact unresolved decisions;
- source conflicts;
- publication readiness and blockers;
- approval instructions and candidate digest.

The dossier does not present candidate interpretations as Stoic canon.

## 11. Acceptance criteria

- `strategy/rulebook.yaml` validates structurally and all citations resolve.
- The generated dossier is deterministic and clearly reports `BLOCKED`.
- Publishing the current incomplete candidate fails without creating a release.
- A synthetic complete, digest-approved fixture publishes deterministically.
- Duplicate YAML keys, stale source hashes, stale approval, unsupported
  instruments/timeframes/operators, and model/execution actions fail validation.
- Invalid or unsigned approvals and approvals made with an unpinned key fail
  publication and release loading.
- SP2 has a stable API that loads published JSON only and fails closed.
- Tests prove backtest fields cannot feed rulebook publication.
- `VISION.md` is unchanged by the milestone.

## 12. Decisions

- [ADR-0001](../../architecture/adr/0001-rulebook-authoring-and-release.md)
- [ADR-0002](../../architecture/adr/0002-content-addressed-human-approval.md)
- [ADR-0003](../../architecture/adr/0003-bounded-rule-expression-language.md)
- [ADR-0004](../../architecture/adr/0004-strategy-source-authority.md)
