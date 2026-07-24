"""Environment-only production configuration for the SP5 control API."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from stoic_derived.ledger.drive import DriveLedgerConfig, DriveLedgerError

SESSION_COOKIE_NAME = "__Host-stoic_session"


class DashboardConfigError(ValueError):
    """Raised when dashboard production configuration is incomplete or unsafe."""


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name)
    if value is None or not value.strip():
        raise DashboardConfigError(f"{name} is required")
    return value.strip()


@dataclass(frozen=True, slots=True)
class DashboardSettings:
    """Validated settings with no secret-bearing dashboard API fields."""

    control_db_path: Path
    outbox_path: Path
    public_origin: str
    google_web_client_id: str
    allowed_hosts: tuple[str, ...]
    release_path: Path | None = None
    release_sha256: str | None = None
    release_public_key: bytes | None = None
    session_ttl_seconds: int = 43_200
    max_request_bytes: int = 65_536

    def __post_init__(self) -> None:
        if not isinstance(self.control_db_path, Path) or not isinstance(self.outbox_path, Path):
            raise DashboardConfigError("database paths must be pathlib.Path values")
        if self.control_db_path == self.outbox_path:
            raise DashboardConfigError("control database and ledger outbox must be distinct")
        parsed = urlsplit(self.public_origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise DashboardConfigError("public_origin must be an absolute origin without a path")
        if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise DashboardConfigError("non-local dashboard origins must use HTTPS")
        if self.public_origin.endswith("/"):
            raise DashboardConfigError("public_origin must not end with a slash")
        if not self.google_web_client_id or len(self.google_web_client_id) > 512:
            raise DashboardConfigError("google_web_client_id must be non-empty and bounded")
        if not self.allowed_hosts or any(
            not host or "/" in host or ":" in host for host in self.allowed_hosts
        ):
            raise DashboardConfigError("allowed_hosts must contain hostnames without ports")
        supplied = (
            self.release_path is not None,
            self.release_sha256 is not None,
            self.release_public_key is not None,
        )
        if len(set(supplied)) != 1:
            raise DashboardConfigError("release path, SHA-256, and public key are all-or-none")
        if self.release_sha256 is not None and (
            len(self.release_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.release_sha256)
        ):
            raise DashboardConfigError("release_sha256 must be a lowercase SHA-256 digest")
        if self.release_public_key is not None and len(self.release_public_key) != 32:
            raise DashboardConfigError("release_public_key must contain exactly 32 bytes")
        if not 300 <= self.session_ttl_seconds <= 86_400:
            raise DashboardConfigError("session_ttl_seconds must be from 300 through 86400")
        if not 4_096 <= self.max_request_bytes <= 1_048_576:
            raise DashboardConfigError("max_request_bytes must be from 4096 through 1048576")

    @property
    def google_login_uri(self) -> str:
        return f"{self.public_origin}/api/v1/auth/google"

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> DashboardSettings:
        control_db_path = Path(_required(values, "STOIC_DASHBOARD_DB_PATH"))
        outbox_path = Path(_required(values, "STOIC_LEDGER_OUTBOX_PATH"))
        origin = _required(values, "STOIC_DASHBOARD_PUBLIC_ORIGIN").rstrip("/")
        google_client_id = _required(values, "STOIC_GOOGLE_WEB_CLIENT_ID")
        parsed = urlsplit(origin)
        default_host = parsed.hostname or ""
        hosts_value = values.get("STOIC_DASHBOARD_ALLOWED_HOSTS", default_host)
        hosts = tuple(sorted({item.strip() for item in hosts_value.split(",") if item.strip()}))

        release_path_value = values.get("STOIC_RELEASE_PATH")
        release_sha = values.get("STOIC_RELEASE_SHA256")
        release_key_hex = values.get("STOIC_RELEASE_PUBLIC_KEY_HEX")
        release_key: bytes | None = None
        if release_key_hex is not None:
            try:
                release_key = bytes.fromhex(release_key_hex)
            except ValueError as exc:
                raise DashboardConfigError(
                    "STOIC_RELEASE_PUBLIC_KEY_HEX must be hexadecimal"
                ) from exc

        try:
            session_ttl = int(values.get("STOIC_DASHBOARD_SESSION_TTL_SECONDS", "43200"))
            max_request_bytes = int(values.get("STOIC_DASHBOARD_MAX_REQUEST_BYTES", "65536"))
        except ValueError as exc:
            raise DashboardConfigError("numeric dashboard settings must be integers") from exc

        return cls(
            control_db_path=control_db_path,
            outbox_path=outbox_path,
            public_origin=origin,
            google_web_client_id=google_client_id,
            allowed_hosts=hosts,
            release_path=Path(release_path_value) if release_path_value else None,
            release_sha256=release_sha,
            release_public_key=release_key,
            session_ttl_seconds=session_ttl,
            max_request_bytes=max_request_bytes,
        )

    @classmethod
    def from_environment(cls) -> DashboardSettings:
        return cls.from_mapping(os.environ)

    def drive_config(self, values: Mapping[str, str] | None = None) -> DriveLedgerConfig:
        try:
            return DriveLedgerConfig.from_mapping(values if values is not None else os.environ)
        except DriveLedgerError as exc:
            raise DashboardConfigError(str(exc)) from exc


__all__ = [
    "SESSION_COOKIE_NAME",
    "DashboardConfigError",
    "DashboardSettings",
]
