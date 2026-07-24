"""Portable, non-executing command line boundary for SP3."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from stoic_derived.backtest.artifact import ArtifactError, inspect_artifact, write_artifact
from stoic_derived.backtest.codec import CodecError, read_batches_jsonl
from stoic_derived.backtest.model import BacktestResult, BacktestValidationError, SimulationPolicy
from stoic_derived.backtest.runner import production_readiness, run_replay


def _nonnegative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _positive_int(value: str) -> int:
    parsed = _nonnegative_int(value)
    if parsed == 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _sha256(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise argparse.ArgumentTypeError("must be a lowercase SHA-256 digest")
    return value


def _public_key_bytes(value: str) -> bytes:
    try:
        parsed = bytes.fromhex(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be hexadecimal") from exc
    if len(parsed) != 32:
        raise argparse.ArgumentTypeError("must encode exactly 32 bytes")
    return parsed


def _result_summary(result: BacktestResult) -> dict[str, object]:
    return {
        "evidence_class": result.evidence_class.value,
        "execution": False,
        "orders_placed": 0,
        "readiness_blockers": list(result.readiness_blockers),
        "run_id": result.run_id,
        "signal_count": len(result.signals),
        "status": result.status.value,
        "trade_count": len(result.trades),
    }


def _policy_from_args(args: argparse.Namespace) -> SimulationPolicy:
    return SimulationPolicy(
        entry_slippage_ticks=args.entry_slippage_ticks,
        exit_slippage_ticks=args.exit_slippage_ticks,
        fees_ticks_round_turn=args.fees_ticks_round_turn,
        zero_costs_declared=args.zero_costs_declared,
        max_active_observations=args.max_active_observations,
        max_active_lineages=args.max_active_lineages,
        max_retained_gaps=args.max_retained_gaps,
        max_accepted_batches=args.max_accepted_batches,
        max_output_records=args.max_output_records,
        max_artifact_bytes=args.max_artifact_bytes,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stoic-backtest")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "readiness",
        help="report release-bound observational readiness and zero-population safety",
    )
    run_parser = commands.add_parser(
        "run",
        help="replay canonical committed batches and publish one immutable research artifact",
    )
    run_parser.add_argument("--input", type=Path, required=True)
    run_parser.add_argument("--output", type=Path, required=True)
    run_parser.add_argument("--release", type=Path)
    run_parser.add_argument("--sha256", type=_sha256)
    run_parser.add_argument("--public-key-hex", type=_public_key_bytes)
    run_parser.add_argument("--entry-slippage-ticks", type=_nonnegative_int, required=True)
    run_parser.add_argument("--exit-slippage-ticks", type=_nonnegative_int, required=True)
    run_parser.add_argument("--fees-ticks-round-turn", type=_nonnegative_int, required=True)
    run_parser.add_argument("--zero-costs-declared", action="store_true")
    run_parser.add_argument("--max-active-observations", type=_positive_int, default=10_000)
    run_parser.add_argument("--max-active-lineages", type=_positive_int, default=16)
    run_parser.add_argument("--max-retained-gaps", type=_positive_int, default=10_000)
    run_parser.add_argument("--max-accepted-batches", type=_positive_int, default=100_000)
    run_parser.add_argument("--max-output-records", type=_positive_int, default=1_000_000)
    run_parser.add_argument("--max-artifact-bytes", type=_positive_int, default=64 * 1024 * 1024)
    inspect_parser = commands.add_parser(
        "inspect",
        help="verify and summarize one immutable research artifact",
    )
    inspect_parser.add_argument("path", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "readiness":
            payload = _result_summary(production_readiness())
        elif args.command == "inspect":
            payload = inspect_artifact(args.path).canonical_dict()
        else:
            pins = (args.release, args.sha256, args.public_key_hex)
            if any(pin is not None for pin in pins) and not all(pin is not None for pin in pins):
                parser.error("--release, --sha256, and --public-key-hex must be provided together")
            policy = _policy_from_args(args)
            with args.input.open("rb") as stream:
                batches = read_batches_jsonl(stream)
            result = run_replay(
                args.release,
                args.sha256,
                args.public_key_hex,
                batches,
                policy,
            )
            summary = write_artifact(
                result,
                args.output,
                max_artifact_bytes=policy.max_artifact_bytes,
            )
            payload = {
                **summary.canonical_dict(),
                "readiness_blockers": list(result.readiness_blockers),
                "signal_count": len(result.signals),
                "trade_count": len(result.trades),
            }
    except (ArtifactError, BacktestValidationError, CodecError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    json.dump(payload, sys.stdout, ensure_ascii=True, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
