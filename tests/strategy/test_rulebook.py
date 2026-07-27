from __future__ import annotations

import hashlib
import json
from base64 import b64encode
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from stoic_derived.strategy.cli import main as cli_main
from stoic_derived.strategy.rulebook import (
    PublicationError,
    RulebookError,
    approval_message,
    candidate_digest,
    load_published_release,
    load_rulebook,
    publish,
    readiness,
    render_dossier,
    review_message,
    unreviewed_cited_evidence,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def public_key_bytes(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def write_release(path: Path, release: dict[str, Any]) -> Path:
    payload = {key: value for key, value in release.items() if key != "payload_sha256"}
    release["payload_sha256"] = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    path.write_bytes(
        json.dumps(release, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    return path


def signal(entry: str, stop: str, target: str) -> dict[str, Any]:
    return {
        "entry": {"kind": "constant", "value": entry},
        "stop": {"kind": "constant", "value": stop},
        "target": {"kind": "constant", "value": target},
        "orientation_guard": {
            "op": "target_gt_entry_gt_stop"
            if Decimal(target) > Decimal(stop)
            else "stop_gt_entry_gt_target"
        },
        "r_multiple": {"op": "reward_over_risk"},
        "confidence": {
            "op": "weighted_sum",
            "features": [{"id": "setup_quality", "weight": 50}],
            "range": {"min": 0, "max": 100},
        },
    }


def complete_rulebook(tmp_path: Path) -> Path:
    asset = tmp_path / "source.pdf"
    asset.write_bytes(b"Stoic primary source")
    return write_rulebook(
        tmp_path / "complete.yaml",
        {
            "schema_version": "1.0",
            "rulebook_version": "1.0.0",
            "scope": {
                "instruments": ["NQ", "ES"],
                "timeframe_maps": {
                    "Scalp": {"htf": "15m", "setup": "5m", "execute": "1m", "manage": "5m"},
                    "Day": {"htf": "60m", "setup": "5m", "execute": "1m", "manage": "5m"},
                    "Swing": {"htf": "1d", "setup": "60m", "execute": "15m", "manage": "60m"},
                    "Position": {"htf": "1w", "setup": "1d", "execute": "60m", "manage": "1d"},
                },
            },
            "evidence": [
                {
                    "id": "primary-1",
                    "source_kind": "pdf",
                    "asset_path": "source.pdf",
                    "asset_sha256": sha256(asset),
                    "locator": {"page": 1},
                    "claim": "A validated source claim.",
                }
            ],
            "rules": [
                {
                    "id": "br-entry",
                    "capability": "entry",
                    "status": "validated",
                    "direction": "long",
                    "entry_model": "sbs_model_1",
                    "claim": "Use the approved break-and-retest entry.",
                    "evidence_ids": ["primary-1"],
                    "setup_type": "break_and_retest",
                    "predicate": {
                        "op": "all",
                        "items": [
                            {
                                "op": "gt",
                                "left": {"kind": "bar_field", "field": "close", "offset": 0},
                                "right": {"kind": "constant", "value": "1.00"},
                            }
                        ],
                    },
                    "signal": signal("2.00", "1.00", "3.00"),
                },
                {
                    "id": "sfp-stop",
                    "capability": "stop",
                    "status": "validated",
                    "direction": "short",
                    "entry_model": "sbs_model_2",
                    "claim": "Use the approved stop.",
                    "evidence_ids": ["primary-1"],
                    "setup_type": "swing_failure_pattern",
                    "predicate": {
                        "op": "not",
                        "item": {
                            "op": "eq",
                            "left": {"kind": "bar_field", "field": "close", "offset": 0},
                            "right": {"kind": "constant", "value": "0"},
                        },
                    },
                    "signal": signal("2.00", "3.00", "1.00"),
                },
                {
                    "id": "target",
                    "capability": "target",
                    "status": "validated",
                    "setup_type": "break_and_retest",
                    "direction": "short",
                    "entry_model": "sbs_model_1",
                    "claim": "Use the approved target.",
                    "evidence_ids": ["primary-1"],
                    "predicate": {
                        "op": "eq",
                        "left": {"kind": "bar_field", "field": "close", "offset": 0},
                        "right": {"kind": "prior_value", "field": "close", "offset": 1},
                    },
                    "signal": signal("2.00", "3.00", "1.00"),
                },
                {
                    "id": "confidence",
                    "capability": "confidence",
                    "status": "validated",
                    "setup_type": "swing_failure_pattern",
                    "direction": "long",
                    "entry_model": "sbs_model_2",
                    "claim": "Use deterministic confidence.",
                    "evidence_ids": ["primary-1"],
                    "predicate": {
                        "op": "within_bars",
                        "bars": 3,
                        "item": {
                            "op": "eq",
                            "left": {"kind": "bar_field", "field": "close", "offset": 0},
                            "right": {"kind": "constant", "value": "1"},
                        },
                    },
                    "signal": signal("2.00", "1.00", "3.00"),
                },
            ],
            "unresolved_decisions": [],
        },
    )


PLACEHOLDER_SIGNATURE = b64encode(bytes(64)).decode("ascii")


def attach_review(
    evidence: dict[str, Any],
    *,
    verdict: str = "claim_supported",
    private_key: Ed25519PrivateKey | None = None,
) -> dict[str, Any]:
    """Give an evidence record the ADR-0004 human attestation decision 12 defines.

    Without a key the signature is a well-formed placeholder: structural validation
    accepts it, `publish` does not. That split is deliberate — it lets the loader
    tests stay key-free while the publication tests still prove the crypto binds.
    """
    fingerprint = (
        hashlib.sha256(public_key_bytes(private_key)).hexdigest()
        if private_key is not None
        else hashlib.sha256(b"placeholder").hexdigest()
    )
    review = {
        "reviewer_email": "human@example.com",
        "reviewed_at": "2026-07-24T00:00:00Z",
        "verdict": verdict,
        "observed": "Watched the cited range; the claim is stated on screen.",
        "asset_sha256": evidence["asset_sha256"],
        **(
            {"transcript_sha256": evidence["transcript_sha256"]}
            if "transcript_sha256" in evidence
            else {}
        ),
        "public_key_fingerprint": fingerprint,
        "signature_base64": PLACEHOLDER_SIGNATURE,
    }
    if private_key is not None:
        review["signature_base64"] = b64encode(
            private_key.sign(
                review_message(
                    evidence_id=evidence["id"],
                    asset_sha256=evidence["asset_sha256"],
                    transcript_sha256=evidence.get("transcript_sha256"),
                    locator=evidence["locator"],
                    claim=evidence["claim"],
                    verdict=verdict,
                    observed=review["observed"],
                    reviewer_email=review["reviewer_email"],
                    reviewed_at=review["reviewed_at"],
                    public_key_fingerprint=fingerprint,
                )
            )
        ).decode("ascii")
    evidence["review"] = review
    return evidence


def write_rulebook(path: Path, payload: dict[str, Any]) -> Path:
    import yaml

    for rule in payload.get("rules", []):
        rule.setdefault("kind", "executable_rule")
    # Every fixture that validates a rule needs its cited evidence reviewed, or the
    # ADR-0004 gate refuses to load it. Fixtures that set a review keep theirs.
    validated = {
        reference
        for rule in payload.get("rules", [])
        if rule.get("status") == "validated"
        for reference in rule.get("evidence_ids", [])
    }
    for evidence in payload.get("evidence", []):
        if evidence.get("id") in validated and "review" not in evidence:
            attach_review(evidence)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def sign_reviews(path: Path, key: Ed25519PrivateKey) -> None:
    """Replace placeholder review signatures with real ones from the pinned key.

    Reviews are authoring data, so this moves the candidate digest — call it before
    capturing any digest baseline, exactly as a real reviewer signs before approval.
    """
    import yaml

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    for evidence in payload.get("evidence", []):
        if evidence.get("review", {}).get("signature_base64") == PLACEHOLDER_SIGNATURE:
            attach_review(evidence, verdict=evidence["review"]["verdict"], private_key=key)
    write_rulebook(path, payload)


def approve(path: Path, private_key: Ed25519PrivateKey | None = None) -> Ed25519PrivateKey:
    import yaml

    key = private_key or Ed25519PrivateKey.generate()
    sign_reviews(path, key)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    candidate = candidate_digest(load_rulebook(path))
    public_key_fingerprint = hashlib.sha256(public_key_bytes(key)).hexdigest()
    payload["approval"] = {
        "reviewer_email": "human@example.com",
        "approved_at": "2026-07-24T00:00:00Z",
        "candidate_sha256": candidate,
        "public_key_fingerprint": public_key_fingerprint,
        "signature_base64": b64encode(
            key.sign(
                approval_message(
                    reviewer_email="human@example.com",
                    approved_at="2026-07-24T00:00:00Z",
                    candidate_sha256=candidate,
                    public_key_fingerprint=public_key_fingerprint,
                )
            )
        ).decode("ascii"),
    }
    write_rulebook(path, payload)
    return key


def test_candidate_digest_excludes_only_approval_envelope(tmp_path: Path) -> None:
    rulebook = complete_rulebook(tmp_path)
    key = Ed25519PrivateKey.generate()
    # Evidence reviews are authoring data and stay inside the digest, so the approval
    # signature covers who reviewed which range. Only the envelope itself is excluded.
    sign_reviews(rulebook, key)
    original = candidate_digest(load_rulebook(rulebook))
    approve(rulebook, key)
    assert candidate_digest(load_rulebook(rulebook)) == original

    import yaml

    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    payload["rules"][0]["claim"] = "Changed meaning."
    write_rulebook(rulebook, payload)
    assert candidate_digest(load_rulebook(rulebook)) != original


def test_complete_approved_rulebook_publishes_byte_identical_canonical_json(tmp_path: Path) -> None:
    rulebook = complete_rulebook(tmp_path)
    private_key = approve(rulebook)
    public_key = public_key_bytes(private_key)
    first = publish(rulebook, tmp_path / "releases", public_key)
    first_bytes = first.read_bytes()
    second = publish(rulebook, tmp_path / "releases", public_key)
    assert second.read_bytes() == first_bytes
    release = json.loads(first_bytes)
    assert release["rulebook_version"] == "1.0.0"
    assert release["source_yaml_sha256"] == sha256(rulebook)
    payload = {key: value for key, value in release.items() if key != "payload_sha256"}
    assert (
        release["payload_sha256"]
        == hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
    )
    assert load_published_release(first, expected_sha256=sha256(first), public_key=public_key)[
        "rulebook_version"
    ]


def test_repository_candidate_is_valid_but_publish_is_truthfully_blocked(tmp_path: Path) -> None:
    candidate = load_rulebook(REPOSITORY_ROOT / "strategy" / "rulebook.yaml")
    state = readiness(candidate)
    assert state.ready is False
    assert any("break_and_retest/long" in blocker for blocker in state.blockers)
    assert any("confluence-score" in blocker for blocker in state.blockers)
    with pytest.raises(PublicationError):
        publish(candidate.path, tmp_path / "releases")
    assert not (tmp_path / "releases").exists()


def test_candidate_qualitative_claim_does_not_block_executable_readiness(tmp_path: Path) -> None:
    rulebook = complete_rulebook(tmp_path)
    import yaml

    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    payload["rules"].append(
        {
            "id": "context-definition",
            "kind": "qualitative_claim",
            "capability": "context_definition",
            "status": "candidate",
            "claim": "This source-backed definition needs only human review.",
            "evidence_ids": ["primary-1"],
        }
    )
    write_rulebook(rulebook, payload)
    approve(rulebook)
    assert readiness(load_rulebook(rulebook)).ready is True


def test_published_loader_requires_external_pin_and_rejects_tampered_scope(tmp_path: Path) -> None:
    rulebook = complete_rulebook(tmp_path)
    private_key = approve(rulebook)
    public_key = public_key_bytes(private_key)
    release_path = publish(rulebook, tmp_path / "releases", public_key)
    with pytest.raises(TypeError):
        load_published_release(release_path)  # type: ignore[call-arg]

    tampered = json.loads(release_path.read_bytes())
    tampered["scope"]["instruments"] = ["NQ", "CL"]
    payload = {key: value for key, value in tampered.items() if key != "payload_sha256"}
    tampered["payload_sha256"] = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    tampered_path = tmp_path / "releases" / "tampered.json"
    tampered_path.write_bytes(
        json.dumps(tampered, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    with pytest.raises(PublicationError, match="instruments"):
        load_published_release(
            tampered_path, expected_sha256=sha256(tampered_path), public_key=public_key
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda release: release.update({"compiler_version": "99.0.0"}), "compiler"),
        (lambda release: release.update({"schema_version": "2.0"}), "schema"),
        (lambda release: release.update({"source_yaml_sha256": "not-a-hash"}), "source_yaml"),
        (lambda release: release.update({"candidate_sha256": "not-a-hash"}), "candidate"),
        (lambda release: release.update({"source_snapshot_digests": {}}), "provenance"),
        (
            lambda release: release["approval"].update({"candidate_sha256": "0" * 64}),
            "approval",
        ),
        (lambda release: release["rules"].pop(), "live-ready"),
        (
            lambda release: release["rules"][0].update(
                {"entry_model": {"model_dependency": "slm"}}
            ),
            "entry_model",
        ),
    ],
)
def test_published_loader_revalidates_all_live_contracts(
    tmp_path: Path, mutate: Any, message: str
) -> None:
    rulebook = complete_rulebook(tmp_path)
    private_key = approve(rulebook)
    public_key = public_key_bytes(private_key)
    release_path = publish(rulebook, tmp_path / "releases", public_key)
    release = json.loads(release_path.read_bytes())
    mutate(release)
    tampered_path = write_release(tmp_path / "releases" / "tampered.json", release)
    with pytest.raises(PublicationError, match=message):
        load_published_release(
            tampered_path, expected_sha256=sha256(tampered_path), public_key=public_key
        )


@pytest.mark.parametrize(
    "approved_at", ["2026-07-24 00:00:00Z", "2026-07-24T00:00:00+00:00", "invalid"]
)
def test_approval_requires_rfc3339_utc_timestamp(tmp_path: Path, approved_at: str) -> None:
    rulebook = complete_rulebook(tmp_path)
    approve(rulebook)
    import yaml

    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    payload["approval"]["approved_at"] = approved_at
    write_rulebook(rulebook, payload)
    with pytest.raises(RulebookError, match="RFC3339"):
        load_rulebook(rulebook)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload["rules"][0]["predicate"].update({"surprise": True}),
            "unsupported field",
        ),
        (
            lambda payload: payload["rules"][0]["predicate"]["items"][0]["left"].update(
                {"surprise": True}
            ),
            "unsupported field",
        ),
        (
            lambda payload: payload["rules"][0].update(
                {"predicate": {"op": "sequence", "items": [payload["rules"][0]["predicate"]]}}
            ),
            "bars",
        ),
    ],
)
def test_predicate_grammar_rejects_unknown_keys_and_unbounded_sequence(
    tmp_path: Path, mutate: Any, message: str
) -> None:
    rulebook = complete_rulebook(tmp_path)
    import yaml

    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    mutate(payload)
    write_rulebook(rulebook, payload)
    with pytest.raises(RulebookError, match=message):
        load_rulebook(rulebook)


def test_cli_validate_verifies_sources_unless_explicitly_skipped(tmp_path: Path) -> None:
    rulebook = complete_rulebook(tmp_path)
    (tmp_path / "source.pdf").write_bytes(b"changed after authoring")
    assert cli_main(["validate", str(rulebook)]) == 1
    assert cli_main(["validate", str(rulebook), "--skip-source-verification"]) == 0


def test_glossary_and_evidence_dossier_are_traceable(tmp_path: Path) -> None:
    rulebook = complete_rulebook(tmp_path)
    import yaml

    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    payload["glossary"] = [
        {"term": "PDH", "meaning": "Previous daily high.", "evidence_ids": ["primary-1"]}
    ]
    write_rulebook(rulebook, payload)
    dossier = render_dossier(load_rulebook(rulebook))
    assert "## Glossary" in dossier
    assert "Previous daily high." in dossier
    assert "source.pdf" in dossier
    assert sha256(tmp_path / "source.pdf") in dossier
    repository_rulebook = load_rulebook(REPOSITORY_ROOT / "strategy" / "rulebook.yaml")
    repository_dossier = render_dossier(repository_rulebook)
    assert repository_rulebook.data["evidence"][0]["transcript_sha256"] in repository_dossier
    assert "transcript.json" in repository_dossier


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda payload: payload["rules"][0]["predicate"]["items"][0].update(
                {"left": {"kind": "derived_feature", "name": "slm_trade_decision"}}
            ),
            "allowlisted",
        ),
        (
            lambda payload: payload["rules"][0]["signal"]["entry"].update({"value": "not-a-price"}),
            "decimal",
        ),
        (lambda payload: payload["rules"][0]["signal"]["stop"].update({"value": "NaN"}), "finite"),
        (
            lambda payload: payload["rules"][0]["signal"]["target"].update({"value": "Infinity"}),
            "finite",
        ),
        (
            lambda payload: payload["rules"][0]["signal"]["r_multiple"].update({"op": "-1"}),
            "reward",
        ),
    ],
)
def test_live_value_semantics_reject_unsafe_values(
    tmp_path: Path, change: Any, message: str
) -> None:
    rulebook = complete_rulebook(tmp_path)
    import yaml

    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    change(payload)
    write_rulebook(rulebook, payload)
    with pytest.raises(RulebookError, match=message):
        load_rulebook(rulebook)


def test_semver_and_locator_kind_pairing_are_enforced(tmp_path: Path) -> None:
    rulebook = complete_rulebook(tmp_path)
    import yaml

    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    payload["rulebook_version"] = "01.0.0"
    write_rulebook(rulebook, payload)
    with pytest.raises(RulebookError, match="semantic version"):
        load_rulebook(rulebook)

    rulebook = complete_rulebook(tmp_path)
    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    payload["evidence"][0]["locator"] = {"start": "00:00:00", "end": "00:00:01"}
    write_rulebook(rulebook, payload)
    with pytest.raises(RulebookError, match="unsupported field"):
        load_rulebook(rulebook)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda payload: payload["rules"][0]["signal"]["target"].update({"value": "1.00"}),
            "target >",
        ),
        (
            lambda payload: payload["rules"][0]["signal"]["orientation_guard"].update(
                {"op": "stop_gt_entry_gt_target"}
            ),
            "orientation_guard",
        ),
    ],
)
def test_validated_profiles_require_directional_price_and_exact_r(
    tmp_path: Path, change: Any, message: str
) -> None:
    rulebook = complete_rulebook(tmp_path)
    import yaml

    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    change(payload)
    write_rulebook(rulebook, payload)
    with pytest.raises(RulebookError, match=message):
        load_rulebook(rulebook)


def test_publish_rejects_prerelease_and_missing_pinned_key(tmp_path: Path) -> None:
    rulebook = complete_rulebook(tmp_path)
    private_key = approve(rulebook)
    with pytest.raises(PublicationError, match="public key"):
        publish(rulebook, tmp_path / "releases")

    import yaml

    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    payload["rulebook_version"] = "1.0.0-candidate"
    write_rulebook(rulebook, payload)
    approve(rulebook, private_key)
    with pytest.raises(PublicationError, match="prerelease"):
        publish(rulebook, tmp_path / "releases", public_key_bytes(private_key))


def test_publish_requires_valid_human_signature_and_pinned_key(tmp_path: Path) -> None:
    rulebook = complete_rulebook(tmp_path)
    private_key = approve(rulebook)
    wrong_public_key = public_key_bytes(Ed25519PrivateKey.generate())
    with pytest.raises(PublicationError, match="fingerprint"):
        publish(rulebook, tmp_path / "releases", wrong_public_key)

    import yaml

    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    payload["approval"]["signature_base64"] = b64encode(b"0" * 64).decode("ascii")
    write_rulebook(rulebook, payload)
    with pytest.raises(PublicationError, match="signature"):
        publish(rulebook, tmp_path / "releases", public_key_bytes(private_key))

    payload["approval"]["reviewer_email"] = "agent"
    write_rulebook(rulebook, payload)
    with pytest.raises(RulebookError, match="email"):
        load_rulebook(rulebook)


def test_approval_message_cli_is_deterministic(
    tmp_path: Path, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    rulebook = complete_rulebook(tmp_path)
    fingerprint = "1" * 64
    expected = approval_message(
        reviewer_email="human@example.com",
        approved_at="2026-07-24T00:00:00Z",
        candidate_sha256=candidate_digest(load_rulebook(rulebook)),
        public_key_fingerprint=fingerprint,
    )
    assert (
        cli_main(
            [
                "approval-message",
                str(rulebook),
                "--reviewer-email",
                "human@example.com",
                "--approved-at",
                "2026-07-24T00:00:00Z",
                "--public-key-fingerprint",
                fingerprint,
            ]
        )
        == 0
    )
    assert capsysbinary.readouterr().out == expected


def test_publish_fails_closed_without_approval_or_with_stale_approval(tmp_path: Path) -> None:
    rulebook = complete_rulebook(tmp_path)
    with pytest.raises(PublicationError, match="approval"):
        publish(rulebook, tmp_path / "releases")
    approve(rulebook)
    import yaml

    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    payload["rules"][0]["claim"] = "A semantic edit invalidates approval."
    write_rulebook(rulebook, payload)
    with pytest.raises(PublicationError, match="approval"):
        publish(rulebook, tmp_path / "releases")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda value: value["scope"].update({"instruments": ["NQ", "CL"]}), "instruments"),
        (
            lambda value: value["scope"]["timeframe_maps"]["Day"].update({"execute": "5m"}),
            "timeframe",
        ),
        (lambda value: value["rules"][0]["predicate"].update({"op": "eval"}), "operator"),
        (
            lambda value: value["rules"][0]["predicate"]["items"][0]["left"].update({"offset": 1}),
            "lookahead",
        ),
        (lambda value: value["rules"][0].update({"action": "place_order"}), "action"),
        (lambda value: value["rules"][0].update({"model_dependency": "slm"}), "model"),
        (lambda value: value.update({"backtest": {"optimized_threshold": 70}}), "backtest"),
    ],
)
def test_invalid_live_inputs_fail_validation(tmp_path: Path, change: Any, message: str) -> None:
    rulebook = complete_rulebook(tmp_path)
    import yaml

    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    change(payload)
    write_rulebook(rulebook, payload)
    with pytest.raises(RulebookError, match=message):
        load_rulebook(rulebook)


def test_duplicate_yaml_keys_and_stale_evidence_fail(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text("schema_version: '1.0'\nschema_version: '1.0'\n", encoding="utf-8")
    with pytest.raises(RulebookError, match="duplicate"):
        load_rulebook(duplicate)

    rulebook = complete_rulebook(tmp_path)
    (tmp_path / "source.pdf").write_bytes(b"Changed source")
    with pytest.raises(RulebookError, match="digest"):
        load_rulebook(rulebook, verify_sources=True)


def test_render_dossier_is_deterministic_and_reports_blockers(tmp_path: Path) -> None:
    rulebook = complete_rulebook(tmp_path)
    import yaml

    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    payload["rules"][0]["status"] = "candidate"
    payload["unresolved_decisions"] = [
        {
            "id": "entry-tolerance",
            "question": "What tolerance is validated?",
            "evidence_ids": ["primary-1"],
        }
    ]
    write_rulebook(rulebook, payload)
    dossier = render_dossier(load_rulebook(rulebook))
    assert dossier == render_dossier(load_rulebook(rulebook))
    assert "# Strategy Rulebook Review Dossier" in dossier
    assert "**Publication readiness: BLOCKED**" in dossier
    assert "entry-tolerance" in dossier
    assert readiness(load_rulebook(rulebook)).ready is False


def test_missing_approval_is_a_readiness_blocker_with_signing_guidance(tmp_path: Path) -> None:
    rulebook = complete_rulebook(tmp_path)
    loaded = load_rulebook(rulebook)
    state = readiness(loaded)
    assert "human approval envelope is missing" in state.blockers
    dossier = render_dossier(loaded)
    assert "approval-message" in dossier
    assert "private key outside this repository" in dossier


def test_media_evidence_requires_a_transcript_pair(tmp_path: Path) -> None:
    rulebook = complete_rulebook(tmp_path)
    import yaml

    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    payload["evidence"][0]["source_kind"] = "media"
    payload["evidence"][0]["locator"] = {"start": "00:00:00", "end": "00:00:01"}
    write_rulebook(rulebook, payload)
    with pytest.raises(RulebookError, match="transcript_path"):
        load_rulebook(rulebook)


def test_signal_schema_accepts_closed_dynamic_operands(tmp_path: Path) -> None:
    rulebook = complete_rulebook(tmp_path)
    import yaml

    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    payload["rules"][0]["signal"].update(
        {
            "entry": {"kind": "bar_field", "field": "close", "offset": 0},
            "stop": {"kind": "prior_value", "field": "low", "offset": 1},
            "target": {"kind": "derived_feature", "name": "SMA20"},
        }
    )
    write_rulebook(rulebook, payload)
    assert load_rulebook(rulebook).data["rules"][0]["signal"]["entry"]["kind"] == "bar_field"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda payload: payload["rules"][0]["signal"]["r_multiple"].update({"extra": True}),
            "unsupported field",
        ),
        (
            lambda payload: payload["rules"][0]["signal"]["orientation_guard"].update(
                {"op": "anything_goes"}
            ),
            "orientation_guard",
        ),
        (
            lambda payload: payload["rules"][0]["signal"]["confidence"]["features"][0].update(
                {"id": "model_score"}
            ),
            "allowlisted confluence",
        ),
        (
            lambda payload: payload["rules"][0]["signal"]["confidence"]["features"][0].update(
                {"weight": 101}
            ),
            "weight",
        ),
        (
            lambda payload: payload["rules"][0]["predicate"]["items"][0]["right"].update(
                {"value": "NaN"}
            ),
            "finite",
        ),
        (
            lambda payload: payload["rules"][0].update({"entry_model": {"backtest": 1}}),
            "entry_model",
        ),
    ],
)
def test_closed_signal_formula_confidence_and_entry_model_reject_escape_hatches(
    tmp_path: Path, change: Any, message: str
) -> None:
    rulebook = complete_rulebook(tmp_path)
    import yaml

    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    change(payload)
    write_rulebook(rulebook, payload)
    with pytest.raises(RulebookError, match=message):
        load_rulebook(rulebook)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda payload: payload["rules"][0]["signal"]["entry"].update({"value": "2.10"}),
            "0.25 NQ/ES tick",
        ),
        (
            lambda payload: payload["rules"][0]["signal"].update(
                {"entry": {"kind": "bar_field", "field": "volume", "offset": 0}}
            ),
            "OHLC price field",
        ),
        (
            lambda payload: payload["rules"][0]["signal"].update(
                {"stop": {"kind": "prior_value", "field": "volume", "offset": 1}}
            ),
            "OHLC price field",
        ),
        (lambda payload: payload["rules"][0].pop("entry_model"), "entry_model"),
    ],
)
def test_validated_signal_profiles_require_tick_safe_prices_and_entry_model(
    tmp_path: Path, change: Any, message: str
) -> None:
    rulebook = complete_rulebook(tmp_path)
    import yaml

    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    change(payload)
    write_rulebook(rulebook, payload)
    with pytest.raises(RulebookError, match=message):
        load_rulebook(rulebook)


def test_stale_and_current_approval_readiness_are_truthful(tmp_path: Path) -> None:
    rulebook = complete_rulebook(tmp_path)
    approve(rulebook)
    current = load_rulebook(rulebook)
    assert readiness(current).ready is True
    current_dossier = render_dossier(current)
    assert "**Publication readiness: PENDING PINNED-KEY VERIFICATION**" in current_dossier
    assert "signature verification occurs at publish" in current_dossier

    import yaml

    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    payload["rules"][0]["claim"] = "A stale approval must not appear ready."
    write_rulebook(rulebook, payload)
    stale = load_rulebook(rulebook)
    assert "human approval envelope has a stale candidate digest" in readiness(stale).blockers
    assert "**Publication readiness: BLOCKED**" in render_dossier(stale)


# --- ADR-0004 primary-evidence review gate (unresolved decision 12) -----------------


def test_validated_rule_requires_a_supported_human_review_of_every_cited_range(
    tmp_path: Path,
) -> None:
    import yaml

    rulebook = complete_rulebook(tmp_path)
    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    del payload["evidence"][0]["review"]
    # write_rulebook re-attaches reviews for validated rules, so write raw here.
    rulebook.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(RulebookError, match="cannot be validated: no supported human review"):
        load_rulebook(rulebook)


def test_a_not_supported_verdict_does_not_validate(tmp_path: Path) -> None:
    import yaml

    rulebook = complete_rulebook(tmp_path)
    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    payload["evidence"][0]["review"]["verdict"] = "claim_not_supported"
    rulebook.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(RulebookError, match="cannot be validated: no supported human review"):
        load_rulebook(rulebook)


def test_unreviewed_cited_evidence_is_a_readiness_blocker(tmp_path: Path) -> None:
    import yaml

    rulebook = complete_rulebook(tmp_path)
    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    # Downgrade the rules so the loader accepts the unreviewed record, then confirm
    # readiness still names the missing review rather than staying silent about it.
    for rule in payload["rules"]:
        rule["status"] = "candidate"
    del payload["evidence"][0]["review"]
    rulebook.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    blockers = readiness(load_rulebook(rulebook)).blockers
    assert "cited evidence has no supported human review: primary-1" in blockers
    assert unreviewed_cited_evidence(load_rulebook(rulebook)) == ("primary-1",)


def test_review_is_bound_to_the_bytes_and_the_claim_it_attests(tmp_path: Path) -> None:
    import yaml

    rulebook = complete_rulebook(tmp_path)
    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    payload["evidence"][0]["review"]["asset_sha256"] = "0" * 64
    rulebook.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(RulebookError, match="does not match the evidence record it reviews"):
        load_rulebook(rulebook)


def test_publish_rejects_a_review_the_pinned_key_did_not_sign(tmp_path: Path) -> None:
    import yaml

    rulebook = complete_rulebook(tmp_path)
    private_key = approve(rulebook)
    # An agent can write a structurally perfect review and even sign it with some key
    # it holds; it cannot sign with the pinned one. That is what makes this an
    # ADR-0004 gate rather than a checkbox.
    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    attach_review(payload["evidence"][0], private_key=Ed25519PrivateKey.generate())
    payload["evidence"][0]["review"]["public_key_fingerprint"] = hashlib.sha256(
        public_key_bytes(private_key)
    ).hexdigest()
    write_rulebook(rulebook, payload)
    approve(rulebook, private_key)
    with pytest.raises(PublicationError, match="review signature verification failed"):
        publish(rulebook, tmp_path / "releases", public_key_bytes(private_key))


def test_editing_a_claim_after_review_invalidates_the_signature(tmp_path: Path) -> None:
    import yaml

    rulebook = complete_rulebook(tmp_path)
    private_key = approve(rulebook)
    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    # Reviewing a weak claim then strengthening it is the attack this closes.
    payload["evidence"][0]["claim"] = "A far stronger claim nobody reviewed."
    write_rulebook(rulebook, payload)
    approve(rulebook, private_key)
    with pytest.raises(PublicationError, match="review signature verification failed"):
        publish(rulebook, tmp_path / "releases", public_key_bytes(private_key))


def test_editing_observed_after_review_invalidates_the_signature(tmp_path: Path) -> None:
    """ADR-0022 as amended 2026-07-27: the reviewer's own words are attested too.

    Before the amendment `observed` sat outside the signed message, so the one field
    a future reader uses to judge a review without re-watching was the one field an
    agent could rewrite undetected.
    """
    import yaml

    rulebook = complete_rulebook(tmp_path)
    private_key = approve(rulebook)
    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    payload["evidence"][0]["review"]["observed"] = "Words the reviewer never wrote."
    write_rulebook(rulebook, payload)
    approve(rulebook, private_key)
    with pytest.raises(PublicationError, match="review signature verification failed"):
        publish(rulebook, tmp_path / "releases", public_key_bytes(private_key))


def test_published_release_carries_the_review_and_revalidates_it(tmp_path: Path) -> None:
    rulebook = complete_rulebook(tmp_path)
    private_key = approve(rulebook)
    public_key = public_key_bytes(private_key)
    release_path = publish(rulebook, tmp_path / "releases", public_key)
    release = json.loads(release_path.read_text(encoding="utf-8"))
    review = release["source_snapshot_digests"]["primary-1"]["review"]
    assert review["verdict"] == "claim_supported"
    assert review["reviewer_email"] == "human@example.com"
    load_published_release(
        release_path, hashlib.sha256(release_path.read_bytes()).hexdigest(), public_key
    )


def test_review_queue_cli_lists_what_a_reviewer_must_open(tmp_path: Path, capsys) -> None:
    import yaml

    rulebook = complete_rulebook(tmp_path)
    payload = yaml.safe_load(rulebook.read_text(encoding="utf-8"))
    for rule in payload["rules"]:
        rule["status"] = "candidate"
    del payload["evidence"][0]["review"]
    rulebook.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    assert cli_main(["review-queue", str(rulebook)]) == 0
    out = capsys.readouterr().out
    assert "primary-1" in out
    assert "A validated source claim." in out
    assert "reviewed NO" in out

    attach_review(payload["evidence"][0])
    rulebook.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    assert cli_main(["review-queue", str(rulebook)]) == 0
    assert "review queue is empty" in capsys.readouterr().out


def test_review_message_cli_is_deterministic_and_binds_the_locator(tmp_path: Path, capsys) -> None:
    rulebook = complete_rulebook(tmp_path)
    args = [
        "review-message",
        str(rulebook),
        "--evidence-id",
        "primary-1",
        "--reviewer-email",
        "human@example.com",
        "--reviewed-at",
        "2026-07-24T00:00:00Z",
        "--observed",
        "Watched the cited range; the claim is stated on screen.",
        "--public-key-fingerprint",
        "0" * 64,
    ]
    assert cli_main(args) == 0
    first = capsys.readouterr().out
    assert cli_main(args) == 0
    assert capsys.readouterr().out == first
    assert "evidence-review" in first
    assert "A validated source claim." in first
