"""Command-line inspection and bounded replay for the SP1 market-data layer."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .aggregate import AggregationSpec, MultiTimeframeAggregator
from .calendar import CmeEquityIndexCalendar, load_calendar_manifest
from .databento import (
    COVERAGE_PRECEDENCE,
    DbnMetadata,
    StoreFactory,
    inspect_dbn,
    iter_historical_trades,
    plan_coverage,
)
from .model import FinalBar, MarketDataIssue, MarketDataValidationError


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def metadata_dict(metadata: DbnMetadata) -> dict[str, object]:
    """Return a deterministic, secret-free metadata projection."""
    return {
        "dataset": metadata.dataset,
        "end_ns": metadata.end_ns,
        "mappings": [
            {
                "end_date": mapping.end_date.isoformat(),
                "instrument_id": mapping.instrument_id,
                "root": mapping.root,
                "start_date": mapping.start_date.isoformat(),
            }
            for mapping in metadata.mappings
        ],
        "path": metadata.path.as_posix(),
        "roots": list(metadata.roots),
        "start_ns": metadata.start_ns,
    }


def inspect_paths(
    paths: Sequence[Path],
    *,
    store_factory: StoreFactory | None = None,
) -> dict[str, object]:
    """Inspect sources and resolve their explicit precedence coverage."""
    if not paths:
        raise MarketDataValidationError("at least one DBN path is required")
    metadata = tuple(inspect_dbn(path, store_factory=store_factory) for path in paths)
    coverage = plan_coverage(metadata)
    return {
        "coverage_precedence": COVERAGE_PRECEDENCE,
        "coverage": [
            {
                "end_ns": item.end_ns,
                "path": item.path.as_posix(),
                "root": item.root,
                "start_ns": item.start_ns,
            }
            for item in coverage
        ],
        "sources": [metadata_dict(item) for item in metadata],
    }


def sample_paths(
    paths: Sequence[Path],
    *,
    record_limit: int,
    store_factory: StoreFactory | None = None,
    calendar: CmeEquityIndexCalendar | None = None,
    calendar_manifest: Path | None = None,
) -> dict[str, object]:
    """Run a bounded historical sample through the production normalization path."""
    if not paths:
        raise MarketDataValidationError("at least one DBN path is required")
    if not isinstance(record_limit, int) or isinstance(record_limit, bool) or record_limit <= 0:
        raise MarketDataValidationError("record_limit must be a positive integer")
    if (calendar is None) == (calendar_manifest is None):
        raise MarketDataValidationError(
            "sample requires exactly one reviewed calendar or calendar manifest"
        )
    metadata = tuple(inspect_dbn(path, store_factory=store_factory) for path in paths)
    coverage = plan_coverage(metadata)
    if calendar is None:
        assert calendar_manifest is not None
        calendar = load_calendar_manifest(calendar_manifest)
    aggregator = MultiTimeframeAggregator(
        calendar,
        AggregationSpec(allowed_lateness_ns=0),
    )
    bars: list[FinalBar] = []
    issues: list[MarketDataIssue] = []
    event_count = 0
    for event in iter_historical_trades(
        coverage,
        store_factory=store_factory,
        limit=record_limit,
    ):
        event_count += 1
        batch = aggregator.push(event)
        bars.extend(batch.bars)
        issues.extend(batch.issues)
    final = aggregator.finish()
    bars.extend(final.bars)
    issues.extend(final.issues)
    bars.sort(
        key=lambda bar: (
            bar.end_ns,
            bar.start_ns,
            bar.instrument.root,
            bar.instrument_id,
            bar.timeframe.value,
        )
    )
    return {
        "aggregation_fingerprint": aggregator.spec.fingerprint,
        "bars": [
            bar.canonical_dict() | {"bar_id": bar.identity, "series_id": bar.series_id}
            for bar in bars
        ],
        "calendar_fingerprint": calendar.fingerprint,
        "calendar_coverage_end": calendar.coverage_end.isoformat(),
        "calendar_coverage_start": calendar.coverage_start.isoformat(),
        "event_count": event_count,
        "issues": [issue.canonical_dict() for issue in issues],
        "record_limit": record_limit,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stoic-data")
    commands = parser.add_subparsers(dest="command", required=True)

    inspect_parser = commands.add_parser("inspect", help="validate DBN metadata and coverage")
    inspect_parser.add_argument("paths", nargs="+", type=Path)

    sample_parser = commands.add_parser("sample", help="build bounded deterministic bar samples")
    sample_parser.add_argument("paths", nargs="+", type=Path)
    sample_parser.add_argument("--records", type=_positive_int, default=10_000)
    sample_parser.add_argument(
        "--calendar-manifest",
        type=Path,
        required=True,
        help="reviewed CME equity-index schedule bundle",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload: dict[str, Any]
        if args.command == "inspect":
            payload = inspect_paths(args.paths)
        else:
            payload = sample_paths(
                args.paths,
                record_limit=args.records,
                calendar_manifest=args.calendar_manifest,
            )
    except (OSError, MarketDataValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    json.dump(payload, sys.stdout, ensure_ascii=True, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
