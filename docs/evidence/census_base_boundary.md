# Passage census — the obvious base, and boundary selection

**Term 1: what makes a base "obvious". Term 2: which line of that base gets broken.**

This file enumerates every passage in the corpus bearing on the two **J** terms
`stoic/sequence.py` injects as undecided predicates: `is_obvious_base` (§2.2.5, **D-3**) and
`select_boundary` (§2.2.6–§2.2.9, under the §2.2.8 no-hindsight constraint).

**What this is not.** No threshold, number, predicate or algorithm is proposed here, hedged or
otherwise — see `claude_memories/audit-hard-rules-not-in-material.md`. Nothing below is settled that
the passages do not settle.

## The hindsight test, and how the `Hindsight?` column is assigned

§2.2.8 requires the boundary to be chosen *"while the outcome is still hidden"* — *"a perfect line
discovered after price has moved is hindsight."* So a passage where the line is named **after** the
move is evidence about **drawing**, not about **selection**. Applied literally, this splits the
corpus in a way that matters more than any individual quote:

| Value | Assigned when | What such a passage can support |
|---|---|---|
| `no` | Live narration in which the speaker names the line **before** the break and says what he is waiting for | Selection |
| `yes` | The move has already resolved and the line is named in review | Drawing only |
| `unclear` | **A static chart screenshot.** It shows *that* a line exists, never *when it was drawn* | Neither, on its own |

**Every marked chart in §10 is `unclear` by construction.** This is not a defect in the charts; it is
what a screenshot can carry. The only passages that clear the §2.2.8 bar are the live-narrated ones —
`M1`'s walkthrough, and `SCALP`, `PTBV`, `TPA` where the speaker marks a line and then waits.

---

## Term 1 — what makes a base "obvious"

### Already cited in `docs/RULEBOOK.md`

| Citation | Verbatim quote (or what is drawn) | What it constrains | Quantifies? | Hindsight? |
|---|---|---|---|---|
| `PC` | *"**Step 2:** Return toward the MA trend area and form an obvious base."* (slide text) | Establishes the term. Return **and** base — two conditions | no | no |
| `PC` | *"Retest toward MA trend area and the consolidation base forms"* (annotation on the bearish `2`) | Equates *base* with *consolidation* on the slide itself | no | no |
| `M1 @ 10:49` | *"of that base after step one we wait for price to return toward the trend area represented by the 10"* → `@ 10:57` *"and 20 simple moving average so the question we ask here did price return and form an obvious base"* | The Step 2 question, as a yes/no | no | no |
| `M1 @ 11:06` | *"an exact touch of one or both averages is optional the moving averages help us see the return within"* | The MAs mark an **area**, not a level to hit | no | no |
| `M1 @ 11:22` | *"during that return i want to see an obvious visual base with a boundary i can mark before the break"* | **The core sentence for both terms.** Ties *obvious* and *markable-before-the-break* into one requirement | no | no |
| `PTBQ` §3 | *"Step 2 must visually retest the 10/20 trend area and form a base/consolidation, although it does not need to touch the averages exactly."* | Restates §2.2.2–§2.2.3 in the entry notes, and separates Step 2's requirement from the later PTB pullback, which has **none** | no | no |
| `SCALP @ 00:27:32` | *"don't want to enter on the first pullback into the moving averages we want to wait what price is"* | A pullback is not yet a base | no | no |
| `SCALP @ 00:28:02` | *"consolidation leads to expansion that's all it is as you can see over here we have a breakout"* → `@ 00:28:10` *"about the moving averages we have pullback to the moving averages but this is not enough to enter"* → `@ 00:28:18` *"we need to wait for consolidation and then break about if that doesn't happen price continues lower"* | The clearest statement that **pullback ≠ base**, and that the base is a separate wait | no | no |
| `M1 @ 12:41` | *"before the move sometimes two possible bases will appear select the one that clearly controls the"* | Two bases can coexist; one *"clearly controls"* | no | no |

### Newly found

| Citation | Verbatim quote (or what is drawn) | What it constrains | Quantifies? | Hindsight? |
|---|---|---|---|---|
| `M1 @ 07:08` | *"process can begin again. I use the word consolidation or balance as per auction market"* → `@ 07:23` *"balance is what we can see we can obviously see consolidation and price moves from consolidation"* | **Names the source of the concept: auction market theory's *balance*.** And grounds *obvious* in visibility — *"balance is what we can see"* | no | no |
| `M1 @ 08:52` | *"step two is a visual return toward the moving average trend area followed by an obvious"* | Spoken restatement of `PC`. *"visual"* attaches to the return | no | no |
| `M1 @ 23:23` | *"averages step two is the return towards the moving average area and the formation of an obvious base"* | Closing recap — third verbatim restatement, still no criterion | no | no |
| `M1 @ 21:50` | *"different one consolidation may be tight and obvious another may form around a trend line"* | **Explicitly says bases take more than one form**, and pairs *tight* with *obvious* as one of them — the other being a trend-line shape | no | yes |
| `M1 @ 21:57` | *"a retest may happen quickly or take more time some charts will be too messy to classify cleanly"* | Duration is not a criterion, and **"too messy to classify" is an allowed outcome** | no | yes |
| `M1 @ 20:26` | *"There is a little consolidation."* → `@ 20:29` *"You just wait for the obvious consolidation."* → `@ 20:32` *"There is your obvious consolidation."* | **The single most direct passage on the term.** A *"little consolidation"* is contrasted with *"the obvious consolidation"* on the same chart, moments apart — the distinction is made, and no criterion is given for it | no | yes |
| `M1 @ 17:50` | *"and the three-step system so over here we have break this was a little retest and a base you"* → `@ 17:59` *"can try to enter on this or you wait for the larger retest larger base you can see how the price"* | **A smaller base nested inside a larger one, with the choice left open** — *"you can try to enter on this or you wait"* | no | yes |
| `M1 @ 18:22` | *"retest a little consolidation if you want to wait a little longer there is a bigger consolidation"* | **A second instance of the same nesting**, same permissive phrasing | no | yes |
| `M1 @ 13:04` | *"step one the pattern remains incomplete a wrong way break a visibly destroyed base or a clear"* → `@ 13:14` *"replacement structure cancels depending setup no step 3 means no entry now price trades through"* | Three ways a base **dies**: wrong-way break, *"visibly destroyed"*, *"clear replacement structure"*. All three are judgment terms | no | no |
| `SCALP @ 00:00:19` | *"as you can see we have fallen below the consolidation right so that's the first step"* → `@ 00:00:36` *"there was a clear boundary here clear consolidation we have broken that consolidation"* | *"clear consolidation"* and *"clear boundary"* named together in a live session open | no | yes |
| `SCALP @ 00:26:51` | *"number two consolidation and forming the base below the 50 sma price breaks down but then it"* | Equates *"number two consolidation"* and *"forming the base"* — the two words are interchangeable in live use | no | yes |
| `TPA @ 00:05:27` | *"one as far as the bearish sequence need to see some kind of consolidation here"* | **Live, before the fact:** *"some kind of consolidation"* is the whole requirement as spoken while waiting | no | **no** |
| `TPA @ 00:43:29` | *"see that's like a consolidation the consolidation a bit small but if this is bouncing like this right"* | **A live borderline call.** *"a bit small"* is noted and the base is used anyway | no | **no** |
| `TPA @ 00:37:06` | *"too close right it's way too tight to judge anything so i'm just sitting in this trade"* | **Tightness cutting the other way** — a range can be *"too tight to judge anything"*. The only passage in the corpus where compression is a problem rather than a qualification | no | **no** |
| `TPA @ 00:22:11` | *"technically it is a it's not an obvious number three but we are crashing below number three"* | **A live "not obvious" call — and the trade is discussed anyway.** *Obvious* is treated as a matter of degree, not a gate | no | **no** |
| `PTBV @ 00:12:05` | *"another break up more obvious consolidation and another break up so this is over here is number one"* | ***"more obvious"* — comparative.** Two consolidations on one chart ranked against each other | no | yes |
| `PTBV @ 00:12:15` | *"the breakout about moving averages obvious pullback which is the number two and the number three"* | *"obvious"* attached to the **pullback**, where §2.2.4 and `SCALP @ 00:28:10` say a pullback is not sufficient | no | yes |
| `PTBV @ 00:39:34` | *"retest of the moving averages so over here we had the break right not a obvious break but then we"* | A second live *"not obvious"* call, on a break rather than a base | no | yes |
| `PTBV @ 01:10:18` | *"as a two there's little consolidation and that's number three so i'm looking for the pullback now"* | **A *"little consolidation"* accepted as the number two** — the opposite disposition to `M1 @ 20:29` | no | **no** |
| `PTBV @ 01:12:10` | *"it won't so you have the little consolidation after the number one consolidation plays out"* | Restates the same acceptance | no | yes |
| `SCALP @ 00:26:10` | *"pullback so that's a step two little consolidation breakout step three and it continues higher"* | A third instance of a *"little consolidation"* counted as Step 2 | no | yes |
| `IBD` | **Drawn:** one large red *Parent Bar*, two small *Inside Bars* inside its range, one large green *Breakout Bar*. Two gold **dashed horizontal lines** at the parent bar's **high and low**, extended rightward; the Breakout Bar's body closes above the upper line | The corpus's only schematic of a **line drawn at the extreme of a contained range, extended right, and then broken.** Its subject is the inside bar (§5.2.8a), **not** the Step 2 base — logged as an adjacent drawing convention, not as evidence about bases | no | unclear |

**Same vocabulary in the §13 complementary layer.** `HTF @ 00:37:25` *"thursday as you can see obvious
consolidation you have smaller consolidation over here the first"* — again *obvious* vs *smaller* on
one chart. `SSS @ 00:30:16` *"and this is what we want to see not every consolidation is going to look
the same"*. `SSS @ 00:43:16` *"it's obvious consolidation energy is building and day six it breaks
short at highest close of the"*. `SSS @ 00:44:47` *"tight consolidation that's building energy and a
well-built chop zone can only break one way"*. `SSS @ 01:01:21` *"If the setup isn't obvious, it
doesn't exist."* `CST @ 00:19:46` *"sweep we want to see tight consolidation in here and psychology is
the indecision and the energy"*. Per §13 this layer yields on conflict and never supplies a step of
the sequence — logged as vocabulary, not as evidence on §2.2.5.

### What the material determines

- The base is a **consolidation / balance**, the term taken from auction market theory
  (`M1 @ 07:08`), and *"balance is what we can see"* (`M1 @ 07:23`).
- **A pullback alone is not a base.** Stated at §2.2.4 and independently at `SCALP @ 00:28:10`.
- **An exact MA touch is not required** (`M1 @ 11:06`, `PTBQ` §3).
- **Bases take more than one form** — *"one consolidation may be tight and obvious another may form
  around a trend line"* (`M1 @ 21:50`); *"not every consolidation is going to look the same"*
  (`SSS @ 00:30:16`).
- **Duration is not a criterion** (`M1 @ 21:57`).
- **"Too messy to classify" is a permitted outcome** (`M1 @ 21:57`), consistent with §2.1.4's *pass*.
- **A base can die three ways:** wrong-way break, visible destruction, clear replacement structure
  (`M1 @ 13:04`).

### What it leaves open

- Every magnitude: how tight, how long, how many bars, how many touches. No passage supplies one, and
  **D-3**'s *"range compression, proximity to the MA trend area, no obvious breakouts inside it"* is a
  human decision recorded in §11 with no cut point on any of its three clauses.
- **Whether a "little consolidation" qualifies.** The corpus is *loud and divided* on this:
  `M1 @ 20:29` waits past one for *"the obvious consolidation"*, while `SCALP @ 00:26:10`,
  `PTBV @ 01:10:18` and `PTBV @ 01:12:10` each count a *"little consolidation"* as the number two.
  Same speaker, same word, opposite dispositions. Per
  `claude_memories/audit-hard-rules-not-in-material.md`, rival operationalizations are enumerated and
  put to the human, not chosen here.
- **Which base, when two are nested.** `M1 @ 17:59` and `M1 @ 18:22` both leave it to the trader
  (*"you can try to enter on this or you wait"*), which is not the same instruction as §2.2.9's
  *"select the one that clearly controls the setup"* and *"if two boundaries look equally valid there
  is no clean step three yet"*. See the closing section.
- Whether *obvious* is a gate or a degree. `TPA @ 00:22:11` calls a number three *"not an obvious"*
  one and proceeds; `SSS @ 01:01:21` says *"If the setup isn't obvious, it doesn't exist."*
- Whether tightness can disqualify. `TPA @ 00:37:06` — *"way too tight to judge anything"* — is the
  only passage pointing that way and is about judging a live position, not a base.

### Cited vs new

**9 cited, 22 new** (plus 6 logged §13-layer occurrences). New passages: `M1` ×9, `SCALP` ×3,
`TPA` ×4, `PTBV` ×5, `IBD` ×1. **No passage quantifies. None refuses**, either — unlike §2.1.4, the
material never states that it is declining to quantify a base; it simply does not.

Of the 22 new rows, **9 are `Hindsight? = no`, 1 is `unclear`** (`IBD`) and 12 are review. The 9
split two ways, and the distinction matters: **5 are live calls on a specific chart** — `TPA`
`@ 00:05:27`, `@ 00:43:29`, `@ 00:37:06`, `@ 00:22:11`, and `PTBV @ 01:10:18` (shown in **bold** in
the table) — while the other 4 (`M1 @ 07:08`, `@ 08:52`, `@ 23:23`, `@ 13:04`) are **definitional
statements that are about no particular move at all**, and so cannot be hindsight in the §2.2.8
sense rather than having passed its test.

---

## Term 2 — boundary selection

### Already cited in `docs/RULEBOOK.md`

| Citation | Verbatim quote (or what is drawn) | What it constrains | Quantifies? | Hindsight? |
|---|---|---|---|---|
| `PC` | *"**Step 3:** Break the selected base boundary in the direction of Step 1."* and *"Selected boundary break = Step 3 entry"* | Establishes the term; the boundary is **selected**, and the break is directional | no | no |
| `PC` | **Drawn:** on the bearish sequence a **horizontal** orange line under the base, spanning the `1`/`2` labels; on the bullish sequence an **up-sloping** orange line over the base near the `3` | **§2.2.7's whole basis: a boundary is not necessarily horizontal.** Two lines, two orientations, on one slide | no | unclear |
| `M1 @ 11:22` | *"during that return i want to see an obvious visual base with a boundary i can mark before the break"* | Markable **before** the break | no | no |
| `M1 @ 11:31` | *"clear support resistance or an obvious trend line can define that boundary other consolidation"* → `@ 11:38` *"patterns shapes can qualify without creating another setup system the structure needs to be"* | **The only enumeration of what may serve as a boundary:** clear support/resistance, an obvious trend line, and other shapes — with the explicit caveat that this must not become a second setup system | no | no |
| `M1 @ 11:45` | *"clear enough for us to choose the active boundary while the outcome is still hidden the visible base"* | **The §2.2.8 constraint, stated positively.** Clarity exists *so that* selection can happen blind | no | no |
| `M1 @ 11:54` | *"and the boundary selected before the break are what matter here you can see my clear resistance"* → `@ 12:02` *"boundary displayed as horizontal dashed line i am choosing the active boundary while i still cannot"* | **The only passage in the corpus where the speaker draws a boundary and says so as he draws it.** A horizontal dashed line, chosen blind | no | **no** |
| `M1 @ 12:11` | *"see what happens next a perfect line discovered after price has moved is hindsight price can"* | The prohibition | no | no |
| `M1 @ 12:41` | *"before the move sometimes two possible bases will appear select the one that clearly controls the"* → `@ 12:49` *"setup before the break if two boundaries look equally valid there is no clean step three yet"* | **The tie-break: wait.** Note the sentence moves from *"two possible bases"* to *"two boundaries"* without marking a change of subject | no | no |
| `M1 @ 12:57` | *"this is a perfect time to be patient and wait if price never breaks the base in the direction of"* | Confirms the tie-break is inaction | no | no |
| `M1 @ 13:22` (§2.3.1) | *"the boundary in the direction of step one this is where step 3 begins and the simple question here"* → `@ 13:30` *"is did price break the pre-selected boundary in the direction of step one"* | ***"pre-selected"*** — the §5.4.7c engine note's *"no new selection happens here"* rests on this word | no | no |

### Newly found

| Citation | Verbatim quote (or what is drawn) | What it constrains | Quantifies? | Hindsight? |
|---|---|---|---|---|
| `M1 @ 12:19` | *"always go higher after you sell price can always go lower after you buy we never going to be perfect"* → `@ 12:27` *"but keep in mind that when you're looking at the historical chart you're looking at the perfect"* → `@ 12:33` *"examples and real trading decisions are going to be messier than the hindsight study mark the level"* | **The reason behind §2.2.8, and it is a warning about backtesting specifically** — *"when you're looking at the historical chart you're looking at the perfect examples"*. Bears directly on how any proposed selection rule may be evaluated | no | no |
| `SCALP @ 00:04:49` | *"it's not that bad it's not that bad would like to see some kind of trend line forming like over here"* → `@ 00:04:58` *"this is a nice boundary here this over here it's a nice boundary the short could be taken below this"* → `@ 00:05:06` *"line i think this is a short"* | **The richest live selection passage in the corpus.** The line is named, an alternative is considered (*"this over here"*), and the trade is specified off it — all before any break | no | **no** |
| `SCALP @ 00:05:18` | *"mean it's pretty good it's pretty good see that this is a boundary here clear boundary if we break"* → `@ 00:05:25` *"it that's a short yep see that boundary now it's clear on five minute right so we could be entering"* | ***"now it's clear on five minute"* — clarity is asserted of a boundary on a named timeframe.** The only passage tying boundary clarity to the chart interval, which §1.3 fixes for the sequence | no | **no** |
| `SCALP @ 00:05:57` | *"we have the lower highs and the trend line holds maybe even fake out but when we break the boundary"* → `@ 00:06:06` *"below that's what i want i want a nice breakdown and i'll be shorting this let me see"* | A **sloping** boundary (*"lower highs"*, *"the trend line holds"*) used live, corroborating §2.2.7 from narration rather than from `PC`'s drawing | no | **no** |
| `SCALP @ 00:10:18` | *"consolidation going up without realizing that this is a boundary that price is building and"* → `@ 00:10:26` *"break of this boundary is going to be a nice sell-off and i believe we're going to the june"* | ***"a boundary that price is building"*** — the boundary is described as forming while the base forms, before any break | no | **no** |
| `SCALP @ 00:29:41` | *"good day close your chart walk away come back tomorrow don't force it this is when i say clear"* → `@ 00:29:53` *"boundary you see how that support holding but now it's a higher low you see how the price is forming"* | **An explicit gloss: *"this is when i say clear boundary"*** — pointing at support that is holding, with a higher low forming | no | yes |
| `PTBV @ 00:40:24` | *"pretty good it looks very clean boundary here but I don't really trust it until"* → `@ 00:40:29` *"we can get back about number three and after we can get about number three then"* | **A clean boundary is explicitly not sufficient.** Trust waits for the break — stated live, before it | no | **no** |
| `PTBV @ 00:51:05` | *"but we need to break out of the consolidation so also this trend line over here could be a fake"* → `@ 00:51:15` *"so if we break below the strand line it could be a fake break and go back up so"* | **A correctly-selected boundary can still produce a fake break** — stated of a sloping line, live, before the event | no | **no** |
| `PTBV @ 00:50:56` | *"the number two that's why we're entering after the number three number two is just consolidation"* | Restates why the break of the line, not the base, is the trigger | no | yes |
| `TPA @ 00:45:25` | *"is breaking out about the step two boundary that's a trade so as long as the momentum holds"* | The corpus's only spoken use of the exact phrase ***"step two boundary"*** — the term `docs/RULEBOOK.md` uses throughout §5.4.7c | no | yes |
| `PTBV @ 00:01:13` | *"the bearish sequence here in the war map and uh i have been bearish since we broke this boundary here"* | A boundary named in retrospect on a higher-timeframe map | no | yes |
| `NQ3` | **Drawn:** labels `1`, `2`, `3`; a horizontal line labelled **`PTB Entry`** at 28,600; risk/reward boxes; `PDH` 28,716.75, `Jun LCOM`, `PDC`; a `100.00%` fib line. **No line is drawn on the Step 2 base** | The cleanest single-sequence fixture **draws the entry trigger and not the boundary** | prices are text; label positions are pixels | unclear |
| `T1` | **Drawn:** orange `1`, `2`, `3`; one horizontal level labelled **`ptb`** at ~28,300; `PLOW`, `Jun LCOM`, two `261.80%` lines; execution marks. **No line on the Step 2 base** | Same pattern: the `ptb` trigger is drawn, the boundary is not | `ptb` off pixels (±10); executions are text | unclear |
| `T2` | **Drawn:** two counts (orange, then green), **two** `ptb` levels at ~28,300 and ~28,345, `PLOW`, `Jun LCOM`, `261.80%` / `423.60%`, six executions. **No line on either count's Step 2 base** | The densest fixture, with two complete sequences, draws **zero** boundaries | `ptb` off pixels (±10); executions text | unclear |
| `DIA-L` (= `DIA-P` = `step-1-2-3.svg`, md5 `5db99292…`) | **Drawn:** 15 candles; labels `Step 1`, `Step 2`, `Confirmed Step 3`, `PTB`, `Step 3 High`, `Entry`. Exactly **two** dashed horizontal lines: `Step 3 High` at the 12th bar's high, and `Entry` at the PTB bar's high (y = 229.6 on both, exact). **No boundary line on the Step 2 base** | **The schematic that teaches the sequence never draws the line Step 3 is defined as breaking** | geometry is exact SVG coordinates, not pixels | unclear |
| `DIA-S` (md5 `5329ee2c…`, the only independent drawing) | **Drawn:** the exact bearish mirror — same six labels, two dashed lines (`Step 3 Low`, `Entry`), **no boundary line** | Confirms the omission is systematic, not an oversight in one file | exact SVG coordinates | unclear |
| `LT` | **Drawn:** `Step 1`, `Step 2`, `Step 3` labels; **a horizontal orange line at ~28,700 spanning ~08:10–09:25, labelled `SBS`**, sitting under the Step 2 structure and broken by the 09:30 drop; `Step 3 Pullbck Entry` and `Pullback Entry` callouts; `261.80%`; `PDH`, `PDL`, `PDC`/`LCOM` | **The one marked chart where a line lies across the Step 2 base and is broken at Step 3 — and it is labelled `SBS`, not "boundary"** | line level off pixels (±10) | unclear |
| `LT3` / `LT4` (**one trade, two snapshots**) | **Drawn:** `1`, `2`, `3`; **three separate horizontal levels labelled `sbs` / `SBS` / `sbs`** at ~27,833, ~28,070 and ~28,155, each spanning a different consolidation; an **unlabelled** horizontal line at ~28,246 running ~10:30 AM–03:00 PM that the Step 3 candle breaks upward through; a short `ptb` level at ~28,245; `BE`; `PWC`, `PLOW`, `PDH` | **Three `sbs` lines drawn across three consolidations on one chart.** Whether the unlabelled ~28,246 line is the selected boundary or a prior-swing level cannot be told from the image | all line levels off pixels (±10); entry `13 @ 28,244.42` is text | unclear |
| `Q1.png` with `DISC` | **Drawn:** a red `1` and red `2` with **no red `3`** (the unconfirmed bearish count), then a green `1`, `2`, `3`; fib `0` / `0.5` / `0.618` / `1`; `LCOM`, `PLOW`, a `New York OR` box. **No base boundary line** | The reset fixture draws fibs and levels, **not** a boundary | levels off pixels | unclear |
| `MAS` | **Drawn:** annotations *"10/20 acting as support"*, *"50sma acting as support"*, *"Weekly OR low"*; `Asia OR` / `London OR` boxes. **No 1-2-3 labels, no base, no boundary** | The MA study illustrates the trend area as a **zone of support**, not a line — bears on §2.2.1's *"trend area"*, not on boundary selection | annotations are text | unclear |
| `DISC` §1 | *"For Step 2, price must retest the moving averages and consolidate. Step 3 occurs when price breaks below that consolidation as it is rejected by the moving averages."* | **States Step 3 as the break of *the consolidation*, with no boundary named at all** — the line is elided entirely in the user-facing Q&A | no | yes |

### What the material determines

- The boundary is **selected before the break** and the selection is made blind — `M1 @ 11:22`,
  `@ 11:45`, `@ 12:02`, `@ 12:11`, and *"pre-selected"* at `@ 13:30`. This is the most heavily
  restated constraint in either census.
- **What may serve as one:** clear support/resistance, an obvious trend line, or other consolidation
  shapes — *"without creating another setup system"* (`M1 @ 11:31`–`11:38`). This is a closed
  enumeration in form but an open one in content.
- **It need not be horizontal.** `PC` draws one horizontal and one sloping; `SCALP @ 00:05:57`
  narrates a sloping one live.
- **The tie-break when two look equally valid is to wait** (`M1 @ 12:49`, `@ 12:57`).
- **A clean boundary is not sufficient** (`PTBV @ 00:40:24`) and **can still produce a fake break**
  (`PTBV @ 00:51:05`).
- The §2.2.8 rationale is aimed at **historical study specifically** (`M1 @ 12:27`).

### What it leaves open

- **How to choose the line**, given a base. Every passage says the line must be chosen *early* and
  *clearly*; none says *where*. `M1 @ 11:31`'s enumeration names three categories and no rule for
  picking among them.
- **Which extreme.** No passage in the corpus says the boundary is the high or the low of the base,
  or its close, or a touch count. `IBD` draws lines at a parent bar's high and low, but its subject
  is the inside bar.
- **Whether one base has one boundary or two.** §2.3.1 breaks it in the Step 1 direction; §5.4.7c
  tests a close against it in the opposite direction. Whether that is one line tested twice or two
  lines is never addressed.
- **What `sbs` is doing on the base.** `LT` and `LT3`/`LT4` are the only marked charts with a line
  across a consolidation, and all four such lines carry the `SBS` label — a **separate** concept
  (`HOW`: *"SBS - Swing Breakout Sequence manipulation pattern"*, and §8). Whether the trader's
  boundary and his `sbs` level are the same object cannot be told from the images.
- **How a sloping boundary is anchored** — how many points, and from which bars.

### Cited vs new

**10 cited, 21 new.** New passages: `M1` ×1, `SCALP` ×5, `PTBV` ×4, `TPA` ×1, `DISC` ×1, and **9
image readings**. **No passage quantifies.**

**7 rows clear the §2.2.8 bar as live selection** — `M1 @ 11:54`–`12:02`, four `SCALP` passages
(`@ 00:04:49`, `@ 00:05:18`, `@ 00:05:57`, `@ 00:10:18`) and two `PTBV` (`@ 00:40:24`, `@ 00:51:05`),
shown in **bold** in the tables. A further 9 rows are `no` in the weaker sense of being definitional
statements about no particular move. **Every one of the 10 image rows is `unclear`**, per the test at
the top of this file.

### The enumeration result that matters most

**Of the ten drawings in the corpus, exactly two carry a line lying across a Step 2 base that is
subsequently broken — `LT` and `LT3`/`LT4` — and in both the line is labelled `SBS`, not "boundary".**
`NQ3`, `T1`, `T2`, `Q1.png`, `MAS`, `DIA-L` (with its two byte-identical twins) and `DIA-S` draw
none. The schematic built to teach the sequence, `DIA-L`/`DIA-S`, draws the `Step 3 High` and the
`Entry` — but not the line whose break §2.3.1 defines Step 3 as.

Stated as a count, not a verdict: the term with the **most restated constraint** in the spec is the
term with the **fewest drawn instances** in the material. Per
`claude_memories/coverage-claims-need-enumeration.md` this is reported after opening every image, not
inferred from a search.

---

## Is boundary selection separate from base detection, or does choosing the base determine the line?

The corpus never poses the question. What the passages show:

**Evidence they are one act.**

1. **`M1 @ 12:41`–`12:49` switches nouns mid-sentence.** *"sometimes two possible **bases** will appear
   select the one that clearly controls the setup before the break if two **boundaries** look equally
   valid there is no clean step three yet."* Two *bases* appear; the tie is broken on two
   *boundaries*. No transition is marked. This is §2.2.9, and it is the passage `docs/CONSTRAINTS.md`
   points at for exactly this question.
2. **`M1 @ 11:22` states them as one requirement:** *"an obvious visual base **with** a boundary i can
   mark before the break"* — one clause, joined by *with*. The base is not described as obvious in
   its own right, but as obvious-and-markable.
3. **`M1 @ 11:45`** makes the base's clarity **instrumental to** selection: *"the structure needs to be
   clear enough **for us to choose** the active boundary"*. Clarity is defined by what it enables.
4. **`DISC` §1 elides the line entirely** — *"Step 3 occurs when price breaks below that
   consolidation"*. If choosing the base fixed the line, this phrasing would lose nothing.
5. **`SCALP @ 00:10:18`** — *"this is a boundary that price is building"* — describes the boundary as
   emerging from the same process that builds the consolidation.

**Evidence they are two acts.**

1. **`PC` draws two different orientations over two bases** — horizontal under the bearish base,
   sloping over the bullish one. If the base fixed the line, one construction would serve both.
2. **`M1 @ 11:31` enumerates boundary *types* independently of base types** — support/resistance, a
   trend line, other shapes — and warns against *"creating another setup system"*, a warning that only
   makes sense if choosing among them is a real, separable decision.
3. **`PTBV @ 00:40:24`** separates them explicitly in time: *"it looks very clean boundary here but I
   don't really trust it until we can get back about number three"* — the boundary is assessed as an
   object with its own quality, after the base is already accepted as the number two.
4. **`SCALP @ 00:04:58`** considers **two candidate lines on one base** — *"this is a nice boundary
   here **this over here** it's a nice boundary"* — which is a selection step that base detection has
   not already performed.
5. **`SCALP @ 00:05:25`** makes clarity **timeframe-relative**: *"see that boundary now it's clear on
   five minute"*. The base did not change; the chart did.
6. **The engine already treats them as two.** `stoic/sequence.py` injects `is_obvious_base` and
   `select_boundary` as separate predicates, and §5.4.7c's engine note says the boundary is *"the one
   already selected under §2.2.8, so no new selection happens here"* — which presupposes a selection
   event distinct from base recognition.

**Reported, not settled.** Both readings are directly supported: **5 passages** on one side, **6** on
the other, and they are not independent — the three `SCALP` items on the "two acts" side come from one
continuous 40-second stretch of one session, and points 2 and 3 on the "one act" side are adjacent
sentences in `M1`. **No passage in the corpus addresses the relationship directly**, and the one
passage that comes closest — §2.2.9's `M1 @ 12:41`–`12:49` — is the one that switches between the two
nouns without comment, which is why it can be read either way.

One asymmetry worth recording without resolving it: **§2.2.9's tie-break and `M1 @ 17:59`/`@ 18:22`
give opposite instructions for two candidate bases.** §2.2.9 says *"if two boundaries look equally
valid there is no clean step three yet"* — wait. The two walkthrough passages say *"you can try to
enter on this **or** you wait for the larger retest larger base"* and *"if you want to wait a little
longer there is a bigger consolidation"* — trader's choice. Whether these conflict depends on whether
*two nested bases* is the same situation as *two equally valid boundaries*, which is the question
above.

---

## Coverage

**Read in full:** `M1` (cover to cover); `TPA` (hit regions in full context, plus the §2.2/§2.3
passages end to end); `edu/123sequence/entry_technique/entry_technique_for_1-2-3_sequence.md` (`ET`);
`edu/123sequence/concepts/PTB Questions.md` (`PTBQ`); `stoic_commandments.txt` (`CMD`);
`how_to_use_stoic_concepts.txt` (`HOW`); `Timeframes Guide` (`TFG`);
`edu/123sequence/discussion/discussions.md` (`DISC`); `docs/RULEBOOK.md` §0, §2.2, §2.3, §5.4.7–c,
§10, §11.

**Images opened — all ten drawings in the corpus:** `price_cycle.jpg` (`PC`), `nq-1-2-3.png` (`NQ3`),
`stoic_trade1.png` (`T1`), `stoic_trade2.png` (`T2`), `stoic_ma_study.png` (`MAS`), `insidebar.png`
(`IBD`), `entry_technique/step-3-livetrade.png` (`LT`), `entry_technique/stoic_live_trade3.png`
(`LT3`), `entry_technique/step-3-pullback-diagram.svg` (`DIA-L`, read as source),
`entry_technique/step-3-pullback-bearish-diagram.svg` (`DIA-S`, read as source),
`discussion/Q1.png`. `LT4` is `LT3`'s closed snapshot of **one** trade (§10.9) and is not counted
separately. `1-2-3-PTB-Long.svg` and `step-1-2-3.svg` were **hashed, not re-read** — both are
md5 `5db99292665d2f688ee34531688444ad`, byte-identical to `DIA-L`.

**Searched:** `PTBV`, `SCALP`, `SSS`, `HTF`, `CST`, `MS`, `OTV`. Terms: base, consolidation, range,
box, balance, tight, compression, coil, sideways, chop, boundary, line, trendline, trend line,
support, resistance, level, high/low of the range, draw, mark, breakout, flag, pennant, obvious,
clear, clean.

**Silent on both terms:** `CMD`, `HOW`, `TFG`, `MS`. `ET` and `PTBQ` govern the entry and say nothing
about boundary selection — `ET` begins *"Step 3 confirms direction and creates the Step 3 High,"*
taking the confirmed break as given. Neither *flag* nor *pennant* occurs anywhere in the corpus.

### Checks of `docs/RULEBOOK.md` §10 against the images — recorded, not resolved

1. **§10.3's bar-by-bar reading of `DIA-L` is exact.** All seven steps verified against SVG
   coordinates, including *"the PTB's low lands on the 20 SMA"* — the PTB bar's low and the 20 SMA
   path are both at y = 435.5, and the `Entry` line and the PTB bar's high are both at y = 229.6.
2. **§10.1's reading of `LT` is confirmed**, including *"`SBS` annotated on the same structure"* as
   Step 2.
3. **§10.9's `BE` caution is confirmed** — the `BE` mark sits with the earlier `+2.8R` morning trade,
   not with the 03:00 PM entry.
4. **§10.5's reading of `Q1.png` is confirmed.** Additionally: the bearish count draws **`1` and `2`
   only, with no `3`** — consistent with `DISC`'s *"has not been confirmed"*, though §10.5 does not
   say so.
5. **§10.2 and §10.8 give two prices for what both sections say is the same level.** §10.2 puts
   `T1`'s `ptb` at *"~28,300"*; §10.8 puts `T2`'s bearish `ptb` at *"~28,290"*. §10.8 itself declares
   ±10 points of pixel error, so the two readings are consistent — noted so it is not later read as
   two levels.
6. **Unresolved at available zoom: the orange `1`/`2`/`3` label placement on `T1` and `T2`.** On both
   charts the orange labels do not read left-to-right in count order — the `3` appears earlier on the
   time axis than the `2`. §10.2 and §10.8 both describe them as *"labelled down the leg"*. Label
   anchors in TradingView are offset from the bars they refer to, so this may be placement rather
   than a mislabelling, and it cannot be settled at this resolution. **Same class as the open `T2`
   reading already recorded in `docs/STATE.md`** — worth one pass at full resolution; nothing here
   depends on it.
7. **Not stated anywhere in §10:** that `NQ3`, `T1`, `T2`, `Q1.png`, `DIA-L` and `DIA-S` draw **no
   Step 2 boundary**. §10.7's table for `NQ3` lists `1`, `2`, `3`, Step 3 High, PTB Entry, Stop and
   Target without noting the absence.

### One source-inventory finding

`OTV` (`edu/123sequence/start_here/only_trading_video.md`) and
`edu/derived/concept_the_only_trading_video_that_you_will_ever_need/transcript.md` are **the same
video transcribed twice** — 13,240 vs 13,095 words, identical opening line, timestamps a few seconds
apart. Only the `start_here` copy has a key in §0. Same class as `DIA-P`/`DIA-L`; citing both would
double-count one source. Also recorded in `docs/evidence/census_meaningful.md`. Not acted on here.
