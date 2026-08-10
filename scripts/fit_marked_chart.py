"""Fit a marked chart's two axes off the artifact, then resolve its marks to bars.

`scripts/date_marked_chart.py` says which *session* a §10 screenshot is. This says which *bar*
every mark on it sits on, which is what a Phase 3 label needs (`docs/PHASE3.md` section 2).

The method reads the artifact, never our own output:

1. **The time axis.** TradingView draws candle bodies in flat, exact colours, so a body mask gives
   the candle columns directly. Their centres fit a comb ``x = phase + spacing * slot`` to within
   a few pixels. The last candle is the in-progress one, and the countdown in the last-price tag
   says how far into it the screenshot was taken — so ``--last-bar`` anchors the whole comb.
2. **The price axis.** With the comb anchored, every slot has a known bar, and a least-squares fit
   of body ends (``max(open, close)`` and ``min(open, close)``) against our bars gives
   ``price = p0 + scale * y``. The residual is the check: on `T1`/`T2` it is 0.9-1.0 points sd over
   120-150 body ends, and the fitted gridlines land on TradingView's own printed axis labels.
3. **The marks.** Execution arrows are two exact colours; their blob centres go through the comb to
   a bar. ``--probe`` walks a pixel column and prices every horizontal line it crosses, which is how
   a drawn `ptb` level, `PLOW` or a plotted moving average is read.

Usage::

    python scripts/fit_marked_chart.py edu/123sequence/stoic_trade2.png --last-bar 2026-07-31T13:45
    python scripts/fit_marked_chart.py <png> --last-bar <ts> --probe 1550 2200

Three things this script is not:

* **Not a labeller.** It resolves marks to bars. Which mark means what is read against
  `docs/RULEBOOK.md` §10 and recorded with its provenance.
* **Not a reader of the count.** The italic 1/2/3 are chart-anchored but hand-placed, and on
  `T1`/`T2` their x-order is not the count order — `docs/CONSTRAINTS.md`. Locating a numeral says
  where the text sits, never which bar it counts.
* **Not tolerant of a wrong ``--last-bar``.** A one-bar error shifts every mark by one bar. The
  price residual has caught it on every fixture so far — `LT4` gives 0.92 pts sd at 22:15 against
  16.9 and 17.4 one bar either side, `LT3` 0.69 against 16.4 and 19.2 — but the fit does absorb
  some of the error, so anchor on the countdown and sweep the neighbours rather than trust one run.

**A session break needs no special handling, and this docstring used to say it did.** The chart
draws no gap for the CME maintenance hour and neither does our 5m frame, which simply holds no bars
between 17:00 and 18:00 ET — so ``last_index - k`` walks across it correctly from either side.
`LT3`/`LT4` spans that break and reported 16.95 points sd for a different reason: **four of its
candles draw no body pixels** — dojis, and candles under the shaded session boxes — and each leaves
a two-slot gap that the old ``span / median_gap`` seed could not see, so the comb searched 134-138
slots when the truth was 139 and the spacing came out 6% long. ``fit_comb`` now seeds the count by
counting the gaps. **The absolute comb residual is not a gate** — `T1` fits cleanly at 10.22 px on
a 39 px spacing — but a residual near *half* the spacing, as `LT4`'s 10.79 px on 22 px was, means
the search never contained the true slot count. The price residual stays the real check.

Colours are TradingView's default light theme as most §10 fixtures were captured. `LT`
(`step-3-livetrade.png`) is a different theme and reports zero candle columns; it needs
`--dump-colours` and new constants. The fit itself is theme-independent.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from stoic.bars import load_bars  # noqa: E402

ET = "America/New_York"

# Exact BGR fills of the default light theme.
BODY_UP = (137, 185, 178)
BODY_DOWN = (158, 203, 228)
ARROW_SELL = (64, 70, 210)
ARROW_BUY = (245, 86, 62)

# Backgrounds and shaded-box tints, so `--probe` can skip them.
BACKGROUND = {
    (222, 249, 252), (208, 235, 238), (194, 223, 224), (182, 211, 212), (190, 217, 219),
    (184, 219, 230), (178, 206, 207), (222, 249, 253), (193, 225, 225), (196, 230, 242),
    (205, 237, 238), (174, 209, 219), (167, 196, 195), (255, 255, 255),
}


def exact(image: np.ndarray, colour: tuple[int, int, int]) -> np.ndarray:
    """Pixels matching `colour` exactly."""
    return np.all(image == np.array(colour, dtype=image.dtype), axis=-1)


def candle_columns(body: np.ndarray, min_width: int = 5) -> list[tuple[int, int]]:
    """Contiguous x-runs carrying body pixels, one per drawn candle."""
    present = body.any(axis=0)
    runs: list[tuple[int, int]] = []
    start = None
    for x, on in enumerate(present):
        if on and start is None:
            start = x
        elif not on and start is not None:
            runs.append((start, x - 1))
            start = None
    if start is not None:
        runs.append((start, len(present) - 1))
    return [r for r in runs if r[1] - r[0] + 1 >= min_width]


def fit_comb(centres: np.ndarray) -> tuple[float, float, float]:
    """Best (spacing, phase, worst residual) for `centres = phase + spacing * slot`.

    Slot assignment and the line fit are alternated to a fixed point. A grid search over
    spacing scored on the worst residual looked simpler and was not: a single stray
    body-coloured blob moves the winner, and a 2 px change in `--xmax` flipped it on `T1`.
    """
    span = float(centres[-1] - centres[0])
    gaps = np.diff(centres)
    step = float(np.median(gaps))
    # Seed the slot count by counting the gaps, NOT by `span / step`: a candle whose body is
    # hidden — a doji, or one drawn under a shaded session box — leaves a two-slot gap, and
    # `span / step` then undercounts by one slot per hidden candle. On `LT4` four are hidden,
    # so the old seed searched 134-138 while the truth was 139 and the fit missed by 6% —
    # a 16.95 pt price residual that was read as a session-break artefact for a day.
    seed = max(1, int(sum(round(g / step) for g in gaps)))
    best: tuple[float, float, float] | None = None
    # Candle centres land on whole pixels, so the spacing is quantised. Seed it off the FULL
    # span for each plausible slot count and keep whichever converges tightest.
    for n in range(max(1, seed - 2), seed + 3):
        spacing, phase = span / n, float(centres[0])
        slots = np.round((centres - phase) / spacing)
        for _ in range(20):
            design = np.vstack([np.ones_like(slots), slots]).T
            coef, *_ = np.linalg.lstsq(design, centres, rcond=None)
            phase, spacing = float(coef[0]), float(coef[1])
            assigned = np.round((centres - phase) / spacing)
            if np.array_equal(assigned, slots):
                break
            slots = assigned
        resid = float(np.abs(centres - (phase + spacing * slots)).max())
        if best is None or resid < best[2]:
            best = (spacing, phase, resid)
    assert best is not None
    return best


def slot_bodies(
    body: np.ndarray, spacing: float, phase: float, xmax: int
) -> dict[int, tuple[int, int]]:
    """Top and bottom pixel of the body drawn in each slot."""
    out: dict[int, tuple[int, int]] = {}
    for slot in range(int((xmax - phase) / spacing) + 1):
        centre = phase + spacing * slot
        x0, x1 = round(centre - spacing / 2 + 3), round(centre + spacing / 2 - 3)
        if x0 < 0 or x1 >= xmax:
            continue
        ys = np.where(body[:, x0 : x1 + 1].any(axis=1))[0]
        if len(ys):
            out[slot] = (int(ys.min()), int(ys.max()))
    return out


def fit_price(
    bodies: dict[int, tuple[int, int]], bars: pd.DataFrame, last_slot: int, last_index: int
) -> tuple[float, float, np.ndarray]:
    """Least squares `price = p0 + scale * y`, trimmed of annotation-colour outliers."""
    ys: list[float] = []
    prices: list[float] = []
    for slot, (top, bottom) in bodies.items():
        i = last_index - (last_slot - slot)
        if i < 0 or i >= len(bars):
            continue
        row = bars.iloc[i]
        ys += [top, bottom]
        prices += [max(row.open, row.close), min(row.open, row.close)]
    y = np.array(ys, float)
    p = np.array(prices, float)
    coef = np.array([0.0, 0.0])
    for _ in range(6):
        design = np.vstack([np.ones_like(y), y]).T
        coef, *_ = np.linalg.lstsq(design, p, rcond=None)
        resid = p - design @ coef
        spread = 1.4826 * np.median(np.abs(resid - np.median(resid)))
        if not spread:
            break
        keep = np.abs(resid - np.median(resid)) < 4 * spread
        if keep.all():
            break
        y, p = y[keep], p[keep]
    return float(coef[0]), float(coef[1]), p - (coef[0] + coef[1] * y)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument(
        "--last-bar",
        required=True,
        help="ET timestamp of the last, in-progress candle, e.g. 2026-07-31T13:45",
    )
    parser.add_argument("--symbol", default="NQ")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument(
        "--xmax", type=int, default=None, help="right edge of the plot area (default: 94%%)"
    )
    parser.add_argument(
        "--probe", type=int, nargs="*", default=[], help="price every line at these x"
    )
    parser.add_argument(
        "--dump-colours", action="store_true", help="print the colour histogram and exit"
    )
    args = parser.parse_args()

    image = cv2.imread(str(args.image))
    if image is None:
        print(f"cannot read {args.image}", file=sys.stderr)
        return 1
    xmax = args.xmax or int(image.shape[1] * 0.94)
    plot = image[:, :xmax]

    if args.dump_colours:
        counts = Counter(map(tuple, plot.reshape(-1, 3)))
        for colour, n in counts.most_common(30):
            print(f"  BGR {tuple(int(v) for v in colour)}  {n:,}")
        return 0

    body = exact(plot, BODY_UP) | exact(plot, BODY_DOWN)
    columns = candle_columns(body)
    if len(columns) < 10:
        print(
            f"only {len(columns)} candle columns found — wrong theme? try --dump-colours",
            file=sys.stderr,
        )
        return 1
    centres = np.array([(a + b) / 2 for a, b in columns])
    spacing, phase, comb_resid = fit_comb(centres)

    bodies = slot_bodies(body, spacing, phase, xmax)
    # The last DETECTED CANDLE, never max(bodies): a stray body-coloured glyph past the live
    # edge would otherwise shift every mark on the chart.
    last_slot = round((centres[-1] - phase) / spacing)

    bars = load_bars(args.symbol, args.timeframe).reset_index()
    bars = bars.assign(et=bars["ts_event"].dt.tz_convert(ET))
    anchor = pd.Timestamp(args.last_bar, tz=ET)
    match = bars.index[bars["et"] == anchor]
    if len(match) != 1:
        print(
            f"--last-bar {anchor} is not a {args.timeframe} bar of {args.symbol}", file=sys.stderr
        )
        return 1
    last_index = int(match[0])

    p0, scale, resid = fit_price(bodies, bars, last_slot, last_index)

    def price_at(y: float) -> float:
        return p0 + scale * y

    def bar_of(slot: float) -> pd.Series:
        return bars.iloc[last_index - (last_slot - round(slot))]

    print(f"{args.image}  {image.shape[1]}x{image.shape[0]}  plot x<{xmax}")
    print(
        f"comb    : spacing {spacing:.3f} px, phase {phase:.2f},"
        f" worst residual {comb_resid:.2f} px"
    )
    print(
        f"anchor  : slot {last_slot} = {anchor:%Y-%m-%d %H:%M} ET"
        f" ({args.symbol} {args.timeframe})"
    )
    print(f"price   : {p0:.3f} {scale:+.5f} * y   [{1 / -scale:.3f} px per point]")
    print(
        f"residual: {len(resid)} body ends, sd {resid.std():.2f} pts,"
        f" max {np.abs(resid).max():.2f} pts"
        "   (chart vs our bars — the fit's only check)"
    )

    print("\nexecution arrows")
    found = False
    for name, colour in (("SELL", ARROW_SELL), ("BUY", ARROW_BUY)):
        mask = exact(plot, colour).astype(np.uint8)
        count, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        seen: set[int] = set()
        for i in range(1, count):
            x, _y, w, _h, area = stats[i]
            if area < 200:
                continue
            slot = float(x + w / 2 - phase) / spacing
            # Right of the live edge there are no bars, only widgets drawn in the same two
            # colours — the open-position P&L pill and the blue/red price-axis tags. `LT3`
            # carries all three.
            if not -0.5 <= slot <= last_slot + 0.5:
                continue
            if round(slot) in seen:
                continue
            seen.add(round(slot))
            row = bar_of(slot)
            found = True
            print(
                f"  {name:4s} slot {slot:6.2f} -> {row.et:%Y-%m-%d %H:%M} ET"
                f"   bar o{row.open} h{row.high} l{row.low} c{row.close}"
            )
    if not found:
        print("  none")

    for x in args.probe:
        print(f"\nlines at x={x} (slot {(x - phase) / spacing:.2f})")
        column = image[:, x]
        y = 0
        while y < len(column):
            colour = tuple(int(v) for v in column[y])
            if colour in BACKGROUND:
                y += 1
                continue
            y0 = y
            while y < len(column) and tuple(int(v) for v in column[y]) == colour:
                y += 1
            if y - y0 >= 2:
                print(f"  y {y0}-{y - 1:<5d} BGR {colour}  price {price_at((y0 + y - 1) / 2):9.2f}")
            if y == y0:
                y += 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
