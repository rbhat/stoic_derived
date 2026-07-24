"""Google Identity Services verification and cookie-session primitives."""

from __future__ import annotations

import hmac
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

import cachecontrol
import requests
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2 import id_token

from .store import AuthenticationError, normalize_email

GOOGLE_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})


class IdentityVerificationError(AuthenticationError):
    """A deliberately generic Google credential verification failure."""


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    google_sub: str
    authoritative_email: str


class IdentityVerifier(Protocol):
    def verify(self, credential: str) -> VerifiedIdentity: ...


class GoogleIdentityVerifier:
    """Verify GIS ID tokens with official google-auth and strict claim policy."""

    def __init__(
        self,
        web_client_id: str,
        *,
        now_seconds: Callable[[], float] = time.time,
    ) -> None:
        if not web_client_id:
            raise IdentityVerificationError("access denied")
        self._web_client_id = web_client_id
        self._now_seconds = now_seconds
        cached = cachecontrol.CacheControl(requests.Session())
        self._request = Request(session=cached)

    def verify(self, credential: str) -> VerifiedIdentity:
        if not isinstance(credential, str) or not 100 <= len(credential) <= 16_384:
            raise IdentityVerificationError("access denied")
        try:
            claims = id_token.verify_oauth2_token(  # type: ignore[no-untyped-call]
                credential,
                self._request,
                audience=self._web_client_id,
            )
        except (GoogleAuthError, ValueError, TypeError) as exc:
            raise IdentityVerificationError("access denied") from exc
        return verify_claims(
            claims,
            expected_audience=self._web_client_id,
            now_seconds=self._now_seconds(),
        )


def verify_claims(
    claims: Mapping[str, object],
    *,
    expected_audience: str,
    now_seconds: float,
) -> VerifiedIdentity:
    issuer = claims.get("iss")
    audience = claims.get("aud")
    expiry = claims.get("exp")
    subject = claims.get("sub")
    email = claims.get("email")
    verified = claims.get("email_verified")
    hosted_domain = claims.get("hd")

    if issuer not in GOOGLE_ISSUERS or audience != expected_audience:
        raise IdentityVerificationError("access denied")
    if not isinstance(expiry, (int, float)) or isinstance(expiry, bool) or expiry <= now_seconds:
        raise IdentityVerificationError("access denied")
    if not isinstance(subject, str) or not subject or len(subject) > 255:
        raise IdentityVerificationError("access denied")
    if verified is not True or not isinstance(email, str):
        raise IdentityVerificationError("access denied")
    try:
        normalized_email = normalize_email(email)
    except ValueError as exc:
        raise IdentityVerificationError("access denied") from exc
    authoritative = normalized_email.endswith("@gmail.com") or (
        isinstance(hosted_domain, str)
        and bool(hosted_domain.strip())
        and normalized_email.rpartition("@")[2] == hosted_domain.strip().casefold()
    )
    if not authoritative:
        raise IdentityVerificationError("access denied")
    return VerifiedIdentity(subject, normalized_email)


def verify_gis_csrf(cookie_token: str | None, form_token: str | None) -> None:
    if (
        not isinstance(cookie_token, str)
        or not isinstance(form_token, str)
        or not cookie_token
        or not form_token
        or len(cookie_token) > 512
        or len(form_token) > 512
        or not hmac.compare_digest(cookie_token, form_token)
    ):
        raise IdentityVerificationError("invalid Google sign-in request")


__all__ = [
    "GOOGLE_ISSUERS",
    "GoogleIdentityVerifier",
    "IdentityVerificationError",
    "IdentityVerifier",
    "VerifiedIdentity",
    "verify_claims",
    "verify_gis_csrf",
]
