#!/usr/bin/env python
"""Sign the decision-12 primary-evidence reviews and write them onto the rulebook.

ADR-0022: a cited range becomes normative only once a human has watched it and
signed an attestation with the pinned Ed25519 key. This script does everything
around that signature -- key handling, message construction, YAML insertion,
verification -- but the signature itself is produced by the operator's key, on
the operator's invocation. Run it yourself; do not have an agent run it.

    scripts/sign_reviews.py                       # dry run: show what would be written
    scripts/sign_reviews.py --apply               # sign and write
    scripts/sign_reviews.py --fingerprint         # print the public key fingerprint

Deviation from coding_rules.md, stated explicitly: the private key lives at
~/.stoic/evidence-review.ed25519, NOT under <repo>/.artifacts/. It is a secret,
not a run artifact, and strategy/RULEBOOK.md:135 requires it outside the repo.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from base64 import b64encode
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from stoic_derived.strategy.rulebook import load_rulebook, review_message  # noqa: E402

DEFAULT_KEY = Path.home() / ".stoic" / "evidence-review.ed25519"
DEFAULT_REVIEWS = REPO / ".scratch" / "decision-12-reviews.json"
DEFAULT_RULEBOOK = REPO / "strategy" / "rulebook.yaml"


def load_or_create_key(path: Path) -> tuple[Ed25519PrivateKey, str]:
    """Load the pinned key, creating it on first use. Raw 32 bytes, mode 0600."""
    if path.exists():
        key = Ed25519PrivateKey.from_private_bytes(path.read_bytes())
        created = False
    else:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        key = Ed25519PrivateKey.generate()
        raw = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as fh:
            fh.write(raw)
        os.replace(tmp, path)
        created = True
    public_raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    fingerprint = sha256(public_raw).hexdigest()
    if created:
        print(f"generated a new Ed25519 key at {path} (mode 0600)")
        print("back this up -- losing it means every review must be redone")
    return key, fingerprint


def build_review(evidence: dict, entry: dict, email: str, when: str, fingerprint: str) -> dict:
    """Assemble one review block and sign the exact bytes the validator will check."""
    review = {
        "reviewer_email": email,
        "reviewed_at": when,
        "verdict": entry["verdict"],
        "observed": entry["observed"],
        "asset_sha256": evidence["asset_sha256"],
        "public_key_fingerprint": fingerprint,
    }
    if evidence.get("transcript_sha256") is not None:
        review["transcript_sha256"] = evidence["transcript_sha256"]
    return review


def render_block(review: dict, key: Ed25519PrivateKey, message: bytes) -> str:
    """Render the review block as YAML at the evidence record's field indent."""
    signature = b64encode(key.sign(message)).decode("ascii")
    lines = ["    review:"]
    for field in (
        "reviewer_email",
        "reviewed_at",
        "verdict",
        "observed",
        "asset_sha256",
        "transcript_sha256",
        "public_key_fingerprint",
    ):
        if field in review:
            value = str(review[field]).replace("'", "''")
            lines.append(f"      {field}: '{value}'")
    lines.append(f"      signature_base64: '{signature}'")
    return "\n".join(lines) + "\n"


def insert_blocks(text: str, blocks: dict[str, str]) -> str:
    """Append each review block to the end of its evidence record.

    Textual rather than a YAML round-trip: safe_dump would reformat the whole
    file and drop its quoting. Each record starts at `  - id: 'ev-...'` and ends
    at the next line indented two spaces or less.
    """
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        out.append(line)
        stripped = line.strip()
        matched = next(
            (eid for eid in blocks if stripped in (f"- id: '{eid}'", f"- id: {eid}")), None
        )
        if matched is None or not line.startswith("  - id:"):
            index += 1
            continue
        index += 1
        while index < len(lines):
            nxt = lines[index]
            if nxt.strip() and not nxt.startswith("    "):
                break
            # Drop any existing review block so --force replaces rather than duplicates.
            if nxt.startswith("    review:"):
                index += 1
                while index < len(lines) and lines[index].startswith("      "):
                    index += 1
                continue
            out.append(nxt)
            index += 1
        out.append(blocks[matched])
    return "".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rulebook", type=Path, default=DEFAULT_RULEBOOK)
    parser.add_argument("--reviews", type=Path, default=DEFAULT_REVIEWS)
    parser.add_argument("--key", type=Path, default=DEFAULT_KEY)
    parser.add_argument("--apply", action="store_true", help="write; otherwise dry run")
    parser.add_argument(
        "--force", action="store_true", help="replace existing review blocks (re-sign)"
    )
    parser.add_argument("--fingerprint", action="store_true", help="print fingerprint and exit")
    args = parser.parse_args()

    key, fingerprint = load_or_create_key(args.key)
    print(f"public_key_fingerprint: {fingerprint}")
    if args.fingerprint:
        return 0

    payload = json.loads(args.reviews.read_text(encoding="utf-8"))
    email = payload["reviewer_email"]
    when = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    rulebook = load_rulebook(args.rulebook, verify_sources=False)
    records = {r["id"]: r for r in rulebook.data["evidence"]}

    blocks: dict[str, str] = {}
    for entry in payload["reviews"]:
        eid = entry["evidence_id"]
        evidence = records.get(eid)
        if evidence is None:
            print(f"unknown evidence id: {eid}", file=sys.stderr)
            return 1
        if evidence.get("review") is not None and not args.force:
            print(f"  skip  {eid}  (already reviewed; --force re-signs)")
            continue
        review = build_review(evidence, entry, email, when, fingerprint)
        message = review_message(
            evidence_id=eid,
            asset_sha256=evidence["asset_sha256"],
            transcript_sha256=evidence.get("transcript_sha256"),
            locator=evidence["locator"],
            claim=evidence["claim"],
            verdict=review["verdict"],
            observed=review["observed"],
            reviewer_email=email,
            reviewed_at=when,
            public_key_fingerprint=fingerprint,
        )
        blocks[eid] = render_block(review, key, message)
        print(f"  sign  {eid}  {review['verdict']}")

    if not blocks:
        print("nothing to do")
        return 0
    if not args.apply:
        print(f"\ndry run -- {len(blocks)} review(s) would be written. Re-run with --apply")
        return 0

    original = args.rulebook.read_text(encoding="utf-8")
    updated = insert_blocks(original, blocks)
    tmp = args.rulebook.with_suffix(args.rulebook.suffix + ".tmp")
    tmp.write_text(updated, encoding="utf-8")
    os.replace(tmp, args.rulebook)

    # The write is only trustworthy if the validator accepts it against the key.
    reloaded = load_rulebook(args.rulebook, verify_sources=False)
    signed = sum(1 for r in reloaded.data["evidence"] if r.get("review") is not None)
    print(f"\nwrote {len(blocks)} review(s); {signed} evidence record(s) now carry one")
    print("verify:  .venv/bin/stoic-rulebook review-queue strategy/rulebook.yaml")
    print(f"pinned public key (for publish --public-key-hex):\n  "
          f"{key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
