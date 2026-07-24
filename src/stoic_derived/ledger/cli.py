"""Portable SP4 readiness, lifecycle, watchdog, and Drive sync commands."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from stoic_derived.market_data.codec import CodecError, read_batches_jsonl
from stoic_derived.signal_engine.alignment import FinalizedSeriesBatch
from stoic_derived.strategy.rulebook import RulebookError

from .codec import LedgerCodecError, decode_event
from .drive import (
    DriveLedgerConfig,
    DriveLedgerError,
    DriveLedgerStore,
    GoogleDriveTransport,
)
from .model import LedgerError, LedgerEvent
from .outbox import LedgerOutbox, OutboxError
from .reconcile import reconcile_events
from .runner import LedgerRunResult, readiness, run_release_ledger
from .watchdog import coalesce_cutoff_batches, enqueue_cutoff

WATCHDOG_SOURCE = "stoic-ledger-watchdog/v1"


def _public_key_bytes(value: str) -> bytes:
    try:
        parsed = bytes.fromhex(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be hexadecimal") from exc
    if len(parsed) != 32:
        raise argparse.ArgumentTypeError("must encode exactly 32 bytes")
    return parsed


def _session_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise argparse.ArgumentTypeError("must use canonical YYYY-MM-DD")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stoic-ledger")
    commands = parser.add_subparsers(dest="command", required=True)

    readiness_parser = commands.add_parser(
        "readiness", help="report release and Drive safety readiness"
    )
    readiness_parser.add_argument("--release", type=Path)
    readiness_parser.add_argument("--sha256")
    readiness_parser.add_argument("--public-key-hex", type=_public_key_bytes)

    run_parser = commands.add_parser(
        "run", help="observe signed-release signals and committed market batches"
    )
    _add_release_args(run_parser)
    run_parser.add_argument("--batches", type=Path, required=True)
    run_parser.add_argument("--outbox", type=Path, required=True)

    watchdog_parser = commands.add_parser(
        "watchdog", help="independently observe one 13:58 Pacific cutoff"
    )
    watchdog_parser.add_argument("--batches", type=Path, required=True)
    watchdog_parser.add_argument("--outbox", type=Path, required=True)
    watchdog_parser.add_argument("--session-date", type=_session_date, required=True)
    watchdog_parser.add_argument("--owner", required=True)
    watchdog_parser.add_argument("--lease-ttl-seconds", type=int, default=300)

    reconcile_parser = commands.add_parser(
        "reconcile", help="reconcile verified Drive and committed outbox events"
    )
    reconcile_parser.add_argument("--outbox", type=Path, required=True)

    sync_parser = commands.add_parser("sync", help="publish committed outbox events to Drive")
    sync_parser.add_argument("--outbox", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "readiness":
            payload = _readiness_payload(parser, args)
        elif args.command == "run":
            payload = _run_payload(args)
        elif args.command == "watchdog":
            payload = _watchdog_payload(args)
        elif args.command == "reconcile":
            payload = _reconcile_payload(args)
        else:
            payload = _sync_payload(args)
    except (
        CodecError,
        DriveLedgerError,
        LedgerCodecError,
        LedgerError,
        OSError,
        OutboxError,
        RulebookError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    json.dump(payload, sys.stdout, ensure_ascii=True, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def _readiness_payload(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> dict[str, object]:
    release_supplied = args.release is not None
    credentials_supplied = args.sha256 is not None or args.public_key_hex is not None
    if release_supplied != (args.sha256 is not None and args.public_key_hex is not None):
        parser.error("--release, --sha256, and --public-key-hex must be supplied together")
    if credentials_supplied and not release_supplied:
        parser.error("--sha256 and --public-key-hex require --release")
    result = readiness(args.release, args.sha256, args.public_key_hex)
    if result.status == "blocked":
        return result.canonical_dict()
    try:
        store = _drive_store()
        drive = store.readiness()
    except DriveLedgerError as exc:
        drive_principal = None
        blockers: tuple[str, ...] = (str(exc),)
    else:
        blockers = drive.blockers
        drive_principal = drive.principal
    if blockers:
        combined = LedgerRunResult(
            status="blocked",
            blockers=tuple(
                {"code": "drive_unready", "message": blocker, "rule_id": None}
                for blocker in blockers
            ),
            signal_count=0,
            event_count=0,
        )
        return combined.canonical_dict()
    payload = result.canonical_dict()
    payload["drive_principal"] = drive_principal
    return payload


def _run_payload(args: argparse.Namespace) -> dict[str, object]:
    preflight = readiness(args.release, args.sha256, args.public_key_hex)
    if preflight.status == "blocked":
        return preflight.canonical_dict()
    batches = _read_batches(args.batches)
    outbox = LedgerOutbox(args.outbox)
    store = _drive_store()
    remote_events = store.read_events()
    result = run_release_ledger(
        batches,
        release_path=args.release,
        expected_sha256=args.sha256,
        public_key=args.public_key_hex,
        outbox=outbox,
        remote_events=remote_events,
    )
    published = store.publish_pending(outbox)
    payload = result.canonical_dict()
    payload["published_event_count"] = len(published)
    return payload


def _watchdog_payload(args: argparse.Namespace) -> dict[str, object]:
    if args.lease_ttl_seconds <= 0:
        raise LedgerError("lease TTL must be positive")
    batches = _read_batches(args.batches)
    eligible = coalesce_cutoff_batches(batches, session_date=args.session_date)
    if not eligible:
        raise LedgerError("no committed batch watermark reaches the requested cutoff")

    outbox = LedgerOutbox(args.outbox)
    store = _drive_store()
    by_id = {event.event_id: event for event in store.read_events()}
    for payload in outbox.undelivered_event_bytes():
        event = decode_event(payload)
        by_id.setdefault(event.event_id, event)
    created: list[LedgerEvent] = []
    for batch in eligible:
        generated = enqueue_cutoff(
            tuple(by_id[event_id] for event_id in sorted(by_id)),
            batch,
            outbox,
            session_date=args.session_date,
            source=WATCHDOG_SOURCE,
            owner=args.owner,
            now_utc_ns=int(datetime.now(tz=UTC).timestamp() * 1_000_000_000),
            lease_ttl_ns=args.lease_ttl_seconds * 1_000_000_000,
        )
        created.extend(generated)
        for event in generated:
            by_id[event.event_id] = event
    published = store.publish_pending(outbox)
    return {
        "closed_or_unresolved_event_count": len(created),
        "execution": False,
        "orders_placed": 0,
        "published_event_count": len(published),
        "session_date": args.session_date.isoformat(),
        "status": "complete",
    }


def _reconcile_payload(args: argparse.Namespace) -> dict[str, object]:
    outbox = LedgerOutbox(args.outbox)
    store = _drive_store()
    store.verify_acknowledged(outbox)
    by_id = {event.event_id: event for event in store.read_events()}
    for payload in outbox.undelivered_event_bytes():
        event = decode_event(payload)
        by_id.setdefault(event.event_id, event)
    return reconcile_events(tuple(by_id[event_id] for event_id in sorted(by_id))).canonical_dict()


def _sync_payload(args: argparse.Namespace) -> dict[str, object]:
    outbox = LedgerOutbox(args.outbox)
    published = _drive_store().publish_pending(outbox)
    return {
        "execution": False,
        "orders_placed": 0,
        "published_event_count": len(published),
        "status": "complete",
    }


def _drive_store() -> DriveLedgerStore:
    config = DriveLedgerConfig.from_mapping(os.environ)
    return DriveLedgerStore(GoogleDriveTransport.from_adc(), config)


def _read_batches(path: Path) -> tuple[FinalizedSeriesBatch, ...]:
    with path.open("rb") as stream:
        return read_batches_jsonl(stream)


def _add_release_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--public-key-hex", type=_public_key_bytes, required=True)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
