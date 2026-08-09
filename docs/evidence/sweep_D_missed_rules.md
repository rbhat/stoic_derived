# Sweep D — mechanical citation sweep on 11 missed rules

Method: read each rule's text and Source column in `docs/RULEBOOK.md`, retrieved the cited
source verbatim (transcript grep with surrounding context, or read the cited image/file directly),
and judged whether the rule states something the cited source(s) do not. `docs/PLAN.md`,
`docs/STATE.md`, `docs/AUDIT-2a.md`, `claude_memories/`, and `sweep_A/B/C*.md` were not opened.

| Rule | Cited as | Source text actually found (verbatim, or "NOT FOUND") | More specific than source? | Note |
|---|---|---|---|---|
| 5.2.8 | `PTBV @ 01:33:01`, `PTBV @ 01:02:29`, `PTBV @ 01:02:39`; `TPA @ 00:17:20`, `TPA @ 00:24:31` | PTBV 01:02:29–01:02:39: *"so now if it's inside candle ptb i would ignore it i would ignore the inside candle we go down make lower lows so we keep tracking the ptb so the ptb is the last candle"*. PTBV 01:33:01: *"until we have the candle that's ptb when it's inside candle you don't want to treat it as ptb"*. TPA 00:17:20: *"is no ptb entry don't treat the inside candles ignore inside candles"*. TPA 00:24:31: *"this is all inside candles these are not ptbs these inside candles are not entries"*. | NO | Both quotes in the rule are verbatim (modulo trivial tidy-up of filler words) and all four timestamps resolve to on-topic material. The rule's only addition — "the anchor moves on (5.3.5)" — is a cross-reference, not a new claim. |
| 5.2.8a | `IBD`; `TPA @ 00:02:20`, `TPA @ 00:18:24`, `TPA @ 00:25:58`; decision **D-23**, §11 | See deep-check section below. | DECISION | Material (`IBD`, `TPA`) establishes the *concept* (inside bars reference a prior non-inside bar) but only for a 2-bar run; the precise generalized phrasing "the nearest preceding bar that is not itself an inside bar" / "not the bar immediately to the left" is D-23's wording, carried by the cited decision. See deep-check. |
| 5.3.3 | `PTBQ` §1 | `PTBQ` §1, full paragraph: *"After the PTB candidate has closed: Bullish: price trades above the latest completed correction bar's high. Bearish: price trades below the latest completed correction bar's low. The activating bar does not need to close beyond that level. However, it must be the latest correction bar within the three-bar window, and sufficient room must remain to the Step 3 High/Low. Exact entry buffers, gaps, and fill rules are not yet locked."* | NO | The rule is a direct paraphrase of "latest completed correction bar" — no added predicate. |
| 5.3.3a | decision **D-23**, §11; §12 row **O-14** | D-23 (§11): *"A candle after Confirmed Step 3 that is approaching the 10/20 SMA, and is not an inside candle. Left deliberately unquantified beyond that: it may get close, wick in, or close beyond, and 'the candle can open and wick unpredictably.'"* | DECISION | Source column names only a decision and an open row, no material. Recorded as-is per instructions; rule text and D-23 text match almost word for word. |
| 5.3.3b | decision **D-23**, §11; `IBD` | D-23: *"...and is not an inside candle."* `IBD` (image): shows one Parent Bar, a run of two Inside Bars pointed at it, and a Breakout Bar — establishes the inside-candle concept generally, not specifically its exclusion from PTB-candidate status. | DECISION | The exclusion itself is stated by D-23, not spoken by any transcript as an independent "PTB candidate must not be inside" rule (it's assembled from 5.2.8/5.2.8a + the D-23 decision that formalizes PTB-candidate criteria). `IBD` corroborates the underlying inside-bar concept only. |
| 5.3.3c | decision **D-23**, §11 | D-23: *"Both mechanical readings were considered and rejected as over-specification — the body test (close < open) and the lower-high test. They pick different bars on 62.8% of candidates (.artifacts/ptb_atr_distribution.md), so neither could be adopted quietly; the human's call is that neither becomes a rule."* | DECISION | Source column names only the decision. Rule text matches D-23 almost verbatim; correctly recorded as a decision, not checked against `edu/`. |
| 5.3.4 | `PTBQ` §1; decision **D-17**, §11 | See deep-check section below. | DECISION | `PTBQ` §1 itself is internally in tension (states a "three-bar window" requirement, then hedges "not definite"); the firm reading — "no bar cap," "fixed by structure, not by count" — is D-17's resolution of that tension, not something the material states outright. See deep-check. |
| 5.3.5 | decision **D-17**, §11; `PTBV @ 00:35:34`, `PTBV @ 01:32:55`, `PTBV @ 01:33:01`; `TPA @ 00:17:50` | PTBV 00:35:34: *"We want to trail behind the PTB."* PTBV 01:32:55: *"and i'm just following this candles right i'm just keep following the candles down"*; 01:33:01 (cont.): *"until we have the candle that's ptb..."*. TPA 00:17:50: *"...candle all we're doing is ptb entries and we are trailing behind them so the biggest nuance..."*. D-17: *"...the resting order re-anchors to each new one."* | DECISION | All four transcript quotes resolve verbatim and support the *narrative* of trailing/following the PTB down. The precise mechanism — "re-anchors every bar," "the resting stop moves to its extreme," "fires on the first trade beyond the current anchor" — is a formalization carried by D-17 and engine design, not spoken in those exact mechanical terms by any transcript. |
| 5.4.7a | `PC`, `M1 @ 23:46` | `PC` (image) literally labels: *"Final Technical Exit: Confirmed opposite Step 3."* `M1 @ 23:38–23:53`: *"the confirmed opposite step three is the final technical exit for the remaining position you can take partials before it but after the step three in the opposite direction is your sign to exit full position."* | NO | Both sources state this condition directly and by name; the rule is, if anything, less elaborate than `M1`. |
| 5.4.7b | `TPA @ 00:24:48`, `PTBV @ 00:03:28`; decision **D-24**, §11 | TPA 00:24:48: *"now price is trading below the moving averages so now the bullish sequence invalidated."* PTBV 00:03:28: *"and if we fail here the bullish sequence will be invalidated."* D-24: *"...the strong qualifier on the MA close [is] the human's."* | DECISION | Both transcript quotes are verbatim and support a bare MA-break invalidating the sequence, but neither says "strong close" — no strength/body-vs-wick qualifier appears in either quote. D-24 explicitly owns that addition as the human's, which is why the rule cites the decision alongside the material. |
| 5.4.7c | decision **D-24**, §11 | D-24: *"...a close beyond the Step 2 boundary against the trade direction (for a long, a bar closing below the Step 2 consolidation boundary — trading through it is not enough). ... the Step 2 boundary condition was not found anywhere in the corpus and is the human's..."* | DECISION | Source column cites only the decision; per instructions not checked against `edu/` for the verdict — but see the deep-check below, which searched anyway and corroborates D-24's own admission that no source states this. |

## Totals

- **NO:** 3 (5.2.8, 5.3.3, 5.4.7a)
- **YES:** 0
- **DECISION:** 8 (5.2.8a, 5.3.3a, 5.3.3b, 5.3.3c, 5.3.4, 5.3.5, 5.4.7b, 5.4.7c)
- **BROKEN:** 0

No citation failed to resolve. No rule stated a predicate that a cited *material* source contradicted or that wasn't at least traceable to a cited decision — but a majority of the swept rows (8/11) lean on a decision (`D-17`, `D-23`, `D-24`) to carry specificity that the raw transcripts/files alone do not establish. That is consistent with this cluster of rules (PTB-candidate definition, PTB window, and trade invalidation) being exactly where Phase 2a's earlier sweeps found the human doing the most interpretive work.

---

## Deep check: 5.3.4 — "There is no bar cap" / "fixed by structure, not by count"

Full text of `PTBQ` §1 (the entirety of the cited material, `edu/123sequence/concepts/PTB Questions.md` lines 1–5):

> What activates the PTB live?
> After the PTB candidate has closed:
> Bullish: price trades above the latest completed correction bar's high.
> Bearish: price trades below the latest completed correction bar's low.
> The activating bar does not need to close beyond that level. However, **it must be the latest
> correction bar within the three-bar window**, and sufficient room must remain to the Step 3
> High/Low. Exact entry buffers, gaps, and fill rules are not yet locked. **The 3 bar window is not
> defintite but a PTB has 2 sides - the direction, the pull back trigger and the move again going
> back.**

Two things to notice:

1. The paragraph **states a three-bar window as a requirement** ("it must be the latest correction
   bar within the three-bar window") in one sentence, then **hedges it** in the very next sentence
   ("The 3 bar window is not defintite" [sic]). The source is internally in tension, not a clean
   statement of "no cap."
2. The second sentence's actual content is: a PTB "has 2 sides — the direction, the pull back
   trigger and the move again going back." That is a structural description (direction / trigger /
   resumption), but it never says the words "no cap," "structure, not count," or "last PTB candidate
   before the move resumes" — those are 5.3.4's own gloss on the sentence.

Decision **D-17** (§11) is what supplies the firm reading: *"There is no bar cap. 'The 3 bar window
is not defintite but a PTB has 2 sides — the direction, the pull back trigger and the move again
going back.' The PTB is the last PTB candidate before the move resumes; the resting order re-anchors
to each new one."* D-17's own text is quoted in 5.3.4 nearly word for word.

**Verdict: DECISION.** The material alone is ambiguous — it names a three-bar window as a
requirement, then immediately undercuts it, without ever asserting "no cap." The unambiguous "no
bar cap, fixed by structure not by count" reading is D-17's resolution of that tension, and the row
correctly co-cites the decision. Nothing here contradicts D-17; the sweep just confirms the raw
`PTBQ` text by itself would not resolve to "no cap" without the decision.

---

## Deep check: 5.4.7c — Step 2 boundary close-invalidation

Rule 5.4.7c is cited to decision **D-24 only** (no material in the Source column). Per the sweep's
own rules, a pure-decision citation is recorded as `DECISION` without checking `edu/` — but the
rule explicitly asks this one be searched anyway, since D-24 itself claims the condition "was not
found anywhere in the corpus."

Searches run (all under `edu/`, `.md`/`.txt` transcripts and concept files):

- `grep -rniI "boundary" edu/ --include="*.md" --include="*.txt"` → the only hit outside
  auto-generated `keyframes.json` duplicates is `TPA @ 00:45:25`: *"...the higher time frame number
  three is breaking out about the step two boundary that's a trade so as long as the momentum holds
  about the 10 20 sma..."* — this is about **entering** a lower-timeframe trade when a **higher
  timeframe** Step 3 breaks its Step 2 boundary. It is an entry-timing remark, not an exit/
  invalidation condition, and not about the boundary of the *same* trade's own Step 2.
- `grep -rniI "invalidat" edu/ --include="*.md"` → hits in `only_trading_video.md` are generic
  planning rhetoric — e.g. line 118: *"They never define their territory. They never define their
  conditions. They never define what invalidates the trade."* — a rhetorical question about having
  a plan at all, not a stated exit rule. The MA-invalidation quotes used for 5.4.7b (`TPA @
  00:24:48`, `PTBV @ 00:03:28`) are the only concrete invalidation statements found anywhere, and
  they are about the moving averages, not the Step 2 boundary.
- `grep -rniI "step 2" edu/ --include="*.md" | grep -iI "clos\|exit\|invalidat"` → **no hits**.
- `grep -rniI "consolidation" edu/ --include="*.md"` → all hits are in `only_trading_video.md`'s
  general consolidation/expansion market-structure narration (e.g. *"Consolidation leads to
  expansion. That's all you really need."*), none of it tied to a close-based exit test against the
  Step 2 boundary.

**Verdict: DECISION**, and the extra search corroborates D-24's own admission rather than
contradicting it: no source anywhere in `edu/` states "a close beyond the Step 2 boundary against
the trade direction ends the trade." D-24 is honest about this — it explicitly separates the
MA-close condition (which it does corroborate with the two transcript quotes) from the Step 2
boundary condition, flagging only the latter as unfound and human-originated. 5.4.7c inherits
exactly that unfound half.

---

## Deep check: 5.2.8a — the "parent bar" reference

Cited: `IBD` (image); `TPA @ 00:02:20`, `TPA @ 00:18:24`, `TPA @ 00:25:58`; decision **D-23**.

**`IBD`** (`edu/123sequence/insidebar.png`), read directly: shows four candles left to right — a
large red candle labelled **"Parent Bar"**, two small candles (one red, one green) both pointed to
by arrows labelled **"Inside Bars"**, and a larger green candle labelled **"Breakout Bar."** Two
dashed horizontal reference lines run from the **Parent Bar's high and low**, extending across
*both* of the small inside bars to the point where the Breakout Bar clears the upper line. The image
draws exactly **one** Parent Bar and references **both** inside bars to it — not to each other.

**`TPA @ 00:02:20`** (context 00:01:58–00:02:36): *"...it could still work no ptb these are inside
candles right we are trading inside of this bearish candle there is no reason for me to do
anything..."* — matches the rule's first quote.

**`TPA @ 00:18:24`** (context 00:18:10–00:18:31): *"...that's the whole reasoning why not to take
inside candles because inside candles are part of that previous candle really there is no high and
low..."* — matches the rule's second quote.

**`TPA @ 00:25:58`** (context 00:25:50–00:26:09): *"...so inside candles are not ptbs so let's move
this forward this is still all inside previous candle right so this is part of the consolidation..."*
— reinforces "inside candles are not PTBs" and that a run of bars can stay inside the same reference
candle, but does not add a new formulation of the parent-bar rule.

**Assessment.** The sources establish the *concept* solidly — inside bars are referenced to a prior,
non-inside "previous candle" / "parent bar," never to each other — and `IBD`'s two-inside-bar case is
a clean visual proof of exactly that reading for a short run. What none of the three transcript quotes
do is state the fully general, recursive rule in words: *"the nearest preceding bar that is not
itself an inside bar"* and its explicit negative, *"not the bar immediately to the left."* Those two
phrases are D-23's language (§11: *"Inside is referenced to the parent bar — the nearest preceding
bar not itself inside — per IBD and 'we are trading inside of this bearish candle'"*), restated
verbatim in 5.2.8a. The transcripts and the image never test a **3+-bar run of consecutive inside
bars** (which is the case that would actually distinguish "nearest non-inside bar" from "bar
immediately to the left," since with only 2 inside bars both readings happen to agree — the bar
immediately to the left of the *second* inside bar is itself the first inside bar, so a naive
literal-neighbor reading would already break on this exact image, which is presumably why D-23 states
it the way it does).

**Verdict: DECISION.** The core claim is well supported by `IBD` + the transcript quotes for the
cases actually shown; the precise general/recursive phrasing and the explicit "not the bar
immediately to the left" exclusion are D-23's formalization, correctly carried by the co-cited
decision rather than spoken outright by any transcript.
