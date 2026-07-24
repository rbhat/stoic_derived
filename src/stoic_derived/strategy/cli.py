"""Command-line interface for review-only rulebook operations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .rulebook import (
    RulebookError,
    approval_message,
    candidate_digest,
    load_rulebook,
    publish,
    readiness,
    render_dossier,
)


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
    return parser


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
