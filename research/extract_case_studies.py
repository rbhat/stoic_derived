"""Seed case-study fixtures from the Vol 1-7 setup PDFs.

This module extracts only what the PDF *proves*: the embedded text layer (page titles
carrying instrument, date and the instructor's own day classification) plus a SHA-256
digest of the source asset. Nothing here reads the chart imagery, and nothing here
invents a price.

Chart-derived numbers (levels, pivots, entry/stop/target) are added in a later,
human-verified pass. Until a reviewer signs a fixture off, `review.status` stays
``unverified`` and downstream code must not consume it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

CASE_STUDY_ROOT = Path("edu/resources/case_studies")

# Instruments the v1 scope can validate against price data (VISION: NQ and ES only).
IN_SCOPE_INSTRUMENTS = frozenset({"NQ", "ES"})

# Leading instrument token, e.g. "NQ Feb 4th ...", "GBP/JPY Apr 16th ...".
_INSTRUMENT_RE = re.compile(r"^\s*([A-Z]{2,3}(?:/[A-Z]{3})?)\b")

# "Feb 4th", "Jan 30th,", "April 30th" -- optional ordinal suffix, optional comma.
_DATE_RE = re.compile(
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?\b",
    re.IGNORECASE,
)

_YEAR_RE = re.compile(r"\b(20\d{2})\b")

# Parenthetical classification, e.g. "(First Red Day)", "(First Red Day, Inside Day)".
_PAREN_RE = re.compile(r"\(([^)]*)\)")

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# The instructor's day-classification vocabulary, normalised to stable slugs. These are
# claims made by the material about a session; several are pure daily-bar arithmetic and
# are therefore directly checkable against price data.
_CLASSIFICATION_SLUGS = {
    "consolidation → expansion": "consolidation_to_expansion",
    "consolidation -> expansion": "consolidation_to_expansion",
    "3rd day reversal": "third_day_reversal",
    "first red day": "first_red_day",
    "first green day": "first_green_day",
    "inside day": "inside_day",
    "double inside day": "double_inside_day",
    "continuation": "continuation",
    "b&r continuation": "break_and_retest_continuation",
    "sfp reversal": "sfp_reversal",
    "lcom retest + sfp": "lcom_retest_plus_sfp",
    "thursdays": "thursday_study",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class PageRecord:
    """One PDF page, parsed from its text layer only."""

    volume: str
    page: int
    title: str
    extra_text: list[str] = field(default_factory=list)
    instrument: str | None = None
    session_date: dt.date | None = None
    classifications: list[str] = field(default_factory=list)
    unmapped_classifications: list[str] = field(default_factory=list)
    kind: str = "overview"


def _parse_classifications(title: str) -> tuple[list[str], list[str]]:
    """Return (mapped slugs, raw phrases that had no slug)."""
    mapped: list[str] = []
    unmapped: list[str] = []
    for group in _PAREN_RE.findall(title):
        for phrase in group.split(","):
            key = phrase.strip().lower()
            if not key:
                continue
            slug = _CLASSIFICATION_SLUGS.get(key)
            if slug is None:
                unmapped.append(phrase.strip())
            else:
                mapped.append(slug)
    return mapped, unmapped


def _is_date_range(title: str) -> bool:
    """Detect spans like 'Feb-Apr 2026' or 'Apr 15-16, 2026' -- not a single session."""
    if re.search(r"\b\d{1,2}\s*-\s*\d{1,2}\b", title):
        return True
    months = "|".join(_MONTHS)
    dash = "[-\u2013]"  # hyphen-minus or en dash
    return bool(re.search(rf"\b({months})[a-z]*\s*{dash}\s*({months})", title, re.IGNORECASE))


def parse_page(volume: str, page_no: int, raw_text: str, fallback_year: int | None) -> PageRecord:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    title = lines[0] if lines else ""
    record = PageRecord(volume=volume, page=page_no, title=title, extra_text=lines[1:])

    instrument_match = _INSTRUMENT_RE.match(title)
    if instrument_match:
        record.instrument = instrument_match.group(1)

    record.classifications, record.unmapped_classifications = _parse_classifications(title)

    if _is_date_range(title):
        record.kind = "overview"
        return record

    date_match = _DATE_RE.search(title)
    if not date_match:
        record.kind = "overview"
        return record

    year_match = _YEAR_RE.search(title)
    year = int(year_match.group(1)) if year_match else fallback_year
    if year is None:
        record.kind = "undated"
        return record

    month = _MONTHS[date_match.group(1)[:3].lower()]
    day = int(date_match.group(2))
    try:
        record.session_date = dt.date(year, month, day)
    except ValueError:
        record.kind = "undated"
        return record

    record.kind = "session"
    return record


def _volume_fallback_year(texts: list[str]) -> int | None:
    """Volume cover pages carry the year that dated pages sometimes omit (e.g. vol2)."""
    for text in texts:
        match = _YEAR_RE.search(text)
        if match:
            return int(match.group(1))
    return None


def parse_pdf(pdf_path: Path) -> tuple[list[PageRecord], str]:
    volume = pdf_path.parent.name
    document = pymupdf.open(pdf_path)
    try:
        texts = [page.get_text() for page in document]
    finally:
        document.close()

    fallback_year = _volume_fallback_year(texts)
    records = [
        parse_page(volume, index, text, fallback_year) for index, text in enumerate(texts, start=1)
    ]
    return records, sha256_file(pdf_path)


def fixture_id(record: PageRecord) -> str:
    instrument = (record.instrument or "unknown").replace("/", "").lower()
    date_part = record.session_date.isoformat() if record.session_date else "undated"
    return f"cs-{record.volume}-p{record.page:02d}-{instrument}-{date_part}"


def build_index(root: Path = CASE_STUDY_ROOT) -> dict:
    pdfs = sorted(root.glob("vol*/*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"no case-study PDFs under {root}")

    sources: list[dict] = []
    fixtures: list[dict] = []
    skipped: list[dict] = []

    for pdf_path in pdfs:
        records, digest = parse_pdf(pdf_path)
        sources.append(
            {
                "volume": records[0].volume,
                "asset_path": pdf_path.as_posix(),
                "asset_sha256": digest,
                "pages": len(records),
            }
        )
        for record in records:
            common = {
                "volume": record.volume,
                "page": record.page,
                "page_title": record.title,
                "kind": record.kind,
            }
            if record.kind != "session":
                skipped.append(common)
                continue

            fixtures.append(
                {
                    "id": fixture_id(record),
                    "source": {
                        "asset_path": pdf_path.as_posix(),
                        "asset_sha256": digest,
                        "page": record.page,
                        "page_title": record.title,
                    },
                    "instrument": record.instrument,
                    "session_date": record.session_date.isoformat(),
                    "weekday": record.session_date.strftime("%A"),
                    "day_classifications": record.classifications,
                    "unmapped_classifications": record.unmapped_classifications,
                    "annotations": record.extra_text,
                    "in_v1_scope": record.instrument in IN_SCOPE_INSTRUMENTS,
                    "chart_extraction": None,
                    "review": {"status": "unverified", "reviewer": None, "reviewed_utc": None},
                }
            )

    return {
        "schema_version": 1,
        "generated_utc": dt.datetime.now(dt.UTC).isoformat(),
        "provenance": "PDF text layer + SHA-256 only; no chart imagery was read",
        "sources": sources,
        "fixtures": fixtures,
        "skipped_pages": skipped,
    }


def summarise(index: dict) -> str:
    fixtures = index["fixtures"]
    in_scope = [f for f in fixtures if f["in_v1_scope"]]
    lines = [
        f"sources        : {len(index['sources'])} PDFs",
        f"session pages  : {len(fixtures)}",
        f"  in v1 scope  : {len(in_scope)} (NQ/ES)",
        f"  out of scope : {len(fixtures) - len(in_scope)}",
        f"skipped pages  : {len(index['skipped_pages'])} (overview / undated)",
        "",
        "by instrument:",
    ]
    counts: dict[str, int] = {}
    for fixture in fixtures:
        counts[fixture["instrument"] or "?"] = counts.get(fixture["instrument"] or "?", 0) + 1
    for instrument, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        scope = "in-scope" if instrument in IN_SCOPE_INSTRUMENTS else ""
        lines.append(f"  {instrument:<8} {count:>3}  {scope}")

    lines += ["", "day classifications:"]
    class_counts: dict[str, int] = {}
    for fixture in fixtures:
        for slug in fixture["day_classifications"]:
            class_counts[slug] = class_counts.get(slug, 0) + 1
    for slug, count in sorted(class_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"  {slug:<32} {count:>3}")

    unmapped = sorted(
        {phrase for fixture in fixtures for phrase in fixture["unmapped_classifications"]}
    )
    if unmapped:
        lines += ["", f"UNMAPPED classification phrases ({len(unmapped)}):"]
        lines += [f"  {phrase!r}" for phrase in unmapped]

    dated = [f["session_date"] for f in in_scope]
    if dated:
        lines += ["", f"in-scope date span: {min(dated)} .. {max(dated)}"]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=CASE_STUDY_ROOT)
    parser.add_argument("--out", type=Path, help="write the index as JSON to this path")
    args = parser.parse_args()

    index = build_index(args.root)
    print(summarise(index))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
