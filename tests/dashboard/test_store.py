from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from stoic_derived.dashboard.models import Role
from stoic_derived.dashboard.store import (
    PRIMARY_ADMIN_EMAIL,
    PRIMARY_ADMIN_ID,
    AuthenticationError,
    ControlStoreError,
    DashboardStore,
    PrimaryAdminError,
)

NOW_NS = 1_774_099_200_000_000_000


def make_store(tmp_path: Path) -> DashboardStore:
    return DashboardStore(tmp_path / "dashboard.sqlite3")


def test_primary_admin_is_bootstrapped_and_cannot_be_changed_through_service(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path)
    primary = store.get_user(PRIMARY_ADMIN_ID)

    with pytest.raises(PrimaryAdminError, match="cannot be changed"):
        store.update_user(
            actor=primary,
            user_id=primary.user_id,
            role=Role.VIEWER,
            enabled=False,
            now_utc_ns=NOW_NS,
            request_id="request-primary-update",
        )

    with pytest.raises(PrimaryAdminError, match="cannot be removed"):
        store.remove_user(
            actor=primary,
            user_id=primary.user_id,
            now_utc_ns=NOW_NS,
            request_id="request-primary-delete",
        )


def test_primary_admin_trigger_rejects_direct_sql_mutation_and_delete(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    connection = sqlite3.connect(store.path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE users SET role = 'viewer' WHERE user_id = ?",
                (PRIMARY_ADMIN_ID,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="cannot be deleted"):
            connection.execute("DELETE FROM users WHERE user_id = ?", (PRIMARY_ADMIN_ID,))
    finally:
        connection.close()

    assert store.get_user(PRIMARY_ADMIN_ID).role is Role.ADMIN, (
        "direct SQL must leave primary role unchanged"
    )


def test_first_login_binds_sub_and_different_sub_cannot_take_invitation(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    bound = store.bind_google_identity(
        google_sub="primary-google-sub",
        authoritative_email=PRIMARY_ADMIN_EMAIL,
        now_utc_ns=NOW_NS,
    )

    with pytest.raises(AuthenticationError, match="access denied"):
        store.bind_google_identity(
            google_sub="attacker-sub",
            authoritative_email=PRIMARY_ADMIN_EMAIL,
            now_utc_ns=NOW_NS + 1,
        )

    assert bound.google_sub == "primary-google-sub", (
        "first authoritative login must bind the durable sub"
    )


def test_role_change_revokes_existing_session_immediately(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    primary = store.get_user(PRIMARY_ADMIN_ID)
    viewer = store.invite_user(
        actor=primary,
        email="viewer@gmail.com",
        role=Role.VIEWER,
        now_utc_ns=NOW_NS,
        request_id="invite-viewer",
    )
    viewer = store.bind_google_identity(
        google_sub="viewer-sub",
        authoritative_email="viewer@gmail.com",
        now_utc_ns=NOW_NS + 1,
    )
    store.create_session(
        user=viewer,
        raw_session_token="s" * 43,
        csrf_token="c" * 43,
        now_utc_ns=NOW_NS + 2,
        ttl_seconds=3_600,
    )

    store.update_user(
        actor=primary,
        user_id=viewer.user_id,
        role=Role.ADMIN,
        enabled=True,
        now_utc_ns=NOW_NS + 3,
        request_id="promote-viewer",
    )

    with pytest.raises(AuthenticationError, match="invalid session"):
        store.resolve_session("s" * 43, now_utc_ns=NOW_NS + 4)


def test_raw_session_token_is_not_stored_and_audit_is_append_only(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    primary = store.bind_google_identity(
        google_sub="primary-sub",
        authoritative_email=PRIMARY_ADMIN_EMAIL,
        now_utc_ns=NOW_NS,
    )
    raw_session = "opaque-session-token-" + "x" * 32
    store.create_session(
        user=primary,
        raw_session_token=raw_session,
        csrf_token="csrf-" + "y" * 32,
        now_utc_ns=NOW_NS + 1,
        ttl_seconds=3_600,
    )
    store.invite_user(
        actor=primary,
        email="viewer@gmail.com",
        role=Role.VIEWER,
        now_utc_ns=NOW_NS + 2,
        request_id="invite-for-audit",
    )

    connection = sqlite3.connect(store.path)
    try:
        stored = str(connection.execute("SELECT session_hash FROM sessions").fetchone()[0])
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("UPDATE audit_log SET action = 'changed'")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM audit_log")
    finally:
        connection.close()

    assert raw_session not in stored, "only a one-way session digest may be stored"
    assert len(stored) == 64, "session digest should be SHA-256"
    store.verify_audit_chain()


def test_startup_rejects_missing_schema_trigger(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    connection = sqlite3.connect(store.path)
    try:
        connection.execute("DROP TRIGGER users_primary_delete_guard")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ControlStoreError, match="declared schema mismatch"):
        DashboardStore(store.path)
