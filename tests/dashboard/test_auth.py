from __future__ import annotations

import pytest

from stoic_derived.dashboard.auth import (
    IdentityVerificationError,
    verify_claims,
    verify_gis_csrf,
)


def valid_claims() -> dict[str, object]:
    return {
        "aud": "client-id",
        "email": "RajeevMBhat@gmail.com",
        "email_verified": True,
        "exp": 2_000,
        "iss": "https://accounts.google.com",
        "sub": "google-subject",
    }


def test_gmail_claims_are_normalized_and_bound_to_google_sub() -> None:
    identity = verify_claims(
        valid_claims(),
        expected_audience="client-id",
        now_seconds=1_000,
    )

    assert identity.google_sub == "google-subject", "Google sub must be the durable identity"
    assert identity.authoritative_email == "rajeevmbhat@gmail.com", (
        "Gmail invitation comparison must be normalized"
    )


def test_verified_workspace_claims_are_authoritative() -> None:
    claims = valid_claims()
    claims["email"] = "operator@example.com"
    claims["hd"] = "example.com"

    identity = verify_claims(claims, expected_audience="client-id", now_seconds=1_000)

    assert identity.authoritative_email == "operator@example.com", (
        "verified Workspace identity with hd should be accepted"
    )


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"aud": "other-client"}, "audience"),
        ({"iss": "https://attacker.example"}, "issuer"),
        ({"exp": 999}, "expired"),
        ({"sub": ""}, "missing subject"),
        ({"email_verified": False}, "unverified email"),
        ({"email": "person@third-party.example"}, "non-authoritative email"),
        (
            {"email": "operator@other.example", "hd": "workspace.example"},
            "Workspace domain mismatch",
        ),
    ],
)
def test_invalid_or_non_authoritative_claims_are_rejected(
    change: dict[str, object],
    expected: str,
) -> None:
    claims = valid_claims()
    claims.update(change)

    with pytest.raises(IdentityVerificationError, match="access denied") as raised:
        verify_claims(claims, expected_audience="client-id", now_seconds=1_000)

    assert raised.value.args, f"{expected} should fail closed"


def test_gis_csrf_requires_matching_cookie_and_form_values() -> None:
    verify_gis_csrf("same-token", "same-token")

    with pytest.raises(IdentityVerificationError, match="invalid Google sign-in"):
        verify_gis_csrf("cookie-token", "form-token")
