"""Secret-free readiness inspection for the deterministic signal engine."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from stoic_derived.strategy.rulebook import (
    RulebookError,
    candidate_digest,
    load_rulebook,
    readiness,
)

from .compiler import compile_production_release


def _public_key_bytes(value: str) -> bytes:
    try:
        parsed = bytes.fromhex(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be hexadecimal") from exc
    if len(parsed) != 32:
        raise argparse.ArgumentTypeError("must encode exactly 32 bytes")
    return parsed


def candidate_readiness(path: Path) -> dict[str, object]:
    """Inspect authoring readiness without making draft YAML executable."""
    rulebook = load_rulebook(path, verify_sources=False)
    state = readiness(rulebook)
    return {
        "blockers": list(state.blockers),
        "candidate_sha256": candidate_digest(rulebook),
        "kind": "authoring_candidate",
        "rulebook_version": rulebook.data["rulebook_version"],
        "signal_engine_ready": False,
        "sp0_publication_ready": state.ready,
        "status": "blocked",
    }


def release_readiness(path: Path, expected_sha256: str, public_key: bytes) -> dict[str, object]:
    """Inspect production compilation through the pinned SP0 loader boundary."""
    result = compile_production_release(path, expected_sha256, public_key)
    return {
        "blockers": [
            {
                "code": blocker.code.value,
                "message": blocker.message,
                "rule_id": blocker.rule_id,
            }
            for blocker in result.readiness.blockers
        ],
        "kind": "published_release",
        "release_sha256": expected_sha256,
        "signal_engine_ready": result.readiness.ready,
        "status": "ready" if result.readiness.ready else "blocked",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stoic-signal")
    commands = parser.add_subparsers(dest="command", required=True)
    readiness_parser = commands.add_parser("readiness", help="report fail-closed SP0/SP2 readiness")
    sources = readiness_parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--candidate", type=Path)
    sources.add_argument("--release", type=Path)
    readiness_parser.add_argument("--sha256")
    readiness_parser.add_argument("--public-key-hex", type=_public_key_bytes)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.candidate is not None:
            if args.sha256 is not None or args.public_key_hex is not None:
                parser.error("--sha256 and --public-key-hex apply only to --release")
            payload = candidate_readiness(args.candidate)
        else:
            if args.sha256 is None or args.public_key_hex is None:
                parser.error("--release requires --sha256 and --public-key-hex")
            payload = release_readiness(args.release, args.sha256, args.public_key_hex)
    except (OSError, RulebookError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    json.dump(payload, sys.stdout, ensure_ascii=True, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
