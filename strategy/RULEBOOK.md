# Strategy Rulebook Review Dossier

- Rulebook version: `0.1.0-candidate`
- Candidate digest: `4ecd2bdc433ca4ab884018a9278425cbecba0476108d1e2af957935b30901737`
- **Publication readiness: BLOCKED**

## Fixed Scope and Guardrails

- Runtime instruments: `NQ, ES`
- Signals only; no broker or execution actions.
- No model, prompt, network, or backtest dependency can enter a release.

## Timeframe Maps

| Type | HTF | Setup | Execute | Manage |
|---|---|---|---|---|
| Scalp | 15m | 5m | 1m | 5m |
| Day | 60m | 5m | 1m | 5m |
| Swing | 1d | 60m | 15m | 60m |
| Position | 1w | 1d | 60m | 1d |

## Evidence Matrix

| ID | Kind | Asset | Asset SHA-256 | Transcript | Transcript SHA-256 | Locator | Human review | Claim |
|---|---|---|---|---|---|---|---|---|
| ev-alternate-sma-profile | media | edu/videos/Stoic Edge System Module 1 is Live · Stoic Traders.mp4 | d15392660ba74ae4185dc8f35dd34ba7a8a0641a9efa1b87339ea9916cc9cb93 | edu/derived/concept_stoic_edge_system_module_1_is_live/transcript.json | fd4204f0ccd2d8fc7cc85b4a6b64bb3ae6347c2fa0ed4ee5237b9bea3c01349a | end=00:20:15, start=00:16:08 | **not reviewed** | An alternate module describes 10 and 20 SMA for its sequence and 50 and 200 SMA for higher-timeframe trend. |
| ev-chop-zone | media | edu/videos/Simple Stoic Setups SSS - Stoic Trader Concepts · Stoic Traders.mp4 | 52add00969e6217b132d8e5e1e62123a30c79a7c33abc5f90163c3522f32fcf9 | edu/derived/concept_simple_stoic_setups_sss/transcript.json | b460c364caafeef8c428ee63dda17bc0223bc029d8f18ea03ee74f8c6ac6c94e | end=00:45:11, start=00:44:32 | **not reviewed** | The chop zone is tight sideways consolidation around moving averages; higher-timeframe context supplies direction and the chop zone supplies timing. |
| ev-context-ordering | media | edu/start_here/The-Only-Trading-Video-That-You-Will-Ever_Need_1080p.mp4 | 48e4cf57745ba70422c27afe9605f067b5ed0b0a98f3ca581cf97eb2efe2bb25 | edu/derived/concept_the_only_trading_video_that_you_will_ever_need/transcript.json | 29706bd24e101962dc2ede1316f36e208058f5ef3a6d5e645ccd4322e9a60632 | end=00:37:05, start=00:36:35 | **not reviewed** | HCOM and LCOM provide the higher-timeframe map, prior-day levels frame the day, and the moving averages provide session context. |
| ev-fib-target-context | media | edu/start_here/The-Only-Trading-Video-That-You-Will-Ever_Need_1080p.mp4 | 48e4cf57745ba70422c27afe9605f067b5ed0b0a98f3ca581cf97eb2efe2bb25 | edu/derived/concept_the_only_trading_video_that_you_will_ever_need/transcript.json | 29706bd24e101962dc2ede1316f36e208058f5ef3a6d5e645ccd4322e9a60632 | end=00:52:15, start=00:51:19 | **not reviewed** | Fib geometry is used to measure targets and pullbacks. |
| ev-hcom-lcom | media | edu/start_here/The-Only-Trading-Video-That-You-Will-Ever_Need_1080p.mp4 | 48e4cf57745ba70422c27afe9605f067b5ed0b0a98f3ca581cf97eb2efe2bb25 | edu/derived/concept_the_only_trading_video_that_you_will_ever_need/transcript.json | 29706bd24e101962dc2ede1316f36e208058f5ef3a6d5e645ccd4322e9a60632 | end=00:28:00, start=00:27:49 | **not reviewed** | HCOM is the highest daily close of the month and LCOM is the lowest daily close of the month. |
| ev-pdh-pdl-pdc | media | edu/videos/Candle Swing Theory PDH PDL PDC - Stoic Trader Concepts · Stoic Traders.mp4 | 4543ed2b26a82a8fbc1f6f023691b57cf6c9f3a41c163466b9944ceaaa76bee4 | edu/derived/concept_candle_swing_theory_pdh_pdl_pdc/transcript.json | f48c0585ba2f5dce503b8b1ac41d3a2bb16dfee9b6af20ab5b35648adb250a64 | end=00:04:08, start=00:03:45 | **not reviewed** | The three points of interest are the previous daily high, previous daily low, and previous daily close; price is waited for at those levels. |
| ev-poi-not-middle-range | media | edu/videos/Candle Swing Theory PDH PDL PDC - Stoic Trader Concepts · Stoic Traders.mp4 | 4543ed2b26a82a8fbc1f6f023691b57cf6c9f3a41c163466b9944ceaaa76bee4 | edu/derived/concept_candle_swing_theory_pdh_pdl_pdc/transcript.json | f48c0585ba2f5dce503b8b1ac41d3a2bb16dfee9b6af20ab5b35648adb250a64 | end=00:22:44, start=00:22:30 | **not reviewed** | The taught setups are considered at previous-day levels rather than in the middle of the prior-day range. |
| ev-sbs-entry-model | media | edu/start_here/The-Only-Trading-Video-That-You-Will-Ever_Need_1080p.mp4 | 48e4cf57745ba70422c27afe9605f067b5ed0b0a98f3ca581cf97eb2efe2bb25 | edu/derived/concept_the_only_trading_video_that_you_will_ever_need/transcript.json | 29706bd24e101962dc2ede1316f36e208058f5ef3a6d5e645ccd4322e9a60632 | end=00:50:58, start=00:46:55 | **not reviewed** | SBS is a swing breakout sequence with two described models and is used as an entry model, not as a third setup type. |
| ev-setup-taxonomy | media | edu/videos/Candle Swing Theory PDH PDL PDC - Stoic Trader Concepts · Stoic Traders.mp4 | 4543ed2b26a82a8fbc1f6f023691b57cf6c9f3a41c163466b9944ceaaa76bee4 | edu/derived/concept_candle_swing_theory_pdh_pdl_pdc/transcript.json | f48c0585ba2f5dce503b8b1ac41d3a2bb16dfee9b6af20ab5b35648adb250a64 | end=00:07:11, start=00:06:27 | **not reviewed** | The two setups are a reversal swing failure pattern and a continuation break and retest. |
| ev-sma-session-context | media | edu/start_here/The-Only-Trading-Video-That-You-Will-Ever_Need_1080p.mp4 | 48e4cf57745ba70422c27afe9605f067b5ed0b0a98f3ca581cf97eb2efe2bb25 | edu/derived/concept_the_only_trading_video_that_you_will_ever_need/transcript.json | 29706bd24e101962dc2ede1316f36e208058f5ef3a6d5e645ccd4322e9a60632 | end=00:45:44, start=00:44:34 | **not reviewed** | The 20 and 200 simple moving averages help with session bias, are read with the existing higher-timeframe territory, and do not constitute a trade by themselves. |
| ev-trapped-trader-context | media | edu/videos/HTF Stoic Trader Protocol - Stoic Trader Concepts · Stoic Traders.mp4 | fa82d43b6674052ae3bfe6afde3fb87e11e081abf4a238560361e5f2ed840ddc | edu/derived/concept_htf_stoic_trader_protocol/transcript.json | 7ab259a56cdc3bbad239051c226430ee47bf732fc5a530176006b369fe938c4e | end=00:04:41, start=00:04:15 | **not reviewed** | The context questions are who is trapped, where their stops are, and when they may be forced to exit. |

## Glossary

| Term | Meaning | Evidence |
|---|---|---|
| 20/200 SMA | Five-minute simple-moving-average context used to read session bias; not a standalone signal. | ev-sma-session-context |
| B&R | Break and retest; the continuation setup archetype. | ev-setup-taxonomy |
| Chop zone | Tight sideways consolidation around moving averages used as timing context. | ev-chop-zone |
| Fib geometry | A tool used in the cited process for measuring pullbacks, targets, and asymmetry. | ev-fib-target-context |
| HCOM | Highest daily close of the month. | ev-hcom-lcom |
| LCOM | Lowest daily close of the month. | ev-hcom-lcom |
| PDC | Previous daily cash close. | ev-pdh-pdl-pdc |
| PDH | Previous daily high. | ev-pdh-pdl-pdc |
| PDL | Previous daily low. | ev-pdh-pdl-pdc |
| SBS | Swing breakout sequence; an entry sequence with two described models. | ev-sbs-entry-model |
| SFP | Swing failure pattern; the sweep or failure reversal setup archetype. | ev-setup-taxonomy |

## Illustrative Examples (Non-Normative)

| ID | Label | Claim |
|---|---|---|
| ex-es-monthly-close-map | ES: S&P 500, 2026 monthly-close map | The ES case-study chart visually labels monthly HCOM and LCOM levels. |
| ex-nq-consolidation-expansion | NQ Feb 3rd: Consolidation to Expansion | The NQ case-study chart visually labels February HCOM, February LCOM, consolidation-to-expansion, and Fib annotations. |
| ex-nq-opening-range | NQ May 4th: opening-range case study | The NQ case-study chart visually labels a monthly opening range, HCOM, LCOM, SBS, SFP, and session annotations. |

## Candidate Strategy Claims

| ID | Status | Capability | Claim | Evidence |
|---|---|---|---|---|
| break-and-retest-contract | unknown | break_and_retest_predicate | No deterministic contract is validated for break definition, retest tolerance, hold condition, expiry, or reset. | ev-setup-taxonomy |
| chop-zone-required | candidate | chop_zone_context | The taught execution process requires a chop or consolidation zone before considering an entry. | ev-chop-zone |
| context-ordering | candidate | context_sequence | Context is considered in this order: higher-timeframe map, prior-day level, session environment, setup, then entry model. | ev-context-ordering, ev-sbs-entry-model, ev-sma-session-context |
| daily-points-of-interest | candidate | daily_level_context | PDH, PDL, and PDC are the previous daily high, previous daily low, and previous daily close; they are daily points of interest. | ev-pdh-pdl-pdc |
| fib-geometry-context | candidate | target_context | In the cited process, Fib geometry is used to measure pullbacks, targets, and asymmetry. | ev-fib-target-context |
| monthly-close-extremes | candidate | higher_timeframe_context | HCOM and LCOM are respectively the highest and lowest daily close of the month. | ev-hcom-lcom |
| point-of-interest-location | candidate | location_filter | A setup is considered at a mapped point of interest, not automatically in the middle of the prior-day range. | ev-poi-not-middle-range |
| sbs-entry-model | candidate | entry_model_selection | SBS is an entry sequence with model 1 and model 2 descriptions, not a third setup type. | ev-sbs-entry-model, ev-setup-taxonomy |
| setup-taxonomy | candidate | setup_classification | break_and_retest is the continuation archetype and swing_failure_pattern is the sweep or failure reversal archetype; these are the two setup types. | ev-setup-taxonomy |
| signal-construction | unknown | entry_stop_target_r_confidence | No executable entry, stop, target, R-multiple, management, or deterministic confluence-score contract is validated. | ev-chop-zone, ev-fib-target-context, ev-sbs-entry-model |
| sma-session-context | candidate | moving_average_context | The 20 and 200 SMA are a five-minute session-context tool, not a standalone signal. | ev-sma-session-context |
| swing-failure-contract | unknown | swing_failure_pattern_predicate | No deterministic contract is validated for sweep depth, wick or close behavior, confirmation, expiry, or reset. | ev-setup-taxonomy |
| trapped-trader-context | candidate | trapped_trader_context | Trapped-trader context asks which side is trapped, where stops may be, and when forced exits may occur. | ev-trapped-trader-context |

## Unresolved Decisions

- `break-and-retest-parameters`: What tick-aware break, retest, hold, expiry, and reset parameters define break_and_retest?
- `chop-zone-parameters`: What bounded width, duration, slope, and moving-average-tangle measures define the chop zone?
- `confluence-score`: What deterministic features, weights, range, and signal threshold define confidence?
- `entry-model-selection`: Which entry model is selected for each qualifying setup and context?
- `fib-anchors-and-target-order`: What anchors and target-selection hierarchy make Fib geometry deterministic?
- `pivot-detection`: What closed-bar pivot or swing-detection method and lookback bounds define a swing?
- `primary-evidence-review`: Which cited media ranges have a human reviewer checked before any candidate becomes validated?
- `risk-and-management`: What stop placement, tick buffer, target policy, management, and R-multiple calculation apply to each direction?
- `sbs-pivots-and-origin`: What pivots and move-origin boundaries distinguish SBS model 1 from SBS model 2?
- `session-calendar`: What are the exact session boundaries, anchor-bar calendar, and timezone policy for deterministic evaluation?
- `sfp-parameters`: What tick-aware sweep depth, wick or close behavior, confirmation, expiry, and reset parameters define swing_failure_pattern?
- `trapped-side-inference`: What deterministic observations infer the trapped side, stop location, and forced-exit condition?

## Source Conflicts

- `sma-profile-conflict`: The alternate module teaches a 10 and 20 sequence with 50 and 200 higher-timeframe context, whereas the v1 scope pins a 20 and 200 SMA profile.

## Publication Blockers

- cited evidence has no supported human review: ev-chop-zone
- cited evidence has no supported human review: ev-context-ordering
- cited evidence has no supported human review: ev-fib-target-context
- cited evidence has no supported human review: ev-hcom-lcom
- cited evidence has no supported human review: ev-pdh-pdl-pdc
- cited evidence has no supported human review: ev-poi-not-middle-range
- cited evidence has no supported human review: ev-sbs-entry-model
- cited evidence has no supported human review: ev-setup-taxonomy
- cited evidence has no supported human review: ev-sma-session-context
- cited evidence has no supported human review: ev-trapped-trader-context
- human approval envelope is missing
- live-required profile is not validated: break_and_retest/long
- live-required profile is not validated: break_and_retest/short
- live-required profile is not validated: swing_failure_pattern/long
- live-required profile is not validated: swing_failure_pattern/short
- rule break-and-retest-contract is unknown
- rule signal-construction is unknown
- rule swing-failure-contract is unknown
- unresolved decision: break-and-retest-parameters
- unresolved decision: chop-zone-parameters
- unresolved decision: confluence-score
- unresolved decision: entry-model-selection
- unresolved decision: fib-anchors-and-target-order
- unresolved decision: pivot-detection
- unresolved decision: primary-evidence-review
- unresolved decision: risk-and-management
- unresolved decision: sbs-pivots-and-origin
- unresolved decision: session-calendar
- unresolved decision: sfp-parameters
- unresolved decision: trapped-side-inference
- unresolved source conflict: sma-profile-conflict

## Approval Instructions

1. Keep the Ed25519 private key outside this repository.
2. Compute `public_key_fingerprint` as SHA-256 of the raw 32-byte public key.
3. Run `stoic-rulebook approval-message` with the reviewer email, UTC `Z` timestamp, and fingerprint; redirect its exact binary stdout with no added newline.
4. Sign those exact bytes and base64-encode the raw 64-byte Ed25519 signature.
5. Add `reviewer_email`, `approved_at`, `candidate_sha256`, `public_key_fingerprint`, and `signature_base64` to the approval envelope.
6. Publish with `--public-key-hex`; publication and SP2 verify the signature against that separately pinned raw public key.
Any semantic YAML edit changes the candidate digest and requires a new approval.
