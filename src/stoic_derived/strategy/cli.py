"""Command-line interface for review-only rulebook operations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .rulebook import (
    RulebookError,
    approval_message,
    candidate_digest,
    is_reviewed,
    load_rulebook,
    publish,
    readiness,
    render_dossier,
    review_message,
    unreviewed_cited_evidence,
)


def _media_seconds(text: str) -> int:
    hours, minutes, seconds = (int(part) for part in text.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stoic-rulebook")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("rulebook", type=Path)
    validate.add_argument(
        "--skip-source-verification",
        action="store_true",
        help="structural-only validation for clean clones without Drive-backed source media",
    )
    digest = commands.add_parser("digest")
    digest.add_argument("rulebook", type=Path)
    render = commands.add_parser("render")
    render.add_argument("rulebook", type=Path)
    render.add_argument("--output", type=Path)
    render.add_argument("--check", type=Path)
    publisher = commands.add_parser("publish")
    publisher.add_argument("rulebook", type=Path)
    publisher.add_argument("--releases-dir", type=Path, default=Path("strategy/releases"))
    publisher.add_argument("--public-key-hex", required=True)
    approval = commands.add_parser("approval-message")
    approval.add_argument("rulebook", type=Path)
    approval.add_argument("--reviewer-email", required=True)
    approval.add_argument("--approved-at", required=True)
    approval.add_argument("--public-key-fingerprint", required=True)
    queue = commands.add_parser(
        "review-queue",
        help="cited media ranges awaiting the ADR-0004 human review, with what to open",
    )
    queue.add_argument("rulebook", type=Path)
    queue.add_argument("--all", action="store_true", help="include already-reviewed records")
    message = commands.add_parser(
        "review-message",
        help="bytes a reviewer's Ed25519 key must sign to attest one cited range",
    )
    message.add_argument("rulebook", type=Path)
    message.add_argument("--evidence-id", required=True)
    message.add_argument("--reviewer-email", required=True)
    message.add_argument("--reviewed-at", required=True)
    message.add_argument("--public-key-fingerprint", required=True)
    message.add_argument(
        "--verdict", default="claim_supported", choices=["claim_supported", "claim_not_supported"]
    )
    return parser


def _print_review_queue(rulebook, *, show_all: bool) -> None:
    pending = set(unreviewed_cited_evidence(rulebook))
    cited: set[str] = set()
    for rule in rulebook.data.get("rules", []):
        cited.update(rule.get("evidence_ids", []))
    records = [
        record
        for record in sorted(rulebook.data["evidence"], key=lambda item: item["id"])
        if show_all or record["id"] in pending
    ]
    if not records:
        print("review queue is empty: every cited range carries a supported human review")
        return
    total = 0
    for record in records:
        locator = record["locator"]
        print(f"\n{record['id']}" + ("" if record["id"] in cited else "  (cited by no rule)"))
        print(f"  claim    {record['claim']}")
        print(f"  asset    {record['asset_path']}")
        if record["source_kind"] == "media":
            span = _media_seconds(locator["end"]) - _media_seconds(locator["start"])
            total += span
            print(f"  range    {locator['start']} .. {locator['end']}  ({span}s)")
            print(
                f'  open     ffplay -ss {locator["start"]} -autoexit '
                f'"{record["asset_path"]}"   # watch it, do not read the transcript'
            )
        else:
            print(f"  page     {locator['page']}")
        print(f"  reviewed {'yes' if is_reviewed(record) else 'NO'}")
    if total:
        print(f"\n{len(records)} record(s), {total // 60}m{total % 60}s of media to watch")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        # Python callers may opt into structural-only validation for clean clones;
        # the normal CLI validate command verifies source bytes by default.
        verify_sources = args.command == "validate" and not args.skip_source_verification
        rulebook = load_rulebook(args.rulebook, verify_sources=verify_sources)
        if args.command == "validate":
            state = readiness(rulebook)
            print(f"valid: {args.rulebook}")
            print(f"readiness: {'READY' if state.ready else 'BLOCKED'}")
            for blocker in state.blockers:
                print(f"blocker: {blocker}")
        elif args.command == "digest":
            print(candidate_digest(rulebook))
        elif args.command == "render":
            rendered = render_dossier(rulebook)
            if args.check is not None:
                if not args.check.exists() or args.check.read_text(encoding="utf-8") != rendered:
                    print(f"render drift: {args.check}", file=sys.stderr)
                    return 1
            elif args.output is not None:
                args.output.write_text(rendered, encoding="utf-8")
            else:
                print(rendered, end="")
        elif args.command == "review-queue":
            _print_review_queue(rulebook, show_all=args.all)
        elif args.command == "review-message":
            records = {record["id"]: record for record in rulebook.data["evidence"]}
            record = records.get(args.evidence_id)
            if record is None:
                raise RulebookError(f"unknown evidence id: {args.evidence_id}")
            sys.stdout.buffer.write(
                review_message(
                    evidence_id=record["id"],
                    asset_sha256=record["asset_sha256"],
                    transcript_sha256=record.get("transcript_sha256"),
                    locator=record["locator"],
                    claim=record["claim"],
                    verdict=args.verdict,
                    reviewer_email=args.reviewer_email,
                    reviewed_at=args.reviewed_at,
                    public_key_fingerprint=args.public_key_fingerprint,
                )
            )
        elif args.command == "approval-message":
            sys.stdout.buffer.write(
                approval_message(
                    reviewer_email=args.reviewer_email,
                    approved_at=args.approved_at,
                    candidate_sha256=candidate_digest(rulebook),
                    public_key_fingerprint=args.public_key_fingerprint,
                )
            )
        else:
            try:
                public_key = bytes.fromhex(args.public_key_hex)
            except ValueError as exc:
                raise RulebookError(
                    "--public-key-hex must contain hexadecimal Ed25519 raw key bytes"
                ) from exc
            output = publish(args.rulebook, args.releases_dir, public_key)
            print(output)
    except RulebookError as exc:
        print(f"rulebook error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
