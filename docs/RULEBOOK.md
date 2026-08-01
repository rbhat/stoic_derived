# Rulebook — the 1-2-3 sequence

**The distilled strategy spec. This is the engine's source of truth, not the transcripts.**
Written 2026-08-01 (Phase 2). Every rule below cites the material it comes from. Where the material
declines to pin something, this file says so in the open — it does not invent a number.

---

## 0. How to read this file

Every definition carries a **status**, because Phase 5 has to know which rules it can compile and
which ones need a decision first.

| Status | Meaning |
|---|---|
| **M** — mechanical | Computable from bars alone. No free parameter. |
| **P** — parametric | Computable, but needs one number the material does not give. The number is a recorded decision (§11) or an open row (§12). |
| **J** — judgment | The material states it as a visual read and **explicitly refuses** to quantify it. Formalizing it is a decision, not a derivation. |

A **J** term is not a gap in our reading of the material. `M1 @ 10:18` says the vagueness is
deliberate: *"I use the word meaningful on purpose. A fixed percentage or minimum candle size would
create precision that the chart does not provide."* Treat a proposed number for a **J** term as a
strategy decision requiring the human, per the standing directive in `CLAUDE.md`.

### Citation keys

| Key | File |
|---|---|
| `PC` | `edu/123sequence/price_cycle.jpg` |
| `M1` | `edu/derived/concept_stoic_edge_system_module_1_is_live/transcript.md` — cited by timestamp |
| `ET` | `edu/123sequence/entry_technique/entry_technique_for_1-2-3_sequence.md` |
| `PTBQ` | `edu/123sequence/concepts/PTB Questions.md` |
| `DISC` | `edu/123sequence/discussion/discussions.md` (with `discussion/Q1.png`) |
| `DIA-L` | `edu/123sequence/entry_technique/step-3-pullback-diagram.svg` (bullish; byte-identical to `step-1-2-3.svg`) |
| `DIA-S` | `edu/123sequence/entry_technique/step-3-pullback-bearish-diagram.svg` |
| `LT` | `edu/123sequence/entry_technique/step-3-livetrade.png` |
| `T1` | `edu/123sequence/stoic_trade1.png` |
| `MAS` | `edu/123sequence/stoic_ma_study.png` |
| `SCALP` | `edu/derived/concept_scalping_example_live_trading_session/transcript.md` — by timestamp |
| `OTV` | `edu/123sequence/start_here/only_trading_video.md` — by timestamp |
| `TFG` | `edu/123sequence/concepts/Timeframes Guide` |
| `HOW` | `edu/123sequence/concepts/how_to_use_stoic_concepts.txt` |
| `CMD` | `edu/123sequence/concepts/stoic_commandments.txt` |
| `SSS` | `edu/derived/concept_simple_stoic_setups_sss/transcript.md` — by timestamp |
| `HTF` | `edu/derived/concept_htf_stoic_trader_protocol/transcript.md` — by timestamp |
| `CST` | `edu/derived/concept_candle_swing_theory_pdh_pdl_pdc/transcript.md` — by timestamp |
| `WM` | `edu/123sequence/war_map/war map jul 23.pdf` |

A citation is checkable: `grep '00:09:07' edu/derived/concept_stoic_edge_system_module_1_is_live/transcript.md`.

### Precedence when sources disagree

1. **`M1` and `PC` govern the sequence.** `M1 @ 01:06` calls the Stoic Edge System course *"the
   current operating version"* and *"if an older lesson conflicts with the rule taught here, follow
   this course and the current rulebook."* `PC` is that course's one-slide framework (`M1 @ 08:36`).
2. **`ET` + `PTBQ` govern the entry**, which `M1`/`PC` leave at *"Step 3 Break"* (see §5.1).
3. `OTV`, `SCALP`, `MAS` illustrate and add context. They never override 1 or 2.
4. `SSS`, `HTF`, `CST`, `WM` are a **different system** — see §13. They are context only.

---

## 1. The chart contract

The sequence is read on **one selected chart** and that chart does not change mid-sequence.

| # | Rule | Status | Source |
|---|---|---|---|
| 1.1 | The chart carries **10 and 20 SMA** (the sequence pair) and **50 and 200 SMA** (the trend filter). | M | `M1 @ 03:45`, `M1 @ 16:52`, `MAS` |
| 1.2 | *"We use 50 and 200 SMA for the higher timeframe trend. And we use 10 and 20 SMA for the three-step sequence."* | M | `M1 @ 20:09` |
| 1.3 | Once the sequence begins, **timeframe, session display and MA settings stay fixed** until the confirmed opposite Step 3 exits the position. | M | `M1 @ 05:46`, `M1 @ 15:27` |
| 1.4 | The framework is timeframe-agnostic: *"the chart interval and the speed of the sequence changes but the operating sequence remains consistent."* Pick the chart that matches the decision. | M | `M1 @ 05:11`, `M1 @ 05:38` |
| 1.5 | Universal means the **structure** travels, not that every chart contains a trade. Liquidity, spreads, volatility and account risk are a **separate** decision from the chart signal. | — | `M1 @ 06:07`, `M1 @ 06:30` |
| 1.6 | The MAs organise what price is already doing; they do not predict and they are *"visual guides not laser lines that price must obey to the tick."* | — | `M1 @ 04:29`, `M1 @ 11:14` |

**Engine note.** 1.3 means state is per `(instrument, timeframe, MA-pair)`. Switching timeframe mid-
sequence is a different chart decision, not a refinement of the same one.

---

## 2. The sequence

### 2.0 The one-slide framework, verbatim from `PC`

> **Step 1:** Meaningful break and close beyond both MAs.
> **Step 2:** Return toward the MA trend area and form an obvious base.
> **Step 3:** Break the selected base boundary in the direction of Step 1.
>
> **Entry:** Step 3 Break
> **Confirmation:** Meaningful close beyond the selected boundary
> **Final Technical Exit:** Confirmed opposite Step 3

`PC` also annotates the top and bottom of the cycle with *"Climax: Price visibly extended from the MA
structure"*, and labels the swing after a bearish sequence *"Lower High"* / after a bullish sequence
*"Higher Low"*.

### 2.1 Step 1 — the break

| # | Rule | Status | Source |
|---|---|---|---|
| 2.1.1 | **Bullish Step 1**: a meaningful visual break **and close above both** the 10 and 20 SMA. **Bearish**: break and close **below both**. | P | `PC`, `M1 @ 09:47`, `M1 @ 10:03` |
| 2.1.2 | *"A wick alone does not count."* | M | `M1 @ 10:03` |
| 2.1.3 | *"A quick test through the averages that closes back inside does not complete step one."* | M | `M1 @ 10:10` |
| 2.1.4 | "Meaningful" is deliberately unquantified — see the **J** note in §0. If you have to argue with yourself about it, pass. | J | `M1 @ 10:18`, `M1 @ 10:32` |
| 2.1.5 | Step 1 makes a directional shift *visible*. It is **not** an entry: *"entry still waits for the retest, the base, and the break of that base."* | M | `M1 @ 10:40` |

The **direction of Step 1 is the direction of the whole sequence** — Step 3 must break in it (§2.3.1),
and the trade is taken in it.

### 2.2 Step 2 — the return and the base

| # | Rule | Status | Source |
|---|---|---|---|
| 2.2.1 | After Step 1, price **returns toward the trend area represented by the 10 and 20 SMA**. | M | `PC`, `M1 @ 10:49` |
| 2.2.2 | *"An exact touch of one or both averages is optional."* The MAs mark the area, not a level to hit. | M | `M1 @ 11:06` |
| 2.2.3 | The return must **visually retest the 10/20 trend area and form a base / consolidation**, though it need not touch the averages exactly. | J | `PTBQ` §3 |
| 2.2.4 | A pullback alone is **not** Step 2. *"We have a pullback to the moving averages but this is not enough to enter. We need to wait for consolidation and then break."* | M | `SCALP @ 28:02`, `SCALP @ 27:32` |
| 2.2.5 | The base must be **obvious**, with a **boundary markable before the break**. | J | `PC`, `M1 @ 11:22` |
| 2.2.6 | The boundary may be *"clear support resistance or an obvious trend line"*; other consolidation shapes qualify *"without creating another setup system."* | J | `M1 @ 11:31` |
| 2.2.7 | In `PC` the bearish selected boundary is drawn **horizontal** under the base; the bullish one is drawn as an **up-sloping line** over the base. A boundary is therefore not necessarily horizontal. | J | `PC` |
| 2.2.8 | The boundary is **chosen while the outcome is still hidden**. *"A perfect line discovered after price has moved is hindsight."* | M | `M1 @ 11:45`, `M1 @ 12:11` |
| 2.2.9 | If **two possible bases** appear, select the one that clearly controls the setup. *"If two boundaries look equally valid there is no clean step three yet"* — wait. | J | `M1 @ 12:41`, `M1 @ 12:49` |

**Engine note on 2.2.8.** This is the hardest fidelity constraint in the whole spec. A backtest that
picks the boundary using bars after the break is not reproducing the method; it is reproducing
hindsight. Boundary selection must be a function of bars **up to and including** the last base bar.

### 2.3 Step 3 — the break of the boundary

| # | Rule | Status | Source |
|---|---|---|---|
| 2.3.1 | **Step 3 begins** when price trades through the **pre-selected boundary in the direction of Step 1**. | M | `PC`, `M1 @ 13:22` |
| 2.3.2 | *"A gap through the boundary still counts as a break."* | M | `M1 @ 14:26` |
| 2.3.3 | The break **creates the entry opportunity**; it does not confirm anything. | M | `PC`, `M1 @ 09:15`, `M1 @ 14:02` |
| 2.3.4 | **Confirmed Step 3** = a *meaningful close beyond the selected boundary*. | P | `PC`, `M1 @ 09:15` |
| 2.3.5 | *"Only a confirmed step 3 changes the chart's technical directional state. An intra-bar break can permit an early entry but it does not make the system technically bullish or bearish before the meaningful close."* | M | `M1 @ 14:10` |
| 2.3.6 | Once bullish Step 3 confirms, **the system is technically bullish on this chart** (and the mirror for bearish). | M | `M1 @ 15:21` |
| 2.3.7 | A break that closes **back inside** the consolidation did **not** confirm. The base *"may remain pending while it is still visually intact. Otherwise, discard it and wait for a fresh consolidation."* | J | `M1 @ 14:40` |
| 2.3.8 | Two execution choices are taught: enter **while the break is happening** (discretionary, unconfirmed) or **wait for the close** and evaluate after confirmation. Whether to take the signal at all is a separate trading decision. | — | `M1 @ 13:30`, `M1 @ 13:54` |
| 2.3.9 | Waiting costs geometry: *"the more you wait for the confirmation the worse your risk to reward will be."* | — | `M1 @ 20:52` |
| 2.3.10 | A boundary that is merely **swept by a wick** is not a Step 3. Worked negative example: *"the step three would be the breakout … but we just barely swept that high … and continues lower."* | M | `M1 @ 19:18`–`19:46` |

### 2.4 Cancellation and reset

| # | Rule | Status | Source |
|---|---|---|---|
| 2.4.1 | **No Step 3 means no entry.** If price never breaks the base in the direction of Step 1, the pattern stays incomplete. | M | `M1 @ 12:57`, `M1 @ 13:14` |
| 2.4.2 | A **wrong-way break**, a **visibly destroyed base**, or a **clear replacement structure** cancels the pending setup. | J | `M1 @ 13:04` |
| 2.4.3 | **Reset rule.** *"If price keeps breaking through the moving averages, reset the count and start again with Step 1."* | M | `DISC` §1 |
| 2.4.4 | Worked reset, narrated bar by bar: a bullish count is abandoned when price breaks back below the averages, and a new count 1-2-3 starts there. *"We can reset the count because the price broke above the moving averages but then price break below the moving averages, so we have a new count number one, number two and number three."* | M | `SCALP @ 26:26`–`27:21` |
| 2.4.5 | A bearish 1-2-3 that **fails to move lower and reverses back above the averages** is not confirmed; the reversal itself becomes the new (bullish) count. | M | `DISC` §1 with `Q1.png` |

**Open:** 2.4.3 and 2.2.3 both key off "the moving averages" without saying *which pair* governs the
reset — see §12 row **O-3**.

### 2.5 Continuation entries — a second signal without a new Step 1

| # | Rule | Status | Source |
|---|---|---|---|
| 2.5.1 | If you miss the initial Step 3, **leave the old break alone**. | M | `M1 @ 15:40` |
| 2.5.2 | While the original directional structure remains active, wait **on the same chart** for a **fresh base and a new break of that base**. | M | `M1 @ 15:45` |
| 2.5.3 | *"On the continuation entries, a new step one is not required. We're simply trading continuation consolidations that retrace to moving averages."* | M | `M1 @ 15:56` |
| 2.5.4 | Observed in the live chart: `LT` labels **two** entries in one move — *"Step 3 Pullbck Entry"* and, lower, a second *"Pullback Entry"*. | — | `LT` |

**Engine note.** 2.5 means the sequence state machine has a *sustained directional state* after a
Confirmed Step 3, inside which any subsequent base-and-break emits a signal. This is a distinct
signal class from the initial Step 3 and should be labelled as such in the signal record.

---

## 3. Step 3 High / Step 3 Low

| # | Rule | Status | Source |
|---|---|---|---|
| 3.1 | *"Step 3 confirms direction and creates the Step 3 High."* | M | `ET` |
| 3.2 | In `DIA-L` the **Step 3 High** is the extreme of the expansion leg **after** Confirmed Step 3, not the confirming bar itself: Confirmed Step 3 is labelled on the breakout bar, and the Step 3 High line is drawn from the high of a **later** bar (the highest high before the pullback begins). Mirror in `DIA-S` for the **Step 3 Low**. | M | `DIA-L`, `DIA-S` |
| 3.3 | The Step 3 High/Low is the **first target** (§6.1) and the reference for *"sufficient room"* on entry (§5.4). | M | `ET`, `PTBQ` §1 |

**Open:** the diagrams fix the Step 3 High as the running extreme of the post-confirmation leg, but
no source states when that extreme is *final* in live time — see §12 row **O-4**.

---

## 4. Climax

| # | Rule | Status | Source |
|---|---|---|---|
| 4.1 | Climax = *"price visibly extended from the MA structure."* | J | `PC` |
| 4.2 | The reference is specifically the **10 SMA**: *"a move running far away from the 10 simple moving average can be a visual climax clue."* | J | `M1 @ 16:19` |
| 4.3 | Climax is a **management** cue only — a reason to stop adding or take a partial. *"These are management choices. They do not create a new signal or change the chart's technical state."* | M | `M1 @ 16:31` |
| 4.4 | Same reading in the live session, called capitulation: *"we are running away from the 10 simple moving average and every time we do that a lot of the times we have a snap back to the 10 and 20 and continuation."* | J | `SCALP @ 16:19` |

**Engine note.** 4.3 is a hard constraint on the L2 state machine: a climax must never fire, suppress
or invalidate a signal. It may only annotate the record and drive partials.

---

## 5. The entry

### 5.1 Which entry governs

`PC` says **Entry: Step 3 Break**. `ET` teaches a later, more specific trigger: wait for the pullback
after the Step 3 High and enter on the **PTB** break. Both are in the material and they are not the
same bar.

**Resolution (human decision D-4, §11): the PTB break is our entry trigger.** The Step 3 boundary
break remains what it is in `M1` — the event that changes the chart's technical state and opens the
opportunity — but the engine's entry order is placed off the PTB.

`LT` is consistent with this: on a live MNQ 5m short, `Step 2` and `Step 3` are labelled at the
structure, and the executed entries are labelled *"Step 3 Pullbck Entry"* and *"Pullback Entry"* —
both below Step 3, not at the boundary break.

### 5.2 The pullback and the PTB

| # | Rule | Status | Source |
|---|---|---|---|
| 5.2.1 | The chain is: **Confirmed Step 3 → Step 3 High → Pullback → PTB → Entry.** | M | `ET` |
| 5.2.2 | **PTB (Pullback Trigger Bar)** = *"simply the last candle in that pullback."* | M | `ET`, `HOW` |
| 5.2.3 | Bullish: place a **buy stop above the PTB high**; entry triggers when price trades above it. Bearish: the last candle of the **bounce** is the PTB; place a **sell stop below its low**. | M | `ET` |
| 5.2.4 | In `DIA-L` the Entry line sits exactly at the PTB bar's **high**, and the next bar trades through it. Mirror in `DIA-S` at the PTB **low**. | M | `DIA-L`, `DIA-S` |
| 5.2.5 | The pullback **need not reach the moving averages or retest the old base.** *"A shallow pullback can qualify."* | M | `PTBQ` §3 |
| 5.2.6 | The PTB pullback has **no MA-touch and no base-touch requirement** — this is what distinguishes it from Step 2, which does require the visual retest of the 10/20 area. | M | `PTBQ` §3 |

### 5.3 Live activation

Verbatim, `PTBQ` §1:

> After the PTB candidate has closed:
> Bullish: price trades above the latest completed correction bar's high.
> Bearish: price trades below the latest completed correction bar's low.
> The activating bar does not need to close beyond that level. However, it must be the latest
> correction bar within the three-bar window, and sufficient room must remain to the Step 3
> High/Low. **Exact entry buffers, gaps, and fill rules are not yet locked.**

| # | Rule | Status | Source |
|---|---|---|---|
| 5.3.1 | The PTB candidate must have **closed** before it can be activated. | M | `PTBQ` §1 |
| 5.3.2 | Activation is **trade-through, not close-through**. | M | `PTBQ` §1 |
| 5.3.3 | The activating level must belong to the **latest** completed correction bar. | M | `PTBQ` §1 |
| 5.3.4 | "…within the three-bar window" — the window is named but not defined. | — | §12 row **O-1** |
| 5.3.5 | Entry buffers, gap handling and fill rules are **stated as not locked** by the source itself. | — | §12 row **O-2** |

### 5.4 Stop and invalidation

| # | Rule | Status | Source |
|---|---|---|---|
| 5.4.1 | **Stop = the PTB low (long) / PTB high (short).** | M | `PTBQ` §2 |
| 5.4.2 | Therefore **R = \|entry − PTB extreme\|**, and this is the R in every downstream ratio. | M | derived from 5.2.3 + 5.4.1 |
| 5.4.3 | When entering off a faster chart, the **stop is set from the slower chart**: *"we could be entering off of the one minute chart but we could be setting stop loss based on the five minute chart, which is whatever the high is gonna put in."* | M | `SCALP @ 05:42`; decision **D-7**, §11 |
| 5.4.4 | *"Sufficient room must remain to the Step 3 High/Low"* — a minimum-room condition exists but has no number. | — | §12 row **O-5** |
| 5.4.5 | Position-level invalidation, distinct from the stop: the **confirmed opposite Step 3** (§6.4). | M | `PC`, `M1 @ 23:46` |

### 5.5 Anticipatory entry (variant, not the default)

| # | Rule | Status | Source |
|---|---|---|---|
| 5.5.1 | An **inside candle** inside the base is taught as a reason to enter before the boundary break: *"inside candles leading to expansions, that's the whole premise."* | — | `SCALP @ 07:11`, `SCALP @ 07:21` |
| 5.5.2 | It is taught **with its own warning**: *"could be a nice signal to enter earlier and don't wait for the breakdown below the boundary, but be careful because you are really entering without confirmation."* In the same session it produced a −1.2R loss the trader attributed to entering too soon. | — | `SCALP @ 07:29`, `SCALP @ 11:56`, `SCALP @ 12:38` |

**Not in scope for v1 signals.** Recorded because it appears in the labelled material and Phase 3
labels may show it; the engine should not emit it. See decision **D-11**, §11.

---

## 6. Targets, management and exit

| # | Rule | Status | Source |
|---|---|---|---|
| 6.1 | **First target = the Step 3 High (long) / Step 3 Low (short).** *"This is the place to take partials and put stop to break even."* | M | `ET` |
| 6.2 | **Second target = the 2.618 fib extension.** | M | decision **D-6**, §11; measured in `SCALP @ 06:35`; drawn on `LT` and `T1` as `261.80%` |
| 6.3 | Fib geometry is a **measurement** tool for targets, anchored on the pullback: measure the **first pullback** after the reversal with the trend-extension tool; the published extension levels are **2.618, 4.23 and 6.86**. | P | `OTV @ 51:26`, `OTV @ 52:39`, `OTV @ 52:44` |
| 6.4 | **Final technical exit = the confirmed opposite Step 3**, for the remaining position. Partials may be taken before it. | M | `PC`, `M1 @ 09:24`, `M1 @ 23:46` |
| 6.5 | Between entry and 6.4, the position is simply held: *"we simply stay with the move until the complete opposite one two three pattern confirms."* | M | `M1 @ 09:24` |
| 6.6 | Climax is the only other sanctioned management cue (§4.3). | M | `M1 @ 16:19` |

**Open:** 6.3's anchor. `OTV` measures *"the first pullback after reversal"*; `SCALP @ 06:35`
measures *"the first lower high"* of the current leg. Whether the Step 3 pullback and the fib anchor
pullback are the same swing is not stated — see §12 row **O-6**.

**Open:** 6.2 vs 6.1 ordering when the Step 3 High/Low sits beyond 2.618, and partial sizing at each
— see §12 row **O-7**.

---

## 7. Direction filters and gating

The sequence produces a signal. These decide whether it deserves risk.

### 7.1 The 50/200 trend filter (the filter `M1` teaches with the sequence)

| # | Rule | Status | Source |
|---|---|---|---|
| 7.1.1 | *"The best setups are going to be in the direction of the 50 and 200 simple moving average."* | M | `M1 @ 18:30` |
| 7.1.2 | *"When the price is staying above 50 you only want to take bullish setups; when the price is staying below 50 you want to look for the bearish setups."* | M | `M1 @ 18:38` |
| 7.1.3 | The 200 SMA carries the higher-timeframe trend: *"we are looking for the bullish setup here because the price is staying above 200 SMA … the higher time frame trend is bullish."* | M | `M1 @ 19:54` |
| 7.1.4 | Do not take a trade **into** the 200 SMA on fast charts: *"on one minute chart, five minute chart, do not long into the 200 SMA."* | M | `SCALP @ 23:02` |
| 7.1.5 | The MAs act as **staged destinations**: *"you can long from 10 20 back to 50, from 50 to 200, and then eventually it flips."* | — | `SCALP @ 22:45` |

**"Staying above/below"** in 7.1.2 has no bar count or tolerance — see §12 row **O-8**.

### 7.2 The 20/200 session bias (the free-training layer)

`OTV` teaches a **20 and 200 SMA** pair on the 5m for session bias — a different pair from `M1`'s
50/200. Recorded for completeness; `M1` governs per §0 precedence.

| # | Rule | Status | Source |
|---|---|---|---|
| 7.2.1 | *"The 20 and 200 SMA help with session bias"* — used mainly on the 5-minute chart. | — | `OTV @ 44:39` |
| 7.2.2 | The read is three-state: price above and accepting / below and failing / **chopping through them, which names a no-edge zone**. | — | `OTV @ 45:20` |
| 7.2.3 | Ordering of the whole map: *"Monthly extremes give the higher time frame bias. Previous day levels frame the day. The 20 and 200 SMA logic help with session bias. Then the setup has to form."* | — | `OTV @ 36:30` |

### 7.3 The higher-timeframe map

| Term | Definition | Status | Source |
|---|---|---|---|
| **HCOM** | **Highest daily close of the month.** *"Not the highest wick"* — the close, because it shows where the market accepted price at the end of the day. | M | `OTV @ 27:54`, `HOW` |
| **LCOM** | **Lowest daily close of the month.** | M | `OTV @ 27:54`, `HOW` |
| **PDH / PDL / PDC** | Previous day high / low / close. *"They tell you where yesterday's market made decisions."* The daily close is the only intraday-relevant close the material trusts, because it is the cash close. | M | `OTV @ 35:29`, `CST @ 04:49` |
| **Trapped side** | The side that committed late into an extreme and would be forced to exit if it fails. Not a pattern — *"where did one side commit very hard, where did they get comfortable, where would they be wrong, where would they be forced to exit."* | J | `OTV @ 31:59`, `OTV @ 30:29` |
| **Asymmetrical R:R** | Risk defined clearly and close, while the forced move is much larger. Not a guarantee. | — | `OTV @ 33:09` |

**HCOM/LCOM lookback:** decision **D-8**, §11 — three months, from the Stoic indicator.

### 7.4 The no-edge zone

| # | Rule | Status | Source |
|---|---|---|---|
| 7.4.1 | Definition: *"any part of the chart where price may be moving but the stoic lens gives you no clear reason to risk capital."* Price moving in it is not evidence it was tradable. | J | `OTV @ 25:30` |
| 7.4.2 | Enumerated instances: the middle of the range; **messy chop around the 20 and 200 SMA**; low-conviction candles far from meaningful levels; **setups with no trap side**; **trades with no clean invalidation**; **trades with no realistic target**; boredom trades; chase trades. | J | `OTV @ 26:20` |
| 7.4.3 | The only mechanical statement of it found in the corpus: *"we do not trade these setups in the middle of previous daily high and previous daily low; we only trade these setups when price has traded to our POIs."* | M | `CST @ 22:22` |
| 7.4.4 | Three of 7.4.2's instances are already mechanical under this rulebook: no clean invalidation → no PTB stop (§5.4.1); no realistic target → the room condition (§5.4.4, open); no trap side → §7.3. | — | derived |

**Open:** the no-edge zone as a whole is taught as a list of situations, not a condition — see §12
row **O-9**.

### 7.5 Does the setup deserve risk

| # | Rule | Status | Source |
|---|---|---|---|
| 7.5.1 | *"The setup has to deserve risk."* A setup name is not enough: it must have context, asymmetrical R:R, invalidation, and a reason to exist. | J | `OTV @ 11:11`, `CMD` §4 |
| 7.5.2 | **No trade is a valid outcome.** Cash is a position. | — | `CMD` §3, `CMD` §8 |
| 7.5.3 | Observed R expectations in the live session: a scalp of 2–3R is *"a good day"*, 4R *"exceptional"*; a day trade held into the close targets ~5R. These are the trader's stated expectations, **not** a minimum-R rule. | — | `SCALP @ 29:32`, `SCALP @ 32:49` |
| 7.5.4 | No minimum R is stated anywhere in the corpus. | — | §12 row **O-10** |

---

## 8. Supporting vocabulary

These are context concepts, not steps of the sequence. Defined here because the signal record and
the confluence score reference them.

| Term | Definition | Status | Source |
|---|---|---|---|
| **Consolidation → expansion** | The whole market-structure model: *"price consolidates, then it expands, then it consolidates again."* Our job is to know where we are in that loop and to enter **from** the consolidation, not to chase the expansion. | — | `OTV @ 37:41`, `OTV @ 41:35` |
| **Cycle stages 1–4** | Stage 1 consolidation after a decline, 2 expansion up, 3 consolidation after an advance, 4 expansion down. Explicitly **not** a trading rule: *"a particular stage describes the market condition. It does not create, filter, confirm or exit a trade."* | — | `M1 @ 06:44`, `M1 @ 08:11` |
| **Break & retest** | The continuation setup. Price breaks a meaningful level, returns to test it, the retest holds. The level is not the trade — the retest must be in the right context, with clean invalidation and room to target. | J | `OTV @ 42:01` |
| **Swing failure pattern (SFP)** | The failure setup, *"the same thing as break and retest"* inverted — also called sweep and retest. Price takes a prior swing high/low, late breakout traders enter, then price fails back through the level and traps them. | J | `OTV @ 42:31` |
| **Two setups only** | *"There are only two trading setups I care about … break and retest or swing failure pattern."* | — | `OTV @ 40:44`, `HOW` |
| **SBS (Swing Breakout Sequence)** | The entry model taught alongside the two setups. **Model 1**: break and retest at the top of the range — breakout, new high, return that liquidates the first breakout buyers, a double bottom (lower-low or lower-high variant), then buy that breakout. **Model 2**: the deeper version — instead of holding at the top of the range, price sweeps down into the move origin (the order block, *"the last move down before the price goes higher"*). *"If this level holds, it's likely SBS model 1. If this level fails, you have SBS model 2."* | J | `OTV @ 46:58`, `OTV @ 47:33`, `OTV @ 49:16`, `OTV @ 50:22` |
| **SBS requires the sweep** | Negative example from the live session: *"that's not really an SBS there — didn't sweep that high, by the tick."* | M | `SCALP @ 15:29` |
| **Fib geometry** | Measurement of pullbacks and projection of targets — see §6.3. *"Fibs aren't prophecy. They are measurement tools."* | P | `OTV @ 51:26`, `OTV @ 1:11:15` |
| **Higher low / lower high** | Reversal tell used for stop placement and exit: *"if it's a higher low it's a likely scenario for the retracement, for the reversal — that's how most reversals start."* | M | `SCALP @ 29:53`, `SCALP @ 30:56` |

---

## 9. Instantiation per Type

`TFG`, verbatim — *map → setup → optional timing*:

| Type | HTF (map) | LTF (setup) | Execute | Manage |
|---|---|---|---|---|
| Scalp | 15m | 5m | 1m | 5m |
| Day | 60m | 5m | 1m | 5m |
| Swing | Daily | 60m | 15m | 60m |
| Position | Weekly | Daily | 60m | Daily |

**Which chart runs the sequence.** Decision **D-7** (§11): the sequence and its MA pair live on the
**setup** timeframe; the execute timeframe may be used to find a tighter pullback entry; **stop and
targets stay on the setup timeframe** (`SCALP @ 05:42`). For Scalp and Day that means: sequence on
5m against the 5m 10/20 SMA, optional 1m entry timing, stop and targets from the 5m.

This is consistent with `M1 @ 05:11` (the sequence travels across intervals unchanged) and with
`M1 @ 15:32`'s warning that switching the timeframe midway *"would create a different chart
decision"* — the 1m look is a timing aid, not a second sequence.

---

## 10. Worked examples

Each of these is a labelled instance in the material. They are the acceptance test for §2–§6 and the
seed set for Phase 3.

### 10.1 `LT` — MNQ, 5m, bearish, live-traded

- **Step 1** labelled on the drop that breaks and closes below the 10/20 ribbon, out of the
  ~28,700–28,750 balance under PDH.
- **Step 2** labelled at the return into the ribbon (~28,700), with `SBS` annotated on the same
  structure.
- **Step 3** labelled on the break below, into the New York open.
- Entries labelled **"Step 3 Pullbck Entry"** and, one leg lower, **"Pullback Entry"** — the
  continuation entry of §2.5.
- Execution marks: short 6 @ 28516.00, cover 6 @ 28345.00. **+2R** annotated near the cover.
- Targets on the chart: **261.80%** near 28,350; PDC/LCOM at ~28,305; PDL at ~28,215.

### 10.2 `T1` — MNQ, 5m, bearish, with the PTB drawn

- Bearish sequence labelled **1**, **2**, **3** down from the 09:30 expansion.
- A horizontal level labelled **`ptb`** at ~28,300 — the PTB extreme, drawn as the trigger level, as
  §5.2.3 requires.
- Two shorts (7 @ 28231.75, 9 @ 28286.67), two covers, marked **−1R** and **+1R**.
- **261.80%** target at ~28,100; PLOW at 28,244; Jun LCOM at 28,482.

### 10.3 `DIA-L` / `DIA-S` — the schematic, bar by bar

Reading the bullish diagram left to right (the bearish one is its exact mirror):

1. Four small bars along the flat 10/20 ribbon.
2. **Step 1** — a large green bar breaking and closing above both MAs.
3. Three red bars returning into the ribbon: **Step 2**, labelled on the last of them.
4. A green bar, then a large green expansion bar: **Confirmed Step 3**, labelled on the second.
5. Two more green bars up; the **Step 3 High** line is drawn from the high of the second of these —
   the extreme of the leg, not of the confirming bar.
6. Two red bars down into the ribbon; the last is the **PTB**.
7. The next bar trades above the PTB high: **Entry**, drawn exactly at the PTB high.

In this diagram the PTB's low lands on the 20 SMA — but §5.2.5 makes that incidental, not required.

### 10.4 `M1 @ 17:04`–`21:21` — the narrated chart walkthrough

The clearest sequence-counting example in the corpus, including the **negative** case at
`M1 @ 19:03`–`19:46` where a bullish Step 3 never completes because the boundary is only swept.

### 10.5 `Q1.png` with `DISC` — a bearish count that resets

A bearish 1-2-3 that is **not** confirmed; price reverses, breaks above the 10/20/50/200, retests,
and continues higher — *"that is completed 1-2-3"* in the opposite direction. Fib retracement 0.5 /
0.618 is drawn on the reversal leg.

### 10.6 `SCALP @ 25:59`–`27:21` — reset narrated bar by bar

Cited in full at 2.4.4. The single best source for how the count is abandoned and restarted.

---

## 11. Decisions

Places the material genuinely underdetermines, settled by the human and recorded here. These are
**strategy decisions**, not readings of the material. They were collected in the Phase-2 register;
this file is now their durable home.

| ID | Question | Decision | Binds |
|---|---|---|---|
| **D-1** | Which MAs define the sequence | **10/20 SMA define the sequence; 50/200 give the trend filter.** Derived from the material at the human's instruction (*"Lets derive from material"*), and stated directly at `M1 @ 20:09`. | §1.1, §2, §7.1 |
| **D-2** | What makes a break/close "meaningful" | **Body, not wick. The stronger the surge, the better.** Confirms and narrows `M1 @ 10:03`. No threshold set. | §2.1.1, §2.3.4 |
| **D-3** | What makes a base "obvious" | **Range compression, proximity to the MA trend area, no obvious breakouts inside it.** | §2.2.5 |
| **D-4** | How the entry trigger is defined | **The entry trigger is the PTB**, per `PTBQ`. The Step 3 boundary break remains the state change, not the order. | §5.1 |
| **D-5** | What "visibly extended" means for climax | **Deferred.** Human's answer: *"Will have to define, keep it till we get more info."* Climax stays advisory (§4.3), so nothing is blocked. | §4 |
| **D-6** | Which target governs | **TP1 = Step 3 High/Low; TP2 = 2.618 fib extension.** | §6.1, §6.2 |
| **D-7** | MA pair per timeframe | **The sequence runs on the setup timeframe's own MAs. The execute timeframe may be used to find a pullback entry. Stop and targets stay on the setup timeframe.** Matches `SCALP @ 05:42`. | §9, §5.4.3 |
| **D-8** | HCOM/LCOM lookback | **Three months** — what the Stoic indicator supplies. | §7.3 |
| **D-9** | Mechanical no-edge zone | **Deferred**; where there is no entry, the offline SLM proposes candidates for human confirmation. Never in the live path (`VISION.md`). | §7.4 |
| **D-10** | Stop placement / minimum R | **Stop = PTB low/high**, per `PTBQ` §2. Minimum R left open — see **O-10**. | §5.4.1 |
| **D-11** | Anticipatory inside-bar entry | **Out of scope for v1 signal emission.** Recorded for Phase 3 labelling only. | §5.5 |

**D-1 carries a discrepancy that needs the human.** The register answer also said *"20/200 are
potential targets … or could be a strong confluence."* The corpus says **50/200** in that role
(`SCALP @ 22:45`: *"from 10 20 back to 50, from 50 to 200"*; `M1 @ 20:09`), while the **20/200** pair
belongs to the older free-training session-bias layer (`OTV @ 44:39`, §7.2). Written here as 50/200
per *"derive from material"*. Confirm or correct — see §12 row **O-11**.

---

## 12. Open — not yet pinned

Nothing in this section may be silently chosen by an implementation. Each row says what breaks
without it.

| ID | Open question | Where it bites | Blocking? |
|---|---|---|---|
| **O-1** | The **"three-bar window"** in `PTBQ` §1 is named but never defined. Is the pullback capped at 3 bars? Is the window measured from the Step 3 High? | §5.3.3 — decides which bar's extreme is the trigger | **Yes** for L3 |
| **O-2** | **Entry buffers, gap handling, fill rules** — the source says these *"are not yet locked."* | §5.3 — decides fill price in replay | **Yes** for L3 and Phase 6 |
| **O-3** | The **reset rule** (§2.4.3) says "the moving averages" without naming the pair. `DISC` §1 mentions 10, 20, 50 and 200 in one breath; `SCALP @ 26:26` narrates the reset against the 10/20 while using the 50 for context. | §2.4 — decides when a count dies | **Yes** for L2 |
| **O-4** | When is the **Step 3 High/Low final** in live time? The diagrams fix it in hindsight; no source gives a live rule. | §3, §5.4.4, §6.1 | **Yes** for L2/L3 |
| **O-5** | **"Sufficient room must remain to the Step 3 High/Low"** — condition stated, no number. | §5.4.4 — gates entry | **Yes** for L4 |
| **O-6** | The **fib anchor**: is the Step 3 pullback the same swing as the *"first pullback after reversal"* that `OTV` measures? `SCALP` measures *"the first lower high."* | §6.3 — decides where 2.618 lands | **Yes** for TP2 |
| **O-7** | **Ordering and partial sizing** when the Step 3 High/Low and 2.618 are not in the expected order. | §6.1, §6.2 | No — TP1 alone is well defined |
| **O-8** | **"Staying above/below the 50"** — no bar count, no tolerance, no rule for price straddling it. | §7.1.2 — the primary gate | **Yes** for L4 |
| **O-9** | The **no-edge zone** is a list of situations, not a condition. §7.4.4 mechanises three of them; the rest are open. | §7.4 | No — the rest are filters, not signals |
| **O-10** | **Minimum R** for a setup to deserve risk. Taught as a principle with no number (`CMD` §4). Observed values (§7.5.3) are expectations, not thresholds. | §7.5 | No — record R, do not gate on it |
| **O-11** | **D-1 discrepancy**: 20/200 vs 50/200 in the "MAs as staged targets / confluence" role. | §7.1.5, §11 | No — the sequence pair is settled |
| **O-12** | Whether a **continuation entry** (§2.5) needs its own Step 3 High before its PTB, or reuses the original. | §2.5, §3 | **Yes** for the continuation signal class |

**O-1 through O-6, O-8 and O-12 must close before Phase 5 writes L2/L3/L4.** They are the reason
Phase 2 exists.

---

## 13. Deliberately out of scope

The corpus contains a **second, separate system** — "Simple Stoic Setups" (`SSS`), the "HTF Stoic
Trader Protocol" (`HTF`), "Candle Swing Theory" (`CST`) and the weekly cycle war map (`WM`). It is
built on daily/weekly/monthly **closes**, a **three-day cycle** with five named templates, **signal
days** (three higher/lower closes, first red/green day, inside day), and an **MA chop zone** using
the 20/200 SMA on the 5m for entry timing.

It is a coherent system and it shares vocabulary with this one — consolidation → expansion, trapped
traders, break & retest, SFP, SBS, fib geometry, the same daily and monthly levels. **It is not the
1-2-3 sequence and its rules are not imported here.** `M1 @ 01:06` sets the precedence: the Stoic
Edge System course is the current operating version, and *"if an older lesson conflicts with the
rule taught here, follow this course."*

Concretely, the following do **not** bind any rule in §1–§9: the three-day cycle and its day 1/2/3
roles; the five templates; signal days; the MA chop zone as an entry trigger; the 6am/10am/2pm
rotation windows; the *"no chop zone, no trade"* rule; the measured-move target; the monthly
bias-by-higher-highs filter; the weekly Monday-range map.

Two things from that system are cited above and only for the reason given:

- `CST @ 04:49` — why the **daily** close is the only close the material treats as real (§7.3).
- `CST @ 22:22` — the one mechanical phrasing of the no-edge zone found anywhere (§7.4.3).

Also out of scope, from `VISION.md` and `CLAUDE.md`: any LLM or SLM in the path that decides a
trade; any parameter grid search for the best value of an open row above.
