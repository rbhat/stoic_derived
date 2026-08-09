# Rulebook — the 1-2-3 sequence

**The distilled strategy spec. This is the engine's source of truth, not the transcripts.**
Every rule cites the material it comes from. Where the material declines to pin something, this file
says so in the open — it does not invent a number.

**This file states what is true now.** It is not a changelog: closed questions live in §11 as
decisions, not as struck-through rows, and `git log -- docs/RULEBOOK.md` is the history.

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
| `DIA-P` | `edu/123sequence/1-2-3-PTB-Long.svg` — **byte-identical to `DIA-L`** (md5 `5db99292…`), so it is the *same drawing under a third path*, not a second one. Cite it for its labels, never as corroboration of `DIA-L` |
| `IBD` | `edu/123sequence/insidebar.png` (the inside-bar schematic: one parent bar, two inside bars, a breakout bar) |
| `LT` | `edu/123sequence/entry_technique/step-3-livetrade.png` |
| `NQ3` | `edu/123sequence/nq-1-2-3.png` (NQ 5m, bullish, live-marked) |
| `PTBV` | `edu/derived/concept_ptb_entries_nq_live_trading_10r/transcript.md` — by timestamp |
| `TPA` | `edu/derived/concept_navigating_tough_price_action_with_1_2_3_and_ptbs/transcript.md` — by timestamp |
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

1. **`M1` and `PC` govern the sequence.** `M1 @ 00:59` calls the Stoic Edge System course *"the
   current operating version"*, and `M1 @ 01:06` adds *"if an older lesson conflicts with the rule
   taught here, follow this course and the current rulebook."* `PC` is that course's one-slide
   framework (`M1 @ 08:36`).
2. **`ET` + `PTBQ` govern the entry**, which `M1`/`PC` leave at *"Step 3 Break"* (see §5.1).
3. `OTV`, `SCALP`, `MAS` illustrate and add context. They never override 1 or 2.
4. `SSS`, `HTF`, `CST`, `WM` are the **complementary layer the 1-2-3 was distilled from** — see §13.
   They supply context and targets, never a step of the sequence, and they yield on conflict.

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
| 2.3.10 | A boundary that is only **barely swept** is not a Step 3. Worked negative example: *"the step three would be the breakout … but we just barely swept that high … and continues lower."* **The source says *barely swept*, which is about magnitude — it is not a wick-vs-body test.** §2.1.2 carries the wick rule, for Step 1, where `M1` does state it. Read the magnitude as the **J** of §2.1.4: no threshold. | J | `M1 @ 19:18`–`19:46` |

### 2.4 Cancellation and reset

| # | Rule | Status | Source |
|---|---|---|---|
| 2.4.1 | **No Step 3 means no entry.** If price never breaks the base in the direction of Step 1, the pattern stays incomplete. | M | `M1 @ 12:57`, `M1 @ 13:14` |
| 2.4.2 | A **wrong-way break**, a **visibly destroyed base**, or a **clear replacement structure** cancels the pending setup. | J | `M1 @ 13:04` |
| 2.4.3 | **Reset rule.** *"If price keeps breaking through the moving averages, reset the count and start again with Step 1."* The pair is the **10/20** — the same pair that runs the sequence. | M | `DISC` §1; decision **D-15**, §11 |
| 2.4.4 | Worked reset, narrated bar by bar: a bullish count is abandoned when price breaks back below the averages, and a new count 1-2-3 starts there. *"We can reset the count because the price broke above the moving averages but then price break below the moving averages, so we have a new count number one, number two and number three."* | M | `SCALP @ 26:26`–`27:21` |
| 2.4.5 | A bearish 1-2-3 that **fails to move lower and reverses back above the averages** is not confirmed; the reversal itself becomes the new (bullish) count. | M | `DISC` §1 with `Q1.png` |
| 2.4.6 | A reset is also a **prompt to re-read direction**, not only to zero the count: a break back through the 10/20 is the local evidence that the higher-timeframe direction may have flipped. The §7.1 gate is therefore re-evaluated at the reset, not carried over. | M | decision **D-15**, §11 |

**Engine note.** Resets are cheap and expected to be frequent. A reset emits nothing, so an engine
that resets many times in a chop is behaving correctly, not thrashing — see **D-19** and §7.1.7.

### 2.5 Continuation entries — a second signal without a new Step 1

| # | Rule | Status | Source |
|---|---|---|---|
| 2.5.1 | If you miss the initial Step 3, **leave the old break alone**. | M | `M1 @ 15:40` |
| 2.5.2 | While the original directional structure remains active, wait **on the same chart** for a **fresh base and a new break of that base**. | M | `M1 @ 15:45` |
| 2.5.3 | *"On the continuation entries, a new step one is not required. We're simply trading continuation consolidations that retrace to moving averages."* | M | `M1 @ 15:56` |
| 2.5.4 | Observed in the live chart: `LT` labels **two** entries in one move — *"Step 3 Pullbck Entry"* and, lower, a second *"Pullback Entry"*. | — | `LT` |
| 2.5.5 | A continuation entry needs **no new Step 3 and no new Step 1**. The directional state opened by the Confirmed Step 3 is what qualifies it: *"the ptb entry is the retracement into the 10 and 20 sma after the confirm step 3. confirm step 3 is very important because otherwise we're just going to be entering on random pullbacks."* | M | `PTBV @ 00:11:18`, `PTBV @ 00:11:28`; decision **D-21**, §11 |
| 2.5.6 | The state runs **until the reset**, and every pullback inside it is an entry: *"even if you don't enter here let's say you missed this entry and price goes higher higher higher higher and then you have this ptb over here so that would be the entry and you [ride] this until price breaks back below moving averages."* | M | `PTBV @ 00:13:07`, `PTBV @ 00:13:13`, `PTBV @ 00:13:20` |
| 2.5.7 | Same rule stated as the session's whole method: *"after one two three all of these are opportunities to enter again all of these are continuation trades"*; *"after 1 to 3 you're looking for continuations, the retracements into the 10 and 20 SMA."* | M | `PTBV @ 00:16:35`, `PTBV @ 00:16:43`, `PTBV @ 00:52:07`, `PTBV @ 00:52:13` |
| 2.5.8 | The reset that ends the state is the **10/20** break of 2.4 — *"look for this continuation higher as long as the price stays about [above] 10 and 20"* — the same pair **D-15** keys the reset off. | M | `PTBV @ 00:37:03`, `PTBV @ 00:13:20`; decision **D-15**, §11 |

**Engine note.** The state machine holds a *sustained directional state* with exactly one entry
condition (Confirmed Step 3) and one exit condition (the §2.4 reset on the 10/20); nothing between
them re-qualifies it. Every PTB inside it emits a signal, labelled as the continuation class.

---

## 3. Step 3 High / Step 3 Low

| # | Rule | Status | Source |
|---|---|---|---|
| 3.1 | *"Step 3 confirms direction and creates the Step 3 High."* | M | `ET` |
| 3.2 | In `DIA-L` the **Step 3 High** is the extreme of the expansion leg **after** Confirmed Step 3, not the confirming bar itself: Confirmed Step 3 is labelled on the breakout bar, and the Step 3 High line is drawn from the high of a **later** bar (the highest high before the pullback begins). Mirror in `DIA-S` for the **Step 3 Low**. | M | `DIA-L`, `DIA-S` |
| 3.3 | The Step 3 High/Low is the **first target** (§6.1) and the reference for *"sufficient room"* on entry (§5.4). | M | `ET`, `PTBQ` §1 |
| 3.4 | **Live definition.** The Step 3 High is the **running maximum of highs from the Confirmed Step 3 bar onward** (Step 3 Low: running minimum), advancing bar by bar for as long as the expansion continues. | M | decision **D-16**, §11 |
| 3.5 | It **never has to be declared final to trade**. The expansion pauses when a PTB candidate completes; from that bar the PTB governs (§5.2), and the working order rides forward with it. The Step 3 High is **frozen at PTB activation** — its value at the moment the entry fills is the number TP1 uses (§6.1). | M | decision **D-16**, §11 |
| 3.6 | `DIA-P` places the Step 3 High on the **second expansion candle** after Confirmed Step 3 — an instance of 3.4, not a bar count. | M | `DIA-P` |
| 3.7 | **A continuation entry (§2.5) does not get a Step 3 High of its own.** There is one running extreme per directional state; it keeps advancing through the continuation and each entry freezes it at its own PTB activation: *"price makes another high over here … and you wait for the pullback and here's your ptb candle right here and you buy stop, stop loss below the candle."* Two entries in one state therefore use **different numbers from the same series**, not two series. | M | `PTBV @ 00:09:43`, `PTBV @ 00:09:50`, `PTBV @ 00:09:59`; decision **D-21**, §11 |

**Engine note.** The diagrams appear to fix the Step 3 High in hindsight; nothing in the engine needs
them to. Entry is a function of the PTB alone, and the only consumer that needs a *number* — TP1 — is
evaluated at fill time, when the running extreme is known.

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

`PC` says **Entry: Step 3 Break**; `ET` teaches a later trigger — wait for the pullback after the
Step 3 High and enter on the **PTB** break. Both are in the material and they are not the same bar.

**Decision D-4: the PTB break is the entry trigger.** The Step 3 boundary break stays what `M1` makes
it — the event that changes the chart's technical state and opens the opportunity — but the order is
placed off the PTB. `LT` agrees: on a live MNQ 5m short, `Step 2` and `Step 3` are labelled at the
structure while both executed entries are labelled as pullback entries, below Step 3.

The engine emits **one signal per PTB activation**, so one directional state can produce several
(**D-13**, and §2.5). The second is not a scale-in and not a lesser signal.

### 5.2 The pullback and the PTB

| # | Rule | Status | Source |
|---|---|---|---|
| 5.2.1 | The chain is: **Confirmed Step 3 → Step 3 High → Pullback → PTB → Entry.** | M | `ET` |
| 5.2.2 | **PTB (Pullback Trigger Bar)** = *"simply the last candle in that pullback."* | M | `ET`, `HOW` |
| 5.2.3 | Bullish: place a **buy stop above the PTB high**; entry triggers when price trades above it. Bearish: the last candle of the **bounce** is the PTB; place a **sell stop below its low**. | M | `ET` |
| 5.2.3a | The order is a **stop market at the PTB extreme** — the PTB high for a long, the PTB low for a short. No buffer beyond the extreme. | M | decision **D-12**, §11 |
| 5.2.4 | In `DIA-L` the Entry line sits exactly at the PTB bar's **high**, and the next bar trades through it. Mirror in `DIA-S` at the PTB **low**. (`DIA-P` shows the same line, but it **is** `DIA-L` — one drawing, so this rests on the bullish/bearish pair, not on three sources.) | M | `DIA-L`, `DIA-S` |
| 5.2.5 | The pullback **need not reach the moving averages or retest the old base.** *"A shallow pullback can qualify."* | M | `PTBQ` §3 |
| 5.2.6 | The PTB pullback has **no MA-touch and no base-touch requirement** — this is what distinguishes it from Step 2, which does require the visual retest of the 10/20 area. | M | `PTBQ` §3 |
| 5.2.7 | 5.2.6 restated live as a preference, not a gate: *"ideally it will touch the moving averages, that's a nice healthy pullback — sometimes it won't."* Remarks elsewhere in the same session that a pullback is *"a bit early because we never touched the moving averages"* are quality reads on the same permissive rule, not a second condition. | M | `PTBV @ 00:08:47`, `PTBV @ 00:43:43`, `PTBV @ 00:43:50` |
| 5.2.8 | **An inside candle is never a PTB.** *"When it's inside candle you don't want to treat it as ptb."* Restated: *"if it's inside candle ptb I would ignore it… we go down, make lower lows, so we keep tracking the ptb — so the ptb is the last candle."* The pullback simply continues and **the anchor stays where it is** — it does not advance to the inside candle (5.3.5a). | M | `PTBV @ 01:33:01`, `PTBV @ 01:02:29`, `PTBV @ 01:02:39`; `TPA @ 00:17:20`, `TPA @ 00:24:31` |
| 5.2.8a | **What *inside* is measured against: the parent bar** — the nearest preceding bar that is not itself an inside bar. Not the bar immediately to the left. `IBD` labels exactly **one** Parent Bar, draws its reference lines from that bar's high and low, and points a run of **two** Inside Bars at it. Stated the same way for a multi-bar run: *"these are inside candles right, we are trading inside of **this** bearish candle"*, and *"inside candles are part of that previous candle."* | M | `IBD`; `TPA @ 00:02:20`, `TPA @ 00:18:24`, `TPA @ 00:25:58`; decision **D-23**, §11 |

### 5.3 Live activation

Verbatim, `PTBQ` §1:

> After the PTB candidate has closed:
> Bullish: price trades above the latest completed correction bar's high.
> Bearish: price trades below the latest completed correction bar's low.
> The activating bar does not need to close beyond that level. However, it must be the latest
> correction bar within the three-bar window, and sufficient room must remain to the Step 3
> High/Low. **Exact entry buffers, gaps, and fill rules are not yet locked.**

Each term that paragraph leaves open: buffers by **D-12** (none), the three-bar window by **D-17**
(no cap), gaps and fills by **D-22**. *"Correction bar"* is `PTBQ`'s word for the PTB candidate;
**D-23** fixes what qualifies as one and **deliberately leaves *approaching* unquantified** — see
**O-14**, §12.

| # | Rule | Status | Source |
|---|---|---|---|
| 5.3.1 | The PTB candidate must have **closed** before it can be activated. Restated live: *"the PTB entry becomes the break of that high — after the full candle closed though, so keep that in mind."* | M | `PTBQ` §1; `PTBV @ 00:35:47`, `PTBV @ 00:35:52` |
| 5.3.2 | Activation is **trade-through, not close-through**. | M | `PTBQ` §1 |
| 5.3.3 | The activating level must belong to the **latest** completed PTB candidate (`PTBQ`'s *"correction bar"*). | M | `PTBQ` §1 |
| 5.3.3a | **PTB candidate, defined.** A candle **inside the pullback that follows Confirmed Step 3** — the pullback being a structural leg, not a property of the candle. Within it, a candidate may come close to the 10/20, wick into them, or close beyond, and the rule draws no distinction, because a candle *"can open and wick unpredictably."* **What marks the start of that pullback is `O-14` and is not settled.** This row previously read *"a candle approaching the 10/20 SMA"*, which put a structural fact on a single bar — see §12 **O-14**. | J | decision **D-23**, §11; §12 row **O-14**; `ET` |
| 5.3.3b | **The one hard exclusion:** a PTB candidate must **not be an inside candle** (5.2.8, 5.2.8a). | M | decision **D-23**, §11; `IBD` |
| 5.3.3c | **No body test and no lower-high test.** Both mechanical readings were put to the human and **rejected as over-specification**: neither `close < open` nor "makes a lower high" is a condition of this spec. Do not reintroduce either as an implementation convenience. | J | decision **D-23**, §11 |
| 5.3.4 | **There is no bar cap.** The PTB is fixed by **structure, not by count**: it is the last PTB candidate before the move resumes. `PTBQ` §1 states **both** *"it must be the latest correction bar within the three-bar window"* **and** *"The 3 bar window is not defintite but a PTB has 2 sides — the direction, the pull back trigger and the move again going back."* The source contradicts itself; **D-17 is what picks the second reading**, so the citation below names the decision first. | M | decision **D-17**, §11; `PTBQ` §1 (both clauses) |
| 5.3.4a | **What ends the walk.** The order re-anchors candle by candle (5.3.5) until exactly one of two things happens: it **fills**, or the setup is **invalidated without an entry** by any of §5.4.7a–c. There is no third outcome and no timeout — an unfilled order does not expire on bar count. | M | decision **D-17**, §11 |
| 5.3.5 | Therefore the working order **re-anchors every bar**: while the pullback continues, each newly completed PTB candidate becomes the PTB and the resting stop moves to its extreme. The order fires on the first trade beyond the current anchor. Stated live as *"we want to trail behind the PTB"*, and again as *"I'm just following the candles down until we have the candle that's PTB."* Corroborated across a whole session: *"all we're doing is ptb entries and we are trailing behind them."* | M | decision **D-17**, §11; `PTBV @ 00:35:34`, `PTBV @ 01:32:55`, `PTBV @ 01:33:01`; `TPA @ 00:17:50` |
| 5.3.5a | **The trail skips inside candles — it does not move to them.** When the next completed candle is an inside candle, the resting order **stays at the current anchor's extreme**; it does not re-anchor and it is not cancelled. **The trail then resumes at the next non-inside candle**, which becomes the new anchor normally. The pause is **per candle**, not a state the pullback enters: a run of inside candles is skipped one by one, however long the run, and nothing about the trail changes when it ends. | M | decision **D-23**, §11; `PTBV @ 01:33:01`, `TPA @ 00:17:20` |
| 5.3.6 | The schematic shows the mechanism with a **two**-bar pullback: two down candles into the moving averages, the **later** one carries the Entry line at its high. Two, not three — the count is incidental. One drawing, cited under either name. | M | `DIA-L` (= `DIA-P`) |
| 5.3.7 | **Fill price.** The order is a stop market (5.2.3a), so it fills **at the trigger** when the bar trades through it, and **at the bar's open** when the bar **gaps past** it — a market fill, taken at whatever the gap offers. A fill is **never better than the trigger**. | M | decision **D-22**, §11 |
| 5.3.8 | **A level that is never traded is not an entry.** *"This would be the ptb entry — price never triggered it"*, and the read moves on to the next PTB. No chasing, no relaxed level. | M | `PTBV @ 00:12:51` |
| 5.3.9 | Corroborating 5.3.7 live — when price has already left the level, the trade is taken at the price available rather than skipped: *"another entry, thousand dollar stop loss, I gotta do market — this is a ptb entry."* | M | `PTBV @ 00:23:37` |
| 5.3.10 | **R is computed from the actual fill, not from the trigger.** A gap fill sits beyond the trigger (5.3.7) while the stop stays at the opposite PTB extreme (5.4.1), so the gap **widens** R and every ratio built on it. | M | derived from 5.3.7 + 5.4.1 |

**Engine note on 5.3.3a — this is what O-14 blocks.** 5.3.5 re-anchors the resting order to every
newly completed PTB candidate. If *"PTB candidate"* is left to mean any bar, **every** completed bar
re-anchors, the buy stop sits above the last bar's high throughout the expansion, and the next
expansion bar fires an entry — the engine signals on every bar of the run.

**The fix is a layer, not a threshold.** The discriminator is *"is this bar inside a pullback"*, which
is a fact about a **leg**, and legs belong to **L1** (`docs/PLAN.md` Phase 5 — L1 already lists
*consolidation vs expansion*). L3 asks L1 where the expansion ended and then applies `ET`'s actual
definition: the PTB is *"simply the last candle in that pullback"*, minus inside bars (5.2.8, 5.2.8a).
Defining a PTB candidate by its distance to the 10/20 was L3 reaching past a layer that already owned
the concept — the invented predicate Phase 2a exists to remove
(`claude_memories/audit-hard-rules-not-in-material.md`). Until **O-14** closes, **L1 and L3** do not
compile.

**Engine note on 5.3.10.** The signal record stores **both the trigger and the fill**, because on a
gap they differ and only the fill sets R. That is a data-model requirement, not a rule about trades —
it sat in 5.3.10 as if it were one until `docs/AUDIT-2a.md` F-6. The derivation chain is also
one-directional now: 5.3.10 rests on 5.3.7 + 5.4.1, and 5.4.2 on 5.2.3 + 5.4.1 + 5.3.7. The two
previously cited each other.

**Engine note on 5.3.5a.** An inside candle has a lower high than its parent by definition (and a
higher low). Anchoring to it would move a long's buy stop **down, inside the parent's range** — so
price could trigger the entry without ever exceeding the parent's high, which is an entry on a move
that has not resumed. Skipping inside candles keeps the trigger at the last bar that actually made
the extreme. That is the mechanical reason behind *"if it's inside candle ptb I would ignore it."*
Note the asymmetry with 5.3.4a: an inside candle **pauses** the trail, it does not end it — only a
fill or an invalidation does that.

**Engine note on 5.3.7.** The rule is stop-market semantics applied honestly, which is why it needs
no parameter: the gap case is a property of the order type, not a choice about the strategy. One
modelling assumption does ride on it — **no slippage is modelled beyond the gap itself**. That is a
replay convention, not a rule from the material; if Phase 6 finds it flattering, it is the thing to
change, and it must change in one place.

### 5.4 Stop and invalidation

| # | Rule | Status | Source |
|---|---|---|---|
| 5.4.1 | **Stop = the PTB low (long) / PTB high (short).** `PTBQ` §2 answers the question in two words — *"PTB low/high"* — with no long/short labels; the pairing comes from §5.2.3, where the entry sits at the opposite extreme, so the stop takes the other side. | M | `PTBQ` §2; `ET` via §5.2.3 |
| 5.4.2 | Therefore **R = \|fill − PTB extreme\|**, and this is the R in every downstream ratio. *Fill*, not trigger — the two differ on a gap (5.3.7, 5.3.10) and only the fill is real. | M | derived from 5.2.3 + 5.4.1 + 5.3.7 |
| 5.4.3 | When entering off a faster chart, the **stop is set from the slower chart**: *"we could be entering off of the one minute chart but we could be setting stop loss based on the five minute chart, which is whatever the high is gonna put in."* | M | `SCALP @ 05:42`; decision **D-7**, §11 |
| 5.4.4 | **There is no minimum stop distance.** The stop sits at the PTB extreme and nowhere else. A small PTB simply produces a small R — that is the trade the method offers, not a defect to correct. No ATR floor, no swing-extreme fallback, no volatility scaling. | M | decision **D-18**, §11 |
| 5.4.5 | **Break-even.** Once price trades beyond the **Step 3 High (long) / Step 3 Low (short)** in the trade direction, the stop moves to the **fill price**. This is the same event as reaching TP1 (§6.1), which is where `ET` already puts it: *"This is the place to take partials and put stop to break even."* | M | decision **D-25**, §11; `ET` |
| 5.4.6 | *"Sufficient room must remain to the Step 3 High/Low"* — expressible as **TP1 distance ≥ m × R**. The inequality is this file's construction of `PTBQ`'s qualitative condition, not `PTBQ`'s own words (`docs/AUDIT-2a.md` F-8); `m` is unset. | P | `PTBQ` §1; §12 row **O-10** |
| 5.4.7 | **Invalidation is distinct from the stop.** The stop (5.4.1) is a price the order rests at; these are conditions that end the setup whether or not the stop is reached. **Any one of 5.4.7a–c invalidates.** They apply to an **open position and to a pending setup alike** — a working order that has not filled is cancelled by the same three conditions (§5.3.4a). | M | decision **D-24**, §11; decision **D-17**, §11 |
| 5.4.7a | The **confirmed opposite Step 3** (§6.4). | M | `PC`, `M1 @ 23:46` |
| 5.4.7b | A **strong close beyond the 10/20 SMA against the trade direction** — for a long, a strong close below them; mirror for a short. **Strong = the close sits beyond the MA by at least 10% of that candle's own high-low range.** The bare break is already the §2.4.3 reset and the §2.5.8 end of the directional state; what 5.4.7b adds is that it also closes an **open position**. | P | `TPA @ 00:24:48`, `PTBV @ 00:03:28`; decision **D-24**, §11 |
| 5.4.7c | A **close beyond the Step 2 boundary against the trade direction** — for a long, a bar **closing** below the Step 2 consolidation boundary; mirror for a short. **A trade through it is not enough.** That is what separates this from §2.3.1, where a trade through the *same* boundary is exactly what starts Step 3. No strength qualifier either: unlike 5.4.7b, the close alone is the whole test. The boundary is the one already selected under §2.2.8, so no new selection happens here. | M | decision **D-24**, §11 |

**Engine note on 5.4.7.** These are evaluated **per bar on an open position and on a pending setup**,
and they fire before the opposite sequence completes — which is the point: 5.4.7a can be many bars
away. The pending-setup case is what terminates §5.3.4's unbounded re-anchoring: the working order
walks candle by candle until it fills or one of these three cancels it.

**All three are close-based, and that is the shape of the rule, not a coincidence.** 5.4.7a is a
*confirmed* Step 3, which §2.3.4 already defines as a meaningful close; 5.4.7b is a strong close;
5.4.7c is a close. Nothing here exits on a trade-through. An intrabar spike beyond a level does not
end a trade under any of the three — only the stop (5.4.1) does that, and the stop is the only
trade-through that **closes** a position. Two other trade-throughs exist and neither exits: the entry
(§5.3.2) and the break-even trigger (5.4.5), which moves the stop rather than ending the trade.

**5.4.7c is the mirror image of §2.3.1 on the same line.** A trade through the selected boundary
*starts* Step 3 in the direction of Step 1; a **close** beyond it in the opposite direction ends the
trade. Deliberately asymmetric — entry is permissive because the PTB stop bounds the risk, and exit
is strict because a wick through a boundary in a live position is noise.

Two evaluation notes. 5.4.7b's *strong* is **quantified by D-24 at 10% of the candle's range** — it
is the one number in the exit path, and it is a recorded decision, not a reading of the material.
5.4.7c carries no strength qualifier and needs none. 5.4.7c is **M** on the same footing as §2.3.1 —
the *test* is computable, while the *boundary* it tests against is selected under §2.2.5–§2.2.8,
which is **J**. Marking it M follows the convention §2.3.1 already set; it does not mean boundary
selection has been solved.

**One asymmetry left open on purpose:** §2.4.3 resets the count on a bare 10/20 break with no
strength qualifier, while 5.4.7b closes a position only on a close **10% of the candle's range**
beyond. A break that closes less than that therefore resets the count but does not invalidate the
trade. That may be exactly right — a reset emits nothing, an invalidation costs money — but it is an
unreconciled difference between two rules keyed to the same event, not a derived result. Quantifying
*strong* sharpened the gap rather than closing it. See §12 row **O-15**.

**Engine note on 5.4.4 and 5.4.5.** R is fixed once, at fill: `|fill − PTB extreme|`, with no floor
and no adjustment. 5.4.5 then moves the **stop**, not R — a break-even stop does not re-scale the R
already recorded on the signal, and every downstream ratio keeps using the entry R. The signal record
should carry the break-even event, not a second R.

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
| 6.1 | **First target = the Step 3 High (long) / Step 3 Low (short).** *"This is the place to take partials and put stop to break even."* The break-even half of that sentence is the stop rule **§5.4.5** (**D-25**); partial *sizing* is still open (**O-7**). | M | `ET`; decision **D-25**, §11 |
| 6.2 | **Second target = the 2.618 fib extension.** | M | decision **D-6**, §11; measured in `SCALP @ 06:35`; drawn on `LT` and `T1` as `261.80%` |
| 6.3 | Fib geometry is a **measurement** tool for targets, anchored on the pullback: measure the **first pullback** after the reversal with the trend-extension tool; the published extension levels are **2.618, 4.23 and 6.86**. | M | `OTV @ 51:26`, `OTV @ 52:39`, `OTV @ 52:44` |
| 6.3a | **Two different tools, two different jobs.** *Retracement* measures a swing — any swing, descriptively: *"we're using fib retracements to measure the pullbacks."* The *extension* is what produces targets, and it is anchored on **one specific swing**: *"then we use the trend extension tool to measure this very first pullback in order to give us these targets."* | M | `OTV @ 52:08`, `OTV @ 52:33`, `OTV @ 52:39`; decision **D-20**, §11 |
| 6.3b | In 1-2-3 terms the anchor is the **Step 2 swing**. `OTV` enters on the second pullback: *"because we don't know the first pullback might be a fake out, we looking for the second pullback. And once the second pullback occurs, then that's more likely that price actually reversed."* The second pullback is the Step 3 pullback that carries the PTB. First pullback anchors the fib; second pullback carries the entry. The cited span establishes that the second pullback *confirms* the reversal; that it is where **we enter** is stated at `OTV @ 1:07:32` — *"There is the first 100%. This is your second pullback where we enter"* — in a passage that also names 2618 and 423 as first and second target, corroborating **D-20** whole. | M | `OTV @ 52:22`, `OTV @ 52:28`, `OTV @ 1:07:32`; decision **D-20**, §11 |
| 6.3c | `SCALP`'s *"we want to measure the first lower high right so 2618 this is the target"* is the bearish mirror of 6.3b, said **before** the breakdown: the first lower high after the reversal is the Step 2 bounce — a translation into 1-2-3 vocabulary that is **D-20**'s, not `SCALP`'s, which never says *Step 1*, *Step 2* or *bounce* anywhere in this trade's narration. The two sources agree. | M | `SCALP @ 06:35`; decision **D-20**, §11 |
| 6.4 | **Final technical exit = the confirmed opposite Step 3**, for the remaining position. Partials may be taken before it. | M | `PC`, `M1 @ 09:24`, `M1 @ 23:46` |
| 6.5 | Between entry and 6.4, the position is simply held: *"we simply stay with the move until the complete opposite one two three pattern confirms."* | M | `M1 @ 09:24` |
| 6.6 | Climax is a sanctioned management cue (§4.3) — **not the only one.** `M1 @ 16:08` lists four things as *"optional management context"*: the 50/200 SMA, climax conditions, additional entries, and partial profits. Two of those are already rules here (continuation entries §2.5, partials §6.1). What binds is §4.3: none of them creates a signal or changes the technical state. | M | `M1 @ 16:08`, `M1 @ 16:19`, `M1 @ 16:31` |

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
| 7.1.4 | Do not **long** into the 200 SMA on fast charts: *"on one minute chart, five minute chart, do not long into the 200 SMA."* **The material states the bullish case only** — nothing in `SCALP` addresses shorting into the 200 from below. The engine applies it long-only until the mirror is decided; do not assume symmetry here. | M | `SCALP @ 23:02` |
| 7.1.5 | The MAs act as **staged destinations**: *"you can long from 10 20 back to 50, from 50 to 200, and then eventually it flips."* | — | `SCALP @ 22:45` |
| 7.1.6 | **MA target rule.** When an MA is used as a destination, take the **next MA beyond entry in the trade direction**, from the set on the chart (10, 20, 50, 200). Which SMA that is falls out of the geometry — it is not a choice between pairs. | M | decision **D-14**, §11 |

| 7.1.7 | **"Staying above/below" needs no bar count and no tolerance band.** The gate is read on each bar's **close** against the 50. When price straddles the 50, the two sides keep alternating, Step 1 keeps failing its own gate, and the count keeps resetting (§2.4) — in the user's words when settling **D-19**, *"if candles keep sticking up and down the 50, it's choppy … practically it could mean that we count/reset continuously."* **That quotation is the user's, not the material's** — it appears nowhere under `edu/`, and is marked so because every other italic quotation in this file is material. | M | decision **D-19**, §11 |
| 7.1.8 | Therefore **there is no chop detector.** Chop is not a state the engine recognises; it is what continuous count-and-reset looks like from outside. The same holds for price stuck around the 10/20 and the 200. | M | decision **D-19**, §11 |

**Engine note.** Two roles that look like one: *gating* (7.1.2) must be one fixed pair or the engine
is non-deterministic, and `M1 @ 20:09` fixes it at 50/200; *targeting* (7.1.5) needs no pair at all,
since the next MA in the direction of travel is the next destination. Do not reach for a lookback or
a tolerance on 7.1.7 — continuous count-and-reset **is** the chop reading, with no threshold.

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
| 7.4.4 | **One of 7.4.2's instances is mechanical under this rulebook; two are not.** *No clean invalidation* → **is** mechanical: §5.4.1 gives every signal a numeric stop by construction. *No realistic target* → the room condition at **§5.4.6** (not §5.4.4), which is **P** and open on **O-10**. *No trap side* → §7.3's *Trapped side*, which is **J**. An earlier version of this row called all three *"already mechanical"*. | — | derived |

**Open:** the no-edge zone as a whole is taught as a list of situations, not a condition — see §12
row **O-9**.

### 7.5 Does the setup deserve risk

| # | Rule | Status | Source |
|---|---|---|---|
| 7.5.1 | *"The setup has to deserve risk."* A setup name is not enough: it must have context, asymmetrical R:R, invalidation, and a reason to exist. | J | `OTV @ 11:11`, `CMD` §4 |
| 7.5.2 | **No trade is a valid outcome.** Cash is a position. | — | `CMD` §3, `CMD` §8 |
| 7.5.3 | Observed R expectations in the live session: a scalp of 2–3R is *"a good day"*, 4R *"exceptional"*; a day trade held into the close targets ~5R. These are the trader's stated expectations, **not** a minimum-R rule. | — | `SCALP @ 29:32`, `SCALP @ 32:49` |
| 7.5.4 | **No minimum R governs the 1-2-3 entry.** One number does exist in the corpus, in the complementary layer: `SSS @ 53:51` says *"the risk to reward is absolutely ridiculous five to one at minimum."* Read in context it describes the R:R a chop-zone setup **offers** when the target is far and the stop tight — the geometry of that setup, not a gate any setup must clear — so it hands **O-10** no threshold. The earlier phrasing here, *"no minimum R is stated anywhere in the corpus"*, was false. | — | §12 row **O-10**; `SSS @ 53:51` |

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

### 10.3 `DIA-L` / `DIA-S` / `DIA-P` — the schematic, bar by bar

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

**`DIA-P` is not a second drawing — it is this same file at a third path.** `1-2-3-PTB-Long.svg`,
`step-3-pullback-diagram.svg` and `step-1-2-3.svg` all hash to `5db99292…` and `diff` empty. Its
`Step 3 High`, `PTB` and `Entry` labels are real and its Entry line does sit at y = the PTB bar's
high exactly with no offset — so it remains a legitimate citation **for its own content**.

**What it cannot do is corroborate.** This passage previously called that entry line *"the
independent confirmation of D-12"* and concluded *"two independent drawings agreeing bar for bar is
why §3.4 and §5.3.4 could be stated mechanically."* Both sentences were false: agreement between a
file and itself is not evidence. §3.4 and §5.3.4 therefore stand on `DIA-L` and the transcripts
alone, and **whether that carries their M status is open** — see `docs/AUDIT-2a.md` F-1. `DIA-S` is
the only genuinely independent drawing in this set, and it is the bearish mirror.

### 10.4 `M1 @ 17:04`–`21:21` — the narrated chart walkthrough

The clearest sequence-counting example in the corpus, including the **negative** case at
`M1 @ 19:03`–`19:46` where a bullish Step 3 never completes because the boundary is only swept.

### 10.5 `Q1.png` with `DISC` — a bearish count that resets

A bearish 1-2-3 that is **not** confirmed; price reverses, breaks above the 10/20/50/200, retests,
and continues higher — *"that is completed 1-2-3"* in the opposite direction. Fib retracement 0.5 /
0.618 is drawn on the reversal leg.

### 10.6 `SCALP @ 25:59`–`27:21` — reset narrated bar by bar

Cited in full at 2.4.4. The single best source for how the count is abandoned and restarted.

### 10.7 `NQ3` — NQ 5m, bullish, marked on a live chart

The cleanest **single-sequence** fixture in the corpus — one count, one PTB, one entry, all with real
prices. It is **not** the only fully-marked chart and not the first: `T1` (§10.2) and
`stoic_trade2.png` mark the same session with executions, and `stoic_trade2.png` carries two complete
counts. This file previously called `NQ3` *"the first fully-marked example with real prices"*, which
was written before those charts were opened — see `docs/AUDIT-2a.md` F-13. Reading it against the
rules:

| | |
|---|---|
| **1** | Labelled on the impulse bar off the 09:30 low that closes back above the 10/20 |
| **2** | The shallow higher low immediately after it — the base, formed just above the June LCOM level |
| **3** | The large expansion bar at ~10:00, closing well beyond the base |
| **Step 3 High** | The bar after it, ~28,620 |
| **PTB Entry** | Line drawn at **28,600** — the high of the single pullback candle following the expansion |
| **Stop** | **28,540.75**, the PTB low (§5.4.1) — box bottom |
| **Target** | **28,716.75**, the **PDH** — not an MA and not a fib |

Three things it settles by demonstration. **A one-bar pullback is enough** — corroborating **D-17**
directly, since a three-bar window would not have been reached here. **The reward box is drawn to an
external level**, so §6's targets are a floor, not a ceiling: a marked daily level beyond TP1 is a
legitimate destination (§7.3). And the whole sequence completes **inside one hour** on the 5m, which
is the timeframe pairing in §9 behaving as specified.

Two cautions before using it as a fixture. It is **one instance** — `CLAUDE.md`'s small-*n* rule
applies, and nothing about frequency or hit rate follows from it. And the Step 1 label sits on a bar
that is itself the reversal, so it is a weaker illustration of the §7.1 gate than of §2.

---

## 11. Decisions

Places the material genuinely underdetermines, settled by the human and recorded here. These are
**strategy decisions**, not readings of the material.

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
| **D-12** | Entry order type and level | **Stop market at the PTB extreme** — PTB high for a long, PTB low for a short. No buffer. | §5.2.3a |
| **D-13** | Two entries on one move | **Both are valid.** The second exists because the first can be missed. Not a scale-in, not a lesser signal — one signal per PTB activation. | §5.1, §2.5 |
| **D-14** | 20/200 vs 50/200 as destinations | **Both work; the choice is subjective and depends on which is closer when trading to it.** Resolved by separating the roles: **gating stays fixed at 50/200** (`M1 @ 20:09`), **targeting takes the next MA beyond entry in the trade direction** from {10, 20, 50, 200}. | §7.1.2, §7.1.6 |
| **D-15** | Which pair the reset rule keys off | **The 10/20** — the pair that runs the sequence. A break back through them resets the count, and the reset is also a prompt to re-read direction, since higher-timeframe context may have flipped. | §2.4.3, §2.4.6 |
| **D-16** | When the Step 3 High/Low is final | **It never has to be.** It is the running extreme from Confirmed Step 3 onward, and it is **frozen at PTB activation** for TP1. Execution keys off the PTB alone: *"once PTB is in, the order is a stop order placed on the PTB candle's High (long) / low (short)."* | §3.4–§3.6 |
| **D-17** | The "three-bar window" | **There is no bar cap.** `PTBQ` §1 asserts both *"within the three-bar window"* and *"The 3 bar window is not defintite"*; this decision takes the second. The PTB is the last PTB candidate before the move resumes, and the resting order re-anchors to each new one. **The walk ends in exactly one of two ways** — *"we keep going candle by candle till either we hit an entry or it invalidates without an entry"* — so §5.4.7's three conditions cancel a pending order as well as closing an open trade. | §5.3.4–§5.3.6, §5.4.7 |
| **D-18** | Stops too tight on a small PTB | **No floor. The stop is the PTB's opposite extreme and nothing else** — *"stop after entry is the opposite extreme of the PTB."* A small PTB gives a small R; that is the trade the method offers, not a defect to correct. This **replaces** an earlier ATR-floor mechanism (`k × ATR(n)` with a swing-extreme fallback) that had no basis in the material — ATR is never mentioned in the corpus — and whose three unset constants were the open row **O-5**. Removing it closes O-5 and unblocks L4. | §5.4.4 |
| **D-19** | *"Staying above/below the 50"* | **Per-bar close against the 50; no bar count, no tolerance, no chop detector.** Straddling the 50 makes the count reset repeatedly, and that is the correct behaviour — *"we need to wait to start counting a breakout."* | §7.1.7, §7.1.8 |
| **D-20** | The fib anchor | **Retracement measures each swing; the extension has one anchor — the first pullback after the reversal, i.e. the Step 2 swing.** Entry sits on the second pullback (the Step 3 pullback / PTB). | §6.3a–§6.3c |
| **D-21** | Does a continuation entry need its own Step 3 High | **No. It reuses the sequence state, and there is one Step 3 High per state, not one per entry.** The qualifying condition is the *existing* Confirmed Step 3 — *"the ptb entry is the retracement into the 10 and 20 sma after the confirm step 3"* (`PTBV @ 00:11:18`) — and the state runs *"until price breaks back below moving averages"* (`PTBV @ 00:13:20`). §3.4's running extreme keeps advancing, so each continuation PTB freezes a **later value of the same series** (§3.7). | §2.5.5–§2.5.8, §3.7 |
| **D-22** | What a fill is when price **gaps** through the trigger | **Market fill at the bar's open.** The stop-market order (D-12) fills at the trigger when the bar trades through it, and at the open when the bar opens beyond it. Never better than the trigger; R is taken from the fill, not the trigger. Slippage beyond the gap is not modelled — a replay convention, flagged as such in the §5.3.7 engine note. | §5.3.7, §5.3.10 |
| **D-24** | What **invalidates an open trade**, beyond the stop | **Three conditions, any one of which ends the trade:** the confirmed opposite Step 3; a **strong close beyond the 10/20 SMA against the trade direction**; and a **close beyond the Step 2 boundary against the trade direction** (for a long, a bar closing below the Step 2 consolidation boundary — **trading through it is not enough**). The MA condition is corroborated by the material — *"now price is trading below the moving averages so now the bullish sequence invalidated"* (`TPA @ 00:24:48`), *"if we fail here the bullish sequence will be invalidated"* (`PTBV @ 00:03:28`) — but the **Step 2 boundary condition was not found anywhere in the corpus** and is the human's, as is the *strong* qualifier on the MA close. Recorded as a decision on that basis rather than cited. ***Strong* is now quantified: the close must sit beyond the MA by at least 10% of that candle's own high-low range.** That number is the human's, chosen not measured, and it is the only number in the exit path. | §5.4.7–§5.4.7c, and §6.5 which it narrows |
| **D-25** | When the stop moves to break-even | **When price trades beyond the Step 3 High (long) / Step 3 Low (short) in the trade direction** — *"once the price has moved in the direction of the trade and broken past step 3's price, then the stop loss moves to break even."* Break-even is the **fill** price (§5.3.7), not the trigger. This is the same event as reaching TP1, which is where `ET` already puts it: *"This is the place to take partials and put stop to break even."* **Known divergence:** `TPA @ 00:13:00` teaches an *earlier* trigger — break-even once price takes out the PTB, making it a *"confirmed PTB bar"*. This decision takes `ET`'s later trigger; `TPA`'s is recorded here so it is not lost. `BE` is drawn on `stoic_live_trade3.png` / `stoic_live_trade4.png`. | §5.4.5, §6.1 |
| **D-23** | What qualifies a candle as a **PTB** | **A candle after Confirmed Step 3 that is approaching the 10/20 SMA, and is not an inside candle.** Left deliberately unquantified beyond that: it may get close, wick in, or close beyond, and *"the candle can open and wick unpredictably."* Both mechanical readings were considered and **rejected as over-specification** — the **body** test (`close < open`) and the **lower-high** test. They pick different bars on 62.8% of candidates (`.artifacts/ptb_atr_distribution.md`), so neither could be adopted quietly; the human's call is that neither becomes a rule. *Inside* is referenced to the **parent bar** — the nearest preceding bar not itself inside — per `IBD` and *"we are trading inside of this bearish candle"* (`TPA @ 00:02:20`). Formalizing the leg boundary is **O-14**, not a decision. **The exclusion also governs the trail:** an inside candle is skipped, and the resting order **stays at the current anchor** rather than moving to it (§5.3.5a) — *"when we trail the PTB, we don't trail the inside candles."* | §5.2.8a, §5.3.3a–c, §5.3.5, §5.3.5a |

---

## 12. Open — not yet pinned

Nothing in this section may be silently chosen by an implementation. Each row says what breaks
without it.

| ID | Open question | Where it bites | Blocking? |
|---|---|---|---|
| **O-7** | **Ordering and partial sizing** when the Step 3 High/Low and 2.618 are not in the expected order. **Narrowed by D-25:** the stop goes to break-even at the Step 3 High/Low regardless of where 2.618 sits, so only the *partial sizing* half is still open. | §6.1, §6.2 | No — TP1 alone is well defined |
| **O-14** | **Where the post-Step-3 expansion leg ends and the pullback begins.** *Reframed 2026-08-08.* It was *"what does **approaching the 10/20 SMA** mean for a PTB candidate"* — a distance threshold nobody could source. That framing was the bug: `ET` defines the PTB as *"simply the last candle in that pullback"*, so it **presupposes a pullback**, and §5.3.3a substituted an atomic property of one candle for a structural fact about a leg. The structural concept belongs to **L1**, which already lists *consolidation vs expansion*; §5.3.3a reached past it. Asked correctly, this is answerable **from the material** rather than by picking a number — §8's consolidation→expansion model, §2.2's return to the trend area, §4's climax, and the bar-by-bar walkthroughs (`TPA @ 00:23:20`–`00:26:52`, `PTBV`) all describe legs ending. **Phase 4 SLM question**, with those passages attached: propose candidate formalizations for human confirmation, per `VISION.md`. | §5.3.3a and §5.3.5 — which bar the order sits on, therefore entry and stop | **Yes** for L1/L3 |
| **O-15** | **The strength asymmetry between the reset and the invalidation.** §2.4.3 resets the count on a bare 10/20 break; §5.4.7b closes an open position only on a close **≥10% of the candle's range** beyond it (**D-24**). So a break closing less than that resets the count but does not exit the trade. That may be correct — a reset emits nothing, an invalidation costs money — but it is an unreconciled difference between two rules keyed to the same event, and it was noticed rather than decided. Quantifying *strong* made the gap precise instead of closing it. | §2.4.3, §5.4.7b, §2.5.8 | No — both rules are usable; they just may not agree |
| **O-9** | The **no-edge zone** is a list of situations, not a condition. §7.4.4 mechanises three of them; the rest are open. | §7.4 | No — the rest are filters, not signals |
| **O-10** | **Minimum R** for a setup to deserve risk, now also carrying the *"sufficient room to the Step 3 High/Low"* condition (§5.4.6). Taught as a principle with no number (`CMD` §4). Observed values (§7.5.3) are expectations, not thresholds. | §7.5, §5.4.6 | No — record R, do not gate on it |

**Blocking: O-14, and only O-14.** It must close before Phase 5 writes **L3**. **O-5 closed on
2026-08-08** — not by setting its three constants but by **D-18 removing the mechanism that needed
them**, which also unblocks **L4**.

IDs are stable and are never reused: O-1, O-2, O-3, O-4, O-5, O-6, O-8, O-11, O-12 and O-13 closed
into §11 and are not listed here. `git log -- docs/RULEBOOK.md` is the history of this file.

---

## 13. The complementary material

"Simple Stoic Setups" (`SSS`), the "HTF Stoic Trader Protocol" (`HTF`), "Candle Swing Theory"
(`CST`) and the weekly cycle war map (`WM`) teach a **fuller system around the same method**:
daily / weekly / monthly **closes**, a **three-day cycle** with five named templates, **signal days**
(three higher or lower closes, first red or green day, inside day), the **MA chop zone** on the 5m,
and four-hour rotation windows.

**Complementary, not excluded.** `M1 @ 00:59` calls the course *"my latest synthesis of that work"* —
the 1-2-3 is distilled **from** this material, which is why the vocabulary is shared. Read them to
understand *why* a rule in §1–§9 says what it says, and to source the context layer in §7.3–§7.5.

**Two constraints on how they are used.**

1. **Precedence on conflict.** `M1 @ 01:06`: *"if an older lesson conflicts with the rule taught here,
   follow this course and the current rulebook."* §1–§6 wins. The live example is the MA pair (§7.1
   vs §7.2), settled by **D-14**.
2. **Distinguish context from trigger.** A rule from this layer may shape *whether a setup deserves
   risk* (§7.3–§7.5) or *what a realistic target is* (§6). It never becomes a step of the sequence
   and never fires an entry — the sequence and the PTB do that. This matters because rules like
   *"no chop zone, no trade"* or *"the third daily close is the signal"* read like sequence rules
   and are not.

Already carried in: `CST @ 04:49` (why the **daily** close is the only close the material treats as
real, §7.3), `CST @ 22:22` (the one mechanical phrasing of the no-edge zone, §7.4.3), and `OTV`'s
concept layer throughout §7 and §8.

**Not yet carried, and worth a decision later:** the three-day cycle and its templates, signal days,
the chop zone, the rotation windows, the measured-move target, the monthly bias filter, the Monday
range. Each is a candidate confluence input for the §7.5 "deserves risk" question and for the
deterministic confidence score `VISION.md` requires — none is a candidate for §2 or §5.

Genuinely out of scope, from `VISION.md` and `CLAUDE.md`: any LLM or SLM in the path that decides a
trade; any parameter grid search for the best value of an open row above.
