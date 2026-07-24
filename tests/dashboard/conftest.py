from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stoic_derived.dashboard.app import DashboardServices, create_app
from stoic_derived.dashboard.auth import IdentityVerifier, VerifiedIdentity
from stoic_derived.dashboard.models import (
    LedgerBlocked,
    LedgerReady,
    LedgerSnapshotResponse,
)
from stoic_derived.dashboard.operations import OperationsService, ProbeResult
from stoic_derived.dashboard.projection import LedgerAuthority, utc_string
from stoic_derived.dashboard.settings import DashboardSettings
from stoic_derived.dashboard.store import PRIMARY_ADMIN_EMAIL, DashboardStore

BASE_NS = 1_774_099_200_000_000_000


class FixedClock:
    def __init__(self, value: int = BASE_NS) -> None:
        self.value = value

    def __call__(self) -> int:
        self.value += 1_000_000_000
        return self.value


class FakeIdentityVerifier(IdentityVerifier):
    def __init__(self, email: str = PRIMARY_ADMIN_EMAIL, subject: str = "google-primary") -> None:
        self.email = email
        self.subject = subject
        self.reject = False

    def verify(self, credential: str) -> VerifiedIdentity:
        if self.reject or credential != "credential-" + "x" * 100:
            from stoic_derived.dashboard.auth import IdentityVerificationError

            raise IdentityVerificationError("access denied")
        return VerifiedIdentity(self.subject, self.email)


class FakeAuthority(LedgerAuthority):
    def __init__(self) -> None:
        self.drive_ready = False
        self.drive_detail = "Drive is not configured"
        self.drive_principal: str | None = None
        self.publish_count = 0
        self.refresh_count = 0
        self.pending = 0
        self.ledger_ready = False
        self.publish_affected = 0

    def snapshot(self, *, generated_at_ns: int) -> LedgerSnapshotResponse:
        if self.ledger_ready:
            return LedgerSnapshotResponse(
                generated_at_utc=utc_string(generated_at_ns),
                ledger=LedgerReady(
                    open_observations=(),
                    closed_observations=(),
                    unresolved_observations=(),
                ),
            )
        return LedgerSnapshotResponse(
            generated_at_utc=utc_string(generated_at_ns),
            ledger=LedgerBlocked(blockers=("signed release unavailable",)),
        )

    def refresh(self, *, generated_at_ns: int) -> LedgerSnapshotResponse:
        self.refresh_count += 1
        return self.snapshot(generated_at_ns=generated_at_ns)

    def publish(self, *, generated_at_ns: int) -> tuple[LedgerSnapshotResponse, int]:
        self.publish_count += 1
        return (
            self.snapshot(generated_at_ns=generated_at_ns),
            self.publish_affected,
        )

    def drive_status(self) -> tuple[bool, str, str | None]:
        return (
            self.drive_ready,
            self.drive_detail,
            self.drive_principal,
        )

    def outbox_status(self) -> tuple[int, int, int]:
        return self.pending, 0, 0


class FakeProbe:
    def __init__(self, ready: bool, detail: str) -> None:
        self.ready = ready
        self.detail = detail
        self.calls = 0

    def run(self) -> ProbeResult:
        self.calls += 1
        return ProbeResult(self.ready, self.detail)


@dataclass(slots=True)
class ApiBundle:
    client: TestClient
    services: DashboardServices
    identity: FakeIdentityVerifier
    authority: FakeAuthority
    market_probe: FakeProbe
    drive_probe: FakeProbe


def make_settings(tmp_path: Path) -> DashboardSettings:
    return DashboardSettings(
        control_db_path=tmp_path / "dashboard.sqlite3",
        outbox_path=tmp_path / "outbox.sqlite3",
        public_origin="https://testserver",
        google_web_client_id="client.apps.googleusercontent.com",
        allowed_hosts=("testserver",),
    )


@pytest.fixture
def api_bundle(tmp_path: Path) -> ApiBundle:
    settings = make_settings(tmp_path)
    clock = FixedClock()
    store = DashboardStore(settings.control_db_path)
    identity = FakeIdentityVerifier()
    authority = FakeAuthority()
    market_probe = FakeProbe(True, "Databento connection succeeded")
    drive_probe = FakeProbe(False, "Drive is not configured")
    operations = OperationsService(
        settings=settings,
        store=store,
        authority=authority,
        probes={"market_data": market_probe, "drive": drive_probe},
        process_started_utc_ns=BASE_NS,
        clock=clock,
    )
    services = DashboardServices(
        settings=settings,
        store=store,
        identity_verifier=identity,
        ledger_authority=authority,
        operations=operations,
        clock=clock,
    )
    app = create_app(settings, service_builder=lambda _: services)
    with TestClient(app, base_url="https://testserver") as client:
        yield ApiBundle(
            client=client,
            services=services,
            identity=identity,
            authority=authority,
            market_probe=market_probe,
            drive_probe=drive_probe,
        )


def login_primary(bundle: ApiBundle) -> tuple[str, str]:
    bundle.client.cookies.set("g_csrf_token", "google-csrf", path="/")
    response = bundle.client.post(
        "/api/v1/auth/google",
        data={
            "credential": "credential-" + "x" * 100,
            "g_csrf_token": "google-csrf",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, "primary GIS login should redirect to the SPA"
    session = bundle.client.get("/api/v1/session")
    assert session.status_code == 200, "new opaque session should authenticate"
    return (
        str(session.json()["csrf_token"]),
        str(response.headers["set-cookie"]),
    )
