from __future__ import annotations

import asyncio
from typing import Any

from stoic_derived.dashboard.app import RequestBodyLimitMiddleware
from stoic_derived.dashboard.settings import SESSION_COOKIE_NAME
from stoic_derived.dashboard.store import PRIMARY_ADMIN_ID

from .conftest import ApiBundle, login_primary


def mutation_headers(csrf: str) -> dict[str, str]:
    return {
        "Origin": "https://testserver",
        "X-CSRF-Token": csrf,
    }


def test_google_login_requires_double_submit_and_sets_hardened_cookie(
    api_bundle: ApiBundle,
) -> None:
    failed = api_bundle.client.post(
        "/api/v1/auth/google",
        data={
            "credential": "credential-" + "x" * 100,
            "g_csrf_token": "body-only",
        },
        follow_redirects=False,
    )

    _, set_cookie = login_primary(api_bundle)

    assert failed.status_code == 403, "GIS login without matching cookie must fail"
    assert f"{SESSION_COOKIE_NAME}=" in set_cookie, "response must issue the host cookie"
    assert "HttpOnly" in set_cookie, "session cookie must not be readable by JavaScript"
    assert "Secure" in set_cookie, "session cookie must be HTTPS-only"
    assert "SameSite=lax" in set_cookie, "session cookie needs explicit SameSite policy"
    assert "Domain=" not in set_cookie, "__Host- session cookies cannot set Domain"


def test_viewer_reads_ledger_but_cannot_reach_admin_or_mutate(api_bundle: ApiBundle) -> None:
    csrf, _ = login_primary(api_bundle)
    invited = api_bundle.client.post(
        "/api/v1/admin/users",
        json={"email": "viewer@gmail.com", "role": "viewer"},
        headers=mutation_headers(csrf),
    )
    viewer = api_bundle.services.store.bind_google_identity(
        google_sub="viewer-sub",
        authoritative_email="viewer@gmail.com",
        now_utc_ns=api_bundle.services.clock(),
    )
    raw_viewer_session = "viewer-session-" + "v" * 32
    api_bundle.services.store.create_session(
        user=viewer,
        raw_session_token=raw_viewer_session,
        csrf_token="viewer-csrf-" + "c" * 32,
        now_utc_ns=api_bundle.services.clock(),
        ttl_seconds=3_600,
    )
    api_bundle.client.cookies.clear()
    api_bundle.client.cookies.set(
        SESSION_COOKIE_NAME,
        raw_viewer_session,
        path="/",
    )

    ledger = api_bundle.client.get("/api/v1/ledger")
    operations = api_bundle.client.get("/api/v1/operations/status")
    users = api_bundle.client.get("/api/v1/admin/users")
    mutate = api_bundle.client.post(
        "/api/v1/admin/operations/drive-refresh",
        headers=mutation_headers("viewer-csrf-" + "c" * 32),
    )

    assert invited.status_code == 201, "admin should be able to invite viewer"
    assert ledger.status_code == 200, "viewer must retain read-only ledger access"
    assert operations.status_code == 200, "viewer may read sanitized operational status"
    assert users.status_code == 403, "viewer cannot read admin user data"
    assert mutate.status_code == 403, "viewer cannot invoke admin controls"


def test_admin_mutation_requires_exact_origin_and_csrf(api_bundle: ApiBundle) -> None:
    csrf, _ = login_primary(api_bundle)

    missing = api_bundle.client.post(
        "/api/v1/admin/users",
        json={"email": "new@gmail.com", "role": "viewer"},
    )
    wrong_origin = api_bundle.client.post(
        "/api/v1/admin/users",
        json={"email": "new@gmail.com", "role": "viewer"},
        headers={"Origin": "https://attacker.example", "X-CSRF-Token": csrf},
    )
    valid = api_bundle.client.post(
        "/api/v1/admin/users",
        json={"email": "new@gmail.com", "role": "viewer"},
        headers=mutation_headers(csrf),
    )
    coerced = api_bundle.client.patch(
        f"/api/v1/admin/users/{valid.json()['user_id']}",
        json={"enabled": "false"},
        headers=mutation_headers(csrf),
    )

    assert missing.status_code == 403, "cookie-authenticated mutation needs CSRF"
    assert wrong_origin.status_code == 403, "mutation origin must match configured origin"
    assert valid.status_code == 201, "matching origin and CSRF should authorize admin"
    assert coerced.status_code == 422, "JSON control types must not be coerced"


def test_identifier_paths_are_bounded_before_control_store_access(
    api_bundle: ApiBundle,
) -> None:
    csrf, _ = login_primary(api_bundle)

    user = api_bundle.client.patch(
        f"/api/v1/admin/users/{'a' * 65}",
        json={"role": "viewer"},
        headers=mutation_headers(csrf),
    )
    rotation = api_bundle.client.post(
        f"/api/v1/admin/key-rotations/{'a' * 33}/verify",
        headers=mutation_headers(csrf),
    )

    assert user.status_code == 422, "overlong user identifiers must fail at the API boundary"
    assert rotation.status_code == 422, (
        "overlong rotation identifiers must fail at the API boundary"
    )


def test_request_limit_checks_streamed_bytes_not_only_content_length() -> None:
    async def exercise() -> list[dict[str, Any]]:
        incoming = iter(
            [
                {"type": "http.request", "body": b"x" * 40_000, "more_body": True},
                {"type": "http.request", "body": b"x" * 30_000, "more_body": False},
            ]
        )
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return next(incoming)

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        async def consume(
            _: dict[str, Any],
            bounded_receive: Any,
            bounded_send: Any,
        ) -> None:
            more = True
            while more:
                message = await bounded_receive()
                more = bool(message.get("more_body", False))
            await bounded_send({"type": "http.response.start", "status": 204, "headers": []})
            await bounded_send({"type": "http.response.body", "body": b""})

        middleware = RequestBodyLimitMiddleware(consume, max_bytes=65_536)
        await middleware(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "POST",
                "scheme": "https",
                "path": "/api/v1/auth/google",
                "raw_path": b"/api/v1/auth/google",
                "query_string": b"",
                "root_path": "",
                "headers": [(b"content-length", b"1")],
                "server": ("testserver", 443),
                "client": ("127.0.0.1", 1),
            },
            receive,
            send,
        )
        return sent

    messages = asyncio.run(exercise())

    assert messages[0]["status"] == 413, "misreported streamed bodies must remain bounded"


def test_primary_admin_api_rejects_demotion_disable_and_removal(api_bundle: ApiBundle) -> None:
    csrf, _ = login_primary(api_bundle)

    changed = api_bundle.client.patch(
        f"/api/v1/admin/users/{PRIMARY_ADMIN_ID}",
        json={"role": "viewer", "enabled": False},
        headers=mutation_headers(csrf),
    )
    removed = api_bundle.client.delete(
        f"/api/v1/admin/users/{PRIMARY_ADMIN_ID}",
        headers=mutation_headers(csrf),
    )

    assert changed.status_code == 409, "primary admin cannot be changed"
    assert removed.status_code == 409, "primary admin cannot be removed"


def test_user_role_change_revokes_session_before_next_request(api_bundle: ApiBundle) -> None:
    csrf, _ = login_primary(api_bundle)
    invited = api_bundle.client.post(
        "/api/v1/admin/users",
        json={"email": "operator@gmail.com", "role": "viewer"},
        headers=mutation_headers(csrf),
    ).json()
    viewer = api_bundle.services.store.bind_google_identity(
        google_sub="operator-sub",
        authoritative_email="operator@gmail.com",
        now_utc_ns=api_bundle.services.clock(),
    )
    viewer_token = "operator-session-" + "o" * 32
    api_bundle.services.store.create_session(
        user=viewer,
        raw_session_token=viewer_token,
        csrf_token="operator-csrf-" + "c" * 32,
        now_utc_ns=api_bundle.services.clock(),
        ttl_seconds=3_600,
    )
    api_bundle.client.patch(
        f"/api/v1/admin/users/{invited['user_id']}",
        json={"role": "admin"},
        headers=mutation_headers(csrf),
    )
    api_bundle.client.cookies.clear()
    api_bundle.client.cookies.set(
        SESSION_COOKIE_NAME,
        viewer_token,
        path="/",
    )

    response = api_bundle.client.get("/api/v1/ledger")

    assert response.status_code == 401, "role mutation must revoke existing sessions immediately"


def test_control_operations_are_audited_and_never_claim_execution(
    api_bundle: ApiBundle,
) -> None:
    csrf, _ = login_primary(api_bundle)
    tested = api_bundle.client.post(
        "/api/v1/admin/operations/connection-tests",
        json={"target": "market_data"},
        headers=mutation_headers(csrf),
    )
    published = api_bundle.client.post(
        "/api/v1/admin/operations/drive-publish",
        headers=mutation_headers(csrf),
    )
    audit = api_bundle.client.get("/api/v1/admin/audit")

    assert tested.status_code == 200
    assert tested.json()["execution"] is False
    assert tested.json()["orders_placed"] == 0
    assert published.json()["state"] == "blocked", "blocked release must block Drive publish"
    actions = {item["action"] for item in audit.json()["records"]}
    assert "operation.connection_test.market_data.requested" in actions, (
        "external probe needs intent evidence"
    )
    assert "operation.connection_test.market_data.complete" in actions, (
        "external probe needs completion evidence"
    )


def test_key_rotation_workflow_never_accepts_secret_material(api_bundle: ApiBundle) -> None:
    csrf, _ = login_primary(api_bundle)

    rejected = api_bundle.client.post(
        "/api/v1/admin/key-rotations",
        json={"target": "databento", "secret": "must-not-enter-api"},
        headers=mutation_headers(csrf),
    )
    created = api_bundle.client.post(
        "/api/v1/admin/key-rotations",
        json={"target": "databento"},
        headers=mutation_headers(csrf),
    )
    verified = api_bundle.client.post(
        f"/api/v1/admin/key-rotations/{created.json()['rotation_id']}/verify",
        headers=mutation_headers(csrf),
    )
    audit = api_bundle.client.get("/api/v1/admin/audit").json()["records"]

    assert rejected.status_code == 422, "strict request model must reject secret fields"
    assert created.json()["state"] == "requested"
    assert verified.json()["state"] == "verified"
    assert "secret" not in str(verified.json()).casefold()
    actions = {item["action"] for item in audit}
    assert "operation.key_rotation_verify.requested" in actions, (
        "credential verification needs intent evidence before its network probe"
    )
    assert "operation.key_rotation_verify.complete" in actions, (
        "credential verification needs sanitized completion evidence"
    )


def test_only_auth_bootstrap_routes_are_public_and_no_html_app_is_served(
    api_bundle: ApiBundle,
) -> None:
    config = api_bundle.client.get("/api/v1/auth/config")
    root = api_bundle.client.get("/")
    ledger = api_bundle.client.get("/api/v1/ledger")
    docs = api_bundle.client.get("/docs")
    openapi = api_bundle.client.get("/openapi.json")

    assert config.status_code == 200, "GIS public config is the intentional bootstrap"
    assert root.status_code == 404, "FastAPI must not serve the SPA or an HTML page"
    assert ledger.status_code == 401, "ledger requires a server-side session"
    assert docs.status_code == 404, "interactive API HTML is disabled"
    assert openapi.status_code == 404, "public OpenAPI route is disabled"
    assert root.json()["schema_version"] == "dashboard-api/v1", (
        "error responses remain versioned JSON contracts"
    )


def test_status_distinguishes_release_drive_outbox_and_watchdog(api_bundle: ApiBundle) -> None:
    login_primary(api_bundle)

    response = api_bundle.client.get("/api/v1/operations/status")

    assert response.status_code == 200
    by_component = {item["component"]: item for item in response.json()["components"]}
    assert by_component["api"]["state"] == "running"
    assert by_component["release"]["state"] == "blocked"
    assert by_component["drive"]["state"] == "blocked"
    assert by_component["watchdog"]["state"] == "blocked"
    assert response.json()["outbox"]["pending_count"] == 0


def test_status_persists_only_the_last_successful_drive_activity(
    api_bundle: ApiBundle,
) -> None:
    csrf, _ = login_primary(api_bundle)
    api_bundle.authority.ledger_ready = True
    api_bundle.authority.publish_affected = 3

    refreshed = api_bundle.client.post(
        "/api/v1/admin/operations/drive-refresh",
        headers=mutation_headers(csrf),
    )
    published = api_bundle.client.post(
        "/api/v1/admin/operations/drive-publish",
        headers=mutation_headers(csrf),
    )
    successful_status = api_bundle.client.get("/api/v1/operations/status").json()

    api_bundle.authority.ledger_ready = False
    blocked = api_bundle.client.post(
        "/api/v1/admin/operations/drive-refresh",
        headers=mutation_headers(csrf),
    )
    after_blocked_status = api_bundle.client.get("/api/v1/operations/status").json()

    assert refreshed.json()["state"] == "complete"
    assert published.json()["state"] == "complete"
    assert published.json()["affected_count"] == 3
    assert successful_status["drive_activity"]["refresh"]["observed_at_utc"] is not None
    assert successful_status["drive_activity"]["publish"]["affected_count"] == 3
    assert blocked.json()["state"] == "blocked"
    assert after_blocked_status["drive_activity"] == successful_status["drive_activity"], (
        "a later blocked attempt must not replace last-successful Drive evidence"
    )


def test_drive_provider_details_are_sanitized_before_status_or_audit(
    api_bundle: ApiBundle,
) -> None:
    csrf, _ = login_primary(api_bundle)
    api_bundle.authority.drive_ready = True
    api_bundle.authority.drive_detail = "HTTP 403: private-folder-id and provider message"
    api_bundle.authority.drive_principal = "operator@workspace.example"
    api_bundle.drive_probe.ready = False
    api_bundle.drive_probe.detail = "HTTP 403: private-folder-id and provider message"

    status = api_bundle.client.get("/api/v1/operations/status")
    tested = api_bundle.client.post(
        "/api/v1/admin/operations/connection-tests",
        json={"target": "drive"},
        headers=mutation_headers(csrf),
    )
    audit = api_bundle.client.get("/api/v1/admin/audit")
    combined = f"{status.text} {tested.text} {audit.text}"

    assert "private-folder-id" not in combined
    assert "provider message" not in combined
    assert "o***@workspace.example" in status.text
    assert tested.json()["detail"] == "Drive authority connection failed"
