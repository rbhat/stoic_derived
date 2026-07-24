"""Secret-free SP5 readiness inspection."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence

from stoic_derived.ledger.runner import readiness

from .settings import DashboardConfigError, DashboardSettings


def readiness_payload(values: Mapping[str, str]) -> dict[str, object]:
    blockers: list[str] = []
    try:
        settings = DashboardSettings.from_mapping(values)
    except DashboardConfigError as exc:
        blockers.append(str(exc))
        return {
            "blockers": blockers,
            "execution": False,
            "observation_count": 0,
            "orders_placed": 0,
            "status": "blocked",
        }
    result = readiness(
        settings.release_path,
        settings.release_sha256,
        settings.release_public_key,
    )
    blockers.extend(f"{item['code']}: {item['message']}" for item in result.blockers)
    return {
        "blockers": sorted(set(blockers)),
        "execution": False,
        "observation_count": 0,
        "orders_placed": 0,
        "status": "blocked" if blockers else "ready",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stoic-dashboard")
    parser.add_subparsers(dest="command", required=True).add_parser(
        "readiness",
        help="report configuration and signed-release readiness without serving the SPA",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    import os

    args = build_parser().parse_args(argv)
    if args.command != "readiness":  # pragma: no cover - argparse owns the vocabulary
        return 2
    json.dump(readiness_payload(os.environ), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["build_parser", "main", "readiness_payload"]
