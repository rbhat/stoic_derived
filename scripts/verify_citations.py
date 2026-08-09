"""Verify every `KEY @ TIMESTAMP` citation in docs/RULEBOOK.md resolves to a real marker.

Two marker dialects:
  transcript.md          **[HH:MM:SS]**  on its own line
  only_trading_video.md  M:SS / MM:SS / H:MM:SS  alone on a line

Negative control: fabricated timestamps must be reported missing. Run with --self-test.

With no arguments it scans docs/RULEBOOK.md — that is the gate, and its count is the baseline
in docs/STATE.md. Pass paths to scan other files instead, e.g. the censuses under docs/evidence/:

    python scripts/verify_citations.py docs/evidence/census_*.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RULEBOOK = REPO / "docs" / "RULEBOOK.md"
D = REPO / "edu" / "derived"

SOURCES = {
    "M1": (D / "concept_stoic_edge_system_module_1_is_live" / "transcript.md", "transcript"),
    "SCALP": (D / "concept_scalping_example_live_trading_session" / "transcript.md", "transcript"),
    "PTBV": (D / "concept_ptb_entries_nq_live_trading_10r" / "transcript.md", "transcript"),
    "TPA": (
        D / "concept_navigating_tough_price_action_with_1_2_3_and_ptbs" / "transcript.md",
        "transcript",
    ),
    "SSS": (D / "concept_simple_stoic_setups_sss" / "transcript.md", "transcript"),
    "HTF": (D / "concept_htf_stoic_trader_protocol" / "transcript.md", "transcript"),
    "CST": (D / "concept_candle_swing_theory_pdh_pdl_pdc" / "transcript.md", "transcript"),
    "MS": (D / "concept_stoic_traders_marker_study" / "transcript.md", "transcript"),
    "OTV": (REPO / "edu" / "123sequence" / "start_here" / "only_trading_video.md", "bare"),
}

CITE = re.compile(r"`([A-Z0-9]+) @ ([0-9:]+)`")
TRANSCRIPT_MARK = re.compile(r"^\*\*\[(\d{2}:\d{2}:\d{2})\]\*\*", re.M)
BARE_MARK = re.compile(r"^(\d{1,2}:\d{2}(?::\d{2})?)\s*$", re.M)


def seconds(ts: str) -> int:
    parts = [int(p) for p in ts.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return h * 3600 + m * 60 + s


def markers(path: Path, dialect: str) -> set[int]:
    text = path.read_text(encoding="utf-8")
    pat = TRANSCRIPT_MARK if dialect == "transcript" else BARE_MARK
    return {seconds(m.group(1)) for m in pat.finditer(text)}


def check(cites: list[tuple[str, str]]) -> list[str]:
    cache: dict[str, set[int]] = {}
    missing = []
    for key, ts in cites:
        if key not in SOURCES:
            missing.append(f"{key} @ {ts}  (unknown citation key)")
            continue
        if key not in cache:
            path, dialect = SOURCES[key]
            if not path.exists():
                missing.append(f"{key} @ {ts}  (source file absent: {path})")
                continue
            cache[key] = markers(path, dialect)
        if seconds(ts) not in cache[key]:
            missing.append(f"{key} @ {ts}")
    return missing


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--self-test"]
    targets = [Path(a).resolve() for a in args] if args else [RULEBOOK]

    cites: list[tuple[str, str]] = []
    for target in targets:
        if not target.exists():
            print(f"target absent: {target}")
            return 1
        cites.extend(CITE.findall(target.read_text(encoding="utf-8")))
    keys = sorted({k for k, _ in cites})
    missing = check(cites)

    scanned = ", ".join(t.relative_to(REPO).as_posix() for t in targets)
    print(f"{len(cites)} citations across {len(keys)} sources: {', '.join(keys)}  [{scanned}]")
    if missing:
        print(f"MISSING ({len(missing)}):")
        for m in missing:
            print(f"  {m}")
    else:
        print("all resolve")

    fake = [("M1", "00:99:99"), ("OTV", "99:99"), ("SCALP", "07:07:07")]
    caught = check(fake)
    ok = len(caught) == len(fake)
    verdict = "PASS" if ok else "FAIL"
    print(f"negative control: {len(caught)}/{len(fake)} fabricated rejected -> {verdict}")

    return 0 if not missing and ok else 1


if __name__ == "__main__":
    sys.exit(main())
