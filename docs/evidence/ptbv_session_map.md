# `PTBV` is two sessions, not one — measured 2026-08-10

**`docs/PHASE3.md` §3 scopes Phase 3 as the §10 marked charts "plus `PTBV`'s full 2026-07-30
session". That is half the video.** `PTBV` (`edu/derived/concept_ptb_entries_nq_live_trading_10r`,
01:37:54) is a cut of **two** trading days, and the second one is **`T1`/`T2`'s session narrated
live**.

`docs/evidence/fixture_dating.md` is not wrong — its row is scoped `PTBV (kf 0399)` and dates that
one keyframe correctly. What was wrong is the generalisation from it to the whole video.

## What was measured

The artifact, not our own output: TradingView's wall clock in the bottom bar of each keyframe.
Its x-position **shifts with the right-hand order panel**, so a fixed crop misses it — an earlier
pass of this same measurement read two frames as "clockless" when both in fact print a clock.
Scan `x ∈ [1100, 1900]`, `y ∈ [1032, 1062]`.

| video | wall clock (ET) | session | what the frame shows |
|---|---|---|---|
| 00:05:01 | 09:31:07 AM | 2026-07-30 | |
| 00:15:01 | 09:49:41 AM | 2026-07-30 | |
| 00:25:00 | 10:20:06 AM | 2026-07-30 | |
| 00:34:58 | 10:44:27 AM | 2026-07-30 | |
| 00:44:58 | 01:21:17 PM | 2026-07-30 | |
| 00:53:26 | 03:14:52 PM | 2026-07-30 | kf 0399 — `fixture_dating.md`'s row |
| 01:01:41 | 03:33:42 PM | 2026-07-30 | |
| 01:04:57 | **04:06:53 PM** | 2026-07-30 | `13 Sell Stop`, `+1,874.00 USD` — `LT34-A1` open |
| 01:06:41 | **09:27:07 AM** | 2026-07-31 | daily chart, pre-market |
| 01:08:22 | 09:30:55 AM | 2026-07-31 | |
| 01:10:02 | 10:03:03 AM | 2026-07-31 | `13 @ 28244.42`, `13 @ 28417.50`, `+4.5R` |
| 01:19:57 | 11:13:38 AM | 2026-07-31 | |
| 01:29:51 | 11:42:01 AM | 2026-07-31 | |
| 01:37:49 | **01:44:11 PM** | 2026-07-31 | the `T1`/`T2` chart, six executions |

**The seam is between video 01:04:57 and 01:06:41**, where the clock jumps **backward** from
16:06:53 to 09:27:07. TradingView's bottom-bar clock is wall time and cannot run backwards, so the
recording is a cut, not one take.

## Which days, read off the charts

- **Segment 1 = 2026-07-30.** Crosshair label `Thu 30 Jul '26` (kf 0399), and the frame carries
  `6 @ 27896.25`, `6 @ 28125.25`, `8 @ 28114.50`, `8 @ 28117.25` and the `BE` text — the three
  executions already labelled as `LT34-M1`, `LT34-M2` and `LT34-A1` in
  `docs/evidence/labels/2026-07-30_LT3_LT4.yaml`.
- **Segment 2 = 2026-07-31.** Crosshair label `Fri 31 Jul '26`, x-axis day separator `31`
  (kf 0532), and the final keyframe is the `T1`/`T2` chart itself: two counts, two `ptb` levels,
  and the six executions §10.8 lists — `9 @ 28286.67` (`−1R`), `7 @ 28231.75`, `7 @ 28301.75`,
  `9 @ 28232.25`, `12 @ 28350.92` (`+1R`), `12 @ 28454.50` (`+2.5R`).

## Consequences for Phase 3

1. **The double-count set is larger than the one `2026-07-30_LT3_LT4.yaml` warns about.** That
   file's `double_count_warning` names `LT34-A1`/`M1`/`M2`. Segment 2 adds **`T1`/`T2`'s three
   `taken` labels** (`docs/evidence/labels/2026-07-31_T1_T2.yaml`). A `PTBV` execution must be
   reconciled against **both** files before it becomes a new id — `docs/PHASE3.md` §3, the
   `DIA-P` error in `docs/AUDIT-2a.md` F-1.
2. **`PTBV`'s labels split across the two existing session files**, since `docs/PHASE3.md` §2 puts
   one YAML per session. `PTBV` gets no file of its own.
3. **Segment 1 reaches 16:06 ET, past `LT34-A1`'s 15:55 entry.** The +4.5R entry is inside the
   video, and kf 0485 shows the working `13 Sell Stop` at `+1,874.00 USD`. The 22:15 ET exit is
   not — it falls in the cut.
4. **The final keyframe is 34 seconds before `T2`'s screenshot bar** (13:44:11 against the 13:45
   bar). `PTBV` ends where `T2` begins.

## Video time does not map linearly to wall clock

The cuts are inside the segments too: video 00:34:58 → 00:44:58 is **10 minutes of video across
2h37m of wall clock**. So a narration timestamp **cannot be interpolated onto a bar** — read the
clock from the nearest keyframe instead. Any label placing a narrated setup on a bar must cite the
keyframe it read, not an interpolation.

**A per-keyframe clock table was specified and not built.** The task was dispatched to a subagent
which died on a session limit having written nothing — the fourth instance of
`claude_memories/long-research-tasks-write-incrementally.md`, and the first where the memory
existed and was overridden anyway. The 14 rows above are what is measured; the remaining 673
keyframes are not.

## Reproduce

```
.venv/bin/python - <<'PY'
import cv2, numpy as np, json
from pathlib import Path
base = Path('edu/derived/concept_ptb_entries_nq_live_trading_10r')
kf = json.load(open(base/'keyframes.json'))['keyframes']
for t in (300,900,1500,2100,2700,3206,3700,3900,4000,4100,4202,4800,5400,5869):
    f = min(kf, key=lambda x: abs(x['t']-t))
    im = cv2.imread(str(base/f['file']))
    cv2.imwrite(f"/tmp/clock_{f['index']:04d}.png",
                cv2.resize(im[1032:1062, 1100:1900], None, fx=2, fy=2))
    print(f['index'], f['hms'])
PY
```

Then read the crops. The clock is `HH:MM:SS AM|PM UTC-4`; `UTC-4` is EDT, so UTC = ET + 4h.
