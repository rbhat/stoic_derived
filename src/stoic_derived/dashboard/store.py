"""Exactly verified SQLite identity, session, control, and audit state."""

from __future__ import annotations

import hmac
import json
import re
import secrets
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import closing, contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .models import Role, RotationState
from .projection import utc_string

CONTROL_SCHEMA_VERSION = 1
PRIMARY_ADMIN_EMAIL = "rajeevmbhat@gmail.com"
PRIMARY_ADMIN_ID = "primary-admin"
ZERO_HASH = "0" * 64
_EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}$")


class ControlStoreError(ValueError):
    """Raised when control state cannot be validated or safely changed."""


class AuthenticationError(ControlStoreError):
    """Raised for a generic authentication or invitation failure."""


class AuthorizationError(ControlStoreError):
    """Raised when the current role cannot perform an operation."""


class PrimaryAdminError(ControlStoreError):
    """Raised before a forbidden primary-administrator mutation."""


@dataclass(frozen=True, slots=True)
class ControlLimits:
    max_users: int = 100
    max_sessions: int = 10_000
    max_audit_records: int = 100_000
    max_rotations: int = 1_000
    max_audit_json_bytes: int = 32_768

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ControlStoreError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class StoredUser:
    user_id: str
    invited_email: str
    display_email: str
    google_sub: str | None
    role: Role
    enabled: bool
    primary: bool
    created_utc_ns: int
    updated_utc_ns: int

    def public_dict(self) -> dict[str, object]:
        return {
            "email": self.display_email,
            "enabled": self.enabled,
            "identity_bound": self.google_sub is not None,
            "primary": self.primary,
            "role": self.role.value,
            "user_id": self.user_id,
        }


@dataclass(frozen=True, slots=True)
class StoredSession:
    user: StoredUser
    csrf_token: str
    expires_utc_ns: int


@dataclass(frozen=True, slots=True)
class StoredRotation:
    rotation_id: str
    target: str
    state: RotationState
    requested_utc_ns: int
    updated_utc_ns: int
    requested_by_email: str
    detail: str


@dataclass(frozen=True, slots=True)
class StoredAuditRecord:
    audit_id: int
    occurred_utc_ns: int
    actor_email: str
    action: str
    resource_type: str
    resource_id: str
    request_id: str
    before: dict[str, object] | None
    after: dict[str, object] | None
    record_hash: str


_TABLE_DDL = {
    "users": f"""
        CREATE TABLE users(
            user_id TEXT PRIMARY KEY CHECK(length(user_id) BETWEEN 1 AND 64),
            invited_email TEXT NOT NULL CHECK(length(invited_email) BETWEEN 3 AND 320),
            display_email TEXT NOT NULL CHECK(length(display_email) BETWEEN 3 AND 320),
            google_sub TEXT CHECK(google_sub IS NULL OR length(google_sub) BETWEEN 1 AND 255),
            role TEXT NOT NULL CHECK(role IN ('admin', 'viewer')),
            enabled INTEGER NOT NULL CHECK(enabled IN (0, 1)),
            is_primary INTEGER NOT NULL CHECK(is_primary IN (0, 1)),
            created_utc_ns INTEGER NOT NULL CHECK(created_utc_ns >= 0),
            updated_utc_ns INTEGER NOT NULL CHECK(updated_utc_ns >= created_utc_ns),
            CHECK(
                is_primary = 0 OR (
                    user_id = '{PRIMARY_ADMIN_ID}' AND
                    invited_email = '{PRIMARY_ADMIN_EMAIL}' AND
                    display_email = '{PRIMARY_ADMIN_EMAIL}' AND
                    role = 'admin' AND
                    enabled = 1
                )
            )
        ) STRICT
    """,
    "sessions": """
        CREATE TABLE sessions(
            session_hash TEXT PRIMARY KEY CHECK(length(session_hash) = 64),
            user_id TEXT NOT NULL,
            csrf_token TEXT NOT NULL CHECK(length(csrf_token) BETWEEN 32 AND 128),
            created_utc_ns INTEGER NOT NULL CHECK(created_utc_ns >= 0),
            expires_utc_ns INTEGER NOT NULL CHECK(expires_utc_ns > created_utc_ns),
            revoked INTEGER NOT NULL CHECK(revoked IN (0, 1)),
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        ) STRICT
    """,
    "connection_status": """
        CREATE TABLE connection_status(
            target TEXT PRIMARY KEY CHECK(target IN ('market_data', 'drive')),
            state TEXT NOT NULL CHECK(state IN ('ready', 'blocked', 'failed')),
            detail TEXT NOT NULL CHECK(length(detail) BETWEEN 1 AND 500),
            checked_utc_ns INTEGER NOT NULL CHECK(checked_utc_ns >= 0),
            checked_by_email TEXT NOT NULL CHECK(length(checked_by_email) BETWEEN 3 AND 320)
        ) STRICT
    """,
    "drive_success": """
        CREATE TABLE drive_success(
            operation TEXT PRIMARY KEY CHECK(operation IN ('drive_refresh', 'drive_publish')),
            observed_utc_ns INTEGER NOT NULL CHECK(observed_utc_ns >= 0),
            affected_count INTEGER NOT NULL CHECK(affected_count >= 0)
        ) STRICT
    """,
    "key_rotations": """
        CREATE TABLE key_rotations(
            rotation_id TEXT PRIMARY KEY CHECK(length(rotation_id) = 32),
            target TEXT NOT NULL CHECK(target = 'databento'),
            state TEXT NOT NULL CHECK(state IN ('requested', 'verified', 'failed', 'cancelled')),
            requested_utc_ns INTEGER NOT NULL CHECK(requested_utc_ns >= 0),
            updated_utc_ns INTEGER NOT NULL CHECK(updated_utc_ns >= requested_utc_ns),
            requested_by_email TEXT NOT NULL CHECK(length(requested_by_email) BETWEEN 3 AND 320),
            detail TEXT NOT NULL CHECK(length(detail) BETWEEN 1 AND 500)
        ) STRICT
    """,
    "audit_log": """
        CREATE TABLE audit_log(
            audit_id INTEGER PRIMARY KEY CHECK(audit_id > 0),
            occurred_utc_ns INTEGER NOT NULL CHECK(occurred_utc_ns >= 0),
            actor_user_id TEXT NOT NULL CHECK(length(actor_user_id) BETWEEN 1 AND 64),
            actor_email TEXT NOT NULL CHECK(length(actor_email) BETWEEN 3 AND 320),
            action TEXT NOT NULL CHECK(length(action) BETWEEN 1 AND 100),
            resource_type TEXT NOT NULL CHECK(length(resource_type) BETWEEN 1 AND 100),
            resource_id TEXT NOT NULL CHECK(length(resource_id) BETWEEN 1 AND 128),
            request_id TEXT NOT NULL CHECK(length(request_id) BETWEEN 1 AND 128),
            before_json TEXT,
            after_json TEXT,
            previous_hash TEXT NOT NULL CHECK(length(previous_hash) = 64),
            record_hash TEXT NOT NULL CHECK(length(record_hash) = 64)
        ) STRICT
    """,
}

_INDEX_DDL = {
    "users_invited_email_uq": (
        "CREATE UNIQUE INDEX users_invited_email_uq ON users(invited_email)"
    ),
    "users_google_sub_uq": (
        "CREATE UNIQUE INDEX users_google_sub_uq ON users(google_sub) WHERE google_sub IS NOT NULL"
    ),
    "sessions_user_idx": "CREATE INDEX sessions_user_idx ON sessions(user_id)",
    "audit_record_hash_uq": ("CREATE UNIQUE INDEX audit_record_hash_uq ON audit_log(record_hash)"),
}

_TRIGGER_DDL = {
    "users_primary_update_guard": f"""
        CREATE TRIGGER users_primary_update_guard
        BEFORE UPDATE ON users
        WHEN OLD.is_primary = 1 AND (
            NEW.user_id IS NOT OLD.user_id OR
            NEW.invited_email IS NOT '{PRIMARY_ADMIN_EMAIL}' OR
            NEW.display_email IS NOT '{PRIMARY_ADMIN_EMAIL}' OR
            NEW.role IS NOT 'admin' OR
            NEW.enabled IS NOT 1 OR
            NEW.is_primary IS NOT 1 OR
            (OLD.google_sub IS NOT NULL AND NEW.google_sub IS NOT OLD.google_sub)
        )
        BEGIN
            SELECT RAISE(ABORT, 'primary administrator is immutable');
        END
    """,
    "users_primary_delete_guard": """
        CREATE TRIGGER users_primary_delete_guard
        BEFORE DELETE ON users
        WHEN OLD.is_primary = 1
        BEGIN
            SELECT RAISE(ABORT, 'primary administrator cannot be deleted');
        END
    """,
    "audit_update_guard": """
        CREATE TRIGGER audit_update_guard
        BEFORE UPDATE ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'audit log is append-only');
        END
    """,
    "audit_delete_guard": """
        CREATE TRIGGER audit_delete_guard
        BEFORE DELETE ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'audit log is append-only');
        END
    """,
}

_COUNT_SQL = {
    "users": "SELECT COUNT(*) FROM users",
    "sessions": "SELECT COUNT(*) FROM sessions",
    "audit_log": "SELECT COUNT(*) FROM audit_log",
    "key_rotations": "SELECT COUNT(*) FROM key_rotations",
}


def normalize_email(value: str) -> str:
    if not isinstance(value, str):
        raise ControlStoreError("email must be a string")
    normalized = value.strip().casefold()
    if (
        not _EMAIL_PATTERN.fullmatch(normalized)
        or ".." in normalized
        or normalized.startswith(".")
        or normalized.endswith(".")
    ):
        raise ControlStoreError("email must be a valid bounded address")
    return normalized


def session_digest(raw_token: str) -> str:
    if not isinstance(raw_token, str) or not 32 <= len(raw_token) <= 256:
        raise AuthenticationError("invalid session")
    return sha256(raw_token.encode("utf-8")).hexdigest()


def _canonical_json(value: Mapping[str, object] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _safe_detail(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        return "Operation did not return a detail"
    return cleaned[:500]


class DashboardStore:
    """Portable transactional store with immutable primary and audit evidence."""

    def __init__(self, path: Path, *, limits: ControlLimits | None = None) -> None:
        if not isinstance(path, Path):
            raise ControlStoreError("path must be a pathlib.Path")
        self._path = path
        self._limits = limits or ControlLimits()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @property
    def path(self) -> Path:
        return self._path

    def list_users(self) -> tuple[StoredUser, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM users ORDER BY is_primary DESC, invited_email"
            ).fetchall()
        return tuple(self._user_from_row(row) for row in rows)

    def get_user(self, user_id: str) -> StoredUser:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            raise ControlStoreError("user not found")
        return self._user_from_row(row)

    def invite_user(
        self,
        *,
        actor: StoredUser,
        email: str,
        role: Role,
        now_utc_ns: int,
        request_id: str,
    ) -> StoredUser:
        self._require_admin(actor)
        normalized = normalize_email(email)
        if not isinstance(role, Role):
            raise ControlStoreError("role must be admin or viewer")
        user_id = secrets.token_hex(16)
        with self._transaction() as connection:
            self._ensure_count_below(connection, "users", self._limits.max_users)
            existing = connection.execute(
                "SELECT user_id FROM users WHERE invited_email = ?", (normalized,)
            ).fetchone()
            if existing is not None:
                raise ControlStoreError("email is already invited")
            connection.execute(
                """
                INSERT INTO users(
                    user_id, invited_email, display_email, google_sub, role,
                    enabled, is_primary, created_utc_ns, updated_utc_ns
                ) VALUES (?, ?, ?, NULL, ?, 1, 0, ?, ?)
                """,
                (user_id, normalized, normalized, role.value, now_utc_ns, now_utc_ns),
            )
            created = self._user_by_id(connection, user_id)
            self._append_audit(
                connection,
                actor=actor,
                action="user.invited",
                resource_type="user",
                resource_id=user_id,
                request_id=request_id,
                now_utc_ns=now_utc_ns,
                before=None,
                after=created.public_dict(),
            )
        return created

    def update_user(
        self,
        *,
        actor: StoredUser,
        user_id: str,
        role: Role | None,
        enabled: bool | None,
        now_utc_ns: int,
        request_id: str,
    ) -> StoredUser:
        self._require_admin(actor)
        with self._transaction() as connection:
            before = self._user_by_id(connection, user_id)
            if before.primary:
                raise PrimaryAdminError("primary administrator cannot be changed")
            selected_role = role or before.role
            selected_enabled = before.enabled if enabled is None else enabled
            connection.execute(
                """
                UPDATE users
                   SET role = ?, enabled = ?, updated_utc_ns = ?
                 WHERE user_id = ?
                """,
                (selected_role.value, int(selected_enabled), now_utc_ns, user_id),
            )
            connection.execute("UPDATE sessions SET revoked = 1 WHERE user_id = ?", (user_id,))
            updated = self._user_by_id(connection, user_id)
            self._append_audit(
                connection,
                actor=actor,
                action="user.updated",
                resource_type="user",
                resource_id=user_id,
                request_id=request_id,
                now_utc_ns=now_utc_ns,
                before=before.public_dict(),
                after=updated.public_dict(),
            )
        return updated

    def remove_user(
        self,
        *,
        actor: StoredUser,
        user_id: str,
        now_utc_ns: int,
        request_id: str,
    ) -> StoredUser:
        self._require_admin(actor)
        with self._transaction() as connection:
            removed = self._user_by_id(connection, user_id)
            if removed.primary:
                raise PrimaryAdminError("primary administrator cannot be removed")
            connection.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            self._append_audit(
                connection,
                actor=actor,
                action="user.removed",
                resource_type="user",
                resource_id=user_id,
                request_id=request_id,
                now_utc_ns=now_utc_ns,
                before=removed.public_dict(),
                after=None,
            )
        return removed

    def bind_google_identity(
        self,
        *,
        google_sub: str,
        authoritative_email: str,
        now_utc_ns: int,
    ) -> StoredUser:
        if not google_sub or len(google_sub) > 255:
            raise AuthenticationError("access denied")
        normalized = normalize_email(authoritative_email)
        with self._transaction() as connection:
            by_sub = connection.execute(
                "SELECT * FROM users WHERE google_sub = ?", (google_sub,)
            ).fetchone()
            if by_sub is not None:
                user = self._user_from_row(by_sub)
                if not user.enabled:
                    raise AuthenticationError("access denied")
                if user.primary and normalized != PRIMARY_ADMIN_EMAIL:
                    raise AuthenticationError("access denied")
                if not user.primary and user.display_email != normalized:
                    connection.execute(
                        """
                        UPDATE users
                           SET display_email = ?, updated_utc_ns = ?
                         WHERE user_id = ?
                        """,
                        (normalized, now_utc_ns, user.user_id),
                    )
                return self._user_by_id(connection, user.user_id)

            by_email = connection.execute(
                "SELECT * FROM users WHERE invited_email = ?", (normalized,)
            ).fetchone()
            if by_email is None:
                raise AuthenticationError("access denied")
            invited = self._user_from_row(by_email)
            if not invited.enabled or invited.google_sub is not None:
                raise AuthenticationError("access denied")
            try:
                connection.execute(
                    """
                    UPDATE users
                       SET google_sub = ?, display_email = ?, updated_utc_ns = ?
                     WHERE user_id = ?
                    """,
                    (google_sub, normalized, now_utc_ns, invited.user_id),
                )
            except sqlite3.IntegrityError as exc:
                raise AuthenticationError("access denied") from exc
            return self._user_by_id(connection, invited.user_id)

    def create_session(
        self,
        *,
        user: StoredUser,
        raw_session_token: str,
        csrf_token: str,
        now_utc_ns: int,
        ttl_seconds: int,
    ) -> StoredSession:
        digest = session_digest(raw_session_token)
        if not 32 <= len(csrf_token) <= 128:
            raise ControlStoreError("csrf_token must be a bounded random token")
        expires = now_utc_ns + ttl_seconds * 1_000_000_000
        with self._transaction() as connection:
            current = self._user_by_id(connection, user.user_id)
            if not current.enabled:
                raise AuthenticationError("access denied")
            connection.execute(
                "DELETE FROM sessions WHERE revoked = 1 OR expires_utc_ns <= ?",
                (now_utc_ns,),
            )
            connection.execute("UPDATE sessions SET revoked = 1 WHERE user_id = ?", (user.user_id,))
            self._ensure_count_below(connection, "sessions", self._limits.max_sessions)
            connection.execute(
                """
                INSERT INTO sessions(
                    session_hash, user_id, csrf_token, created_utc_ns, expires_utc_ns, revoked
                ) VALUES (?, ?, ?, ?, ?, 0)
                """,
                (digest, user.user_id, csrf_token, now_utc_ns, expires),
            )
        return StoredSession(current, csrf_token, expires)

    def resolve_session(self, raw_session_token: str, *, now_utc_ns: int) -> StoredSession:
        digest = session_digest(raw_session_token)
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT s.csrf_token, s.expires_utc_ns, s.revoked, u.*
                  FROM sessions AS s
                  JOIN users AS u ON u.user_id = s.user_id
                 WHERE s.session_hash = ?
                """,
                (digest,),
            ).fetchone()
        if (
            row is None
            or int(row["revoked"]) != 0
            or int(row["expires_utc_ns"]) <= now_utc_ns
            or int(row["enabled"]) != 1
        ):
            raise AuthenticationError("invalid session")
        user = self._user_from_row(row)
        return StoredSession(
            user=user,
            csrf_token=str(row["csrf_token"]),
            expires_utc_ns=int(row["expires_utc_ns"]),
        )

    def revoke_session(self, raw_session_token: str) -> None:
        digest = session_digest(raw_session_token)
        with self._transaction() as connection:
            connection.execute("UPDATE sessions SET revoked = 1 WHERE session_hash = ?", (digest,))

    def record_operation_intent(
        self,
        *,
        actor: StoredUser,
        operation_id: str,
        operation: str,
        now_utc_ns: int,
        request_id: str,
    ) -> None:
        self._require_admin(actor)
        with self._transaction() as connection:
            self._append_audit(
                connection,
                actor=actor,
                action=f"operation.{operation}.requested",
                resource_type="operation",
                resource_id=operation_id,
                request_id=request_id,
                now_utc_ns=now_utc_ns,
                before=None,
                after={"operation": operation, "state": "requested"},
            )

    def record_operation_result(
        self,
        *,
        actor: StoredUser,
        operation_id: str,
        operation: str,
        state: str,
        detail: str,
        now_utc_ns: int,
        request_id: str,
        connection_target: str | None = None,
        affected_count: int = 0,
    ) -> None:
        self._require_admin(actor)
        safe_detail = _safe_detail(detail)
        if state not in {"complete", "blocked", "failed"}:
            raise ControlStoreError("invalid operation result state")
        if (
            not isinstance(affected_count, int)
            or isinstance(affected_count, bool)
            or affected_count < 0
        ):
            raise ControlStoreError("affected_count must be a non-negative integer")
        with self._transaction() as connection:
            if connection_target is not None:
                if connection_target not in {"market_data", "drive"}:
                    raise ControlStoreError("invalid connection target")
                probe_state = "ready" if state == "complete" else state
                connection.execute(
                    """
                    INSERT INTO connection_status(
                        target, state, detail, checked_utc_ns, checked_by_email
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(target) DO UPDATE SET
                        state = excluded.state,
                        detail = excluded.detail,
                        checked_utc_ns = excluded.checked_utc_ns,
                        checked_by_email = excluded.checked_by_email
                    """,
                    (
                        connection_target,
                        probe_state,
                        safe_detail,
                        now_utc_ns,
                        actor.display_email,
                    ),
                )
            if state == "complete" and operation in {"drive_refresh", "drive_publish"}:
                connection.execute(
                    """
                    INSERT INTO drive_success(operation, observed_utc_ns, affected_count)
                    VALUES (?, ?, ?)
                    ON CONFLICT(operation) DO UPDATE SET
                        observed_utc_ns = excluded.observed_utc_ns,
                        affected_count = excluded.affected_count
                    """,
                    (operation, now_utc_ns, affected_count),
                )
            self._append_audit(
                connection,
                actor=actor,
                action=f"operation.{operation}.{state}",
                resource_type="operation",
                resource_id=operation_id,
                request_id=request_id,
                now_utc_ns=now_utc_ns,
                before={"state": "requested"},
                after={
                    "affected_count": affected_count,
                    "detail": safe_detail,
                    "operation": operation,
                    "state": state,
                },
            )

    def connection_status(self) -> dict[str, tuple[str, str, int]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT target, state, detail, checked_utc_ns FROM connection_status"
            ).fetchall()
        return {
            str(row["target"]): (
                str(row["state"]),
                str(row["detail"]),
                int(row["checked_utc_ns"]),
            )
            for row in rows
        }

    def drive_success_status(self) -> dict[str, tuple[int, int]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT operation, observed_utc_ns, affected_count FROM drive_success"
            ).fetchall()
        return {
            str(row["operation"]): (
                int(row["observed_utc_ns"]),
                int(row["affected_count"]),
            )
            for row in rows
        }

    def create_rotation(
        self,
        *,
        actor: StoredUser,
        target: str,
        now_utc_ns: int,
        request_id: str,
    ) -> StoredRotation:
        self._require_admin(actor)
        if target != "databento":
            raise ControlStoreError("unsupported rotation target")
        rotation_id = secrets.token_hex(16)
        detail = "Update the Databento secret outside the dashboard, then verify it here."
        with self._transaction() as connection:
            self._ensure_count_below(
                connection,
                "key_rotations",
                self._limits.max_rotations,
            )
            open_row = connection.execute(
                """
                SELECT rotation_id
                  FROM key_rotations
                 WHERE target = ? AND state = 'requested'
                """,
                (target,),
            ).fetchone()
            if open_row is not None:
                raise ControlStoreError("an open Databento rotation already exists")
            connection.execute(
                """
                INSERT INTO key_rotations(
                    rotation_id, target, state, requested_utc_ns, updated_utc_ns,
                    requested_by_email, detail
                ) VALUES (?, ?, 'requested', ?, ?, ?, ?)
                """,
                (
                    rotation_id,
                    target,
                    now_utc_ns,
                    now_utc_ns,
                    actor.display_email,
                    detail,
                ),
            )
            rotation = self._rotation_by_id(connection, rotation_id)
            self._append_audit(
                connection,
                actor=actor,
                action="key_rotation.requested",
                resource_type="key_rotation",
                resource_id=rotation_id,
                request_id=request_id,
                now_utc_ns=now_utc_ns,
                before=None,
                after=self._rotation_public(rotation),
            )
        return rotation

    def finish_rotation(
        self,
        *,
        actor: StoredUser,
        rotation_id: str,
        state: RotationState,
        detail: str,
        now_utc_ns: int,
        request_id: str,
    ) -> StoredRotation:
        self._require_admin(actor)
        if state not in {
            RotationState.VERIFIED,
            RotationState.FAILED,
            RotationState.CANCELLED,
        }:
            raise ControlStoreError("rotation can only finish with a terminal state")
        with self._transaction() as connection:
            before = self._rotation_by_id(connection, rotation_id)
            if before.state is not RotationState.REQUESTED:
                raise ControlStoreError("rotation is already terminal")
            connection.execute(
                """
                UPDATE key_rotations
                   SET state = ?, detail = ?, updated_utc_ns = ?
                 WHERE rotation_id = ?
                """,
                (state.value, _safe_detail(detail), now_utc_ns, rotation_id),
            )
            updated = self._rotation_by_id(connection, rotation_id)
            self._append_audit(
                connection,
                actor=actor,
                action=f"key_rotation.{state.value}",
                resource_type="key_rotation",
                resource_id=rotation_id,
                request_id=request_id,
                now_utc_ns=now_utc_ns,
                before=self._rotation_public(before),
                after=self._rotation_public(updated),
            )
        return updated

    def list_rotations(self) -> tuple[StoredRotation, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM key_rotations ORDER BY requested_utc_ns DESC, rotation_id"
            ).fetchall()
        return tuple(self._rotation_from_row(row) for row in rows)

    def get_rotation(self, rotation_id: str) -> StoredRotation:
        with closing(self._connect()) as connection:
            return self._rotation_by_id(connection, rotation_id)

    def list_audit(self, *, limit: int) -> tuple[StoredAuditRecord, ...]:
        if not 1 <= limit <= 200:
            raise ControlStoreError("audit limit must be from 1 through 200")
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM audit_log ORDER BY audit_id DESC LIMIT ?", (limit,)
            ).fetchall()
        return tuple(self._audit_from_row(row) for row in rows)

    def verify_audit_chain(self) -> None:
        with closing(self._connect()) as connection:
            self._verify_audit_chain(connection)

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            journal_mode = str(connection.execute("PRAGMA journal_mode=WAL").fetchone()[0])
            if journal_mode.lower() != "wal":
                raise ControlStoreError("dashboard SQLite requires WAL journal mode")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=FULL")
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version not in {0, CONTROL_SCHEMA_VERSION}:
                raise ControlStoreError("unsupported dashboard SQLite schema version")
            if version == 0:
                for ddl in _TABLE_DDL.values():
                    connection.execute(
                        ddl.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1)
                    )
                for ddl in _INDEX_DDL.values():
                    connection.execute(
                        ddl.replace("CREATE ", "CREATE ", 1).replace(
                            " INDEX ", " INDEX IF NOT EXISTS ", 1
                        )
                    )
                for ddl in _TRIGGER_DDL.values():
                    connection.execute(
                        ddl.replace("CREATE TRIGGER ", "CREATE TRIGGER IF NOT EXISTS ", 1)
                    )
                self._verify_schema(connection)
                connection.execute(f"PRAGMA user_version={CONTROL_SCHEMA_VERSION}")
            else:
                self._verify_schema(connection)
            connection.execute(
                """
                INSERT OR IGNORE INTO users(
                    user_id, invited_email, display_email, google_sub, role,
                    enabled, is_primary, created_utc_ns, updated_utc_ns
                ) VALUES (?, ?, ?, NULL, 'admin', 1, 1, 0, 0)
                """,
                (PRIMARY_ADMIN_ID, PRIMARY_ADMIN_EMAIL, PRIMARY_ADMIN_EMAIL),
            )
            primary = self._user_by_id(connection, PRIMARY_ADMIN_ID)
            if (
                primary.invited_email != PRIMARY_ADMIN_EMAIL
                or primary.display_email != PRIMARY_ADMIN_EMAIL
                or primary.role is not Role.ADMIN
                or not primary.enabled
                or not primary.primary
            ):
                raise ControlStoreError("primary administrator invariant is not satisfied")
            self._verify_audit_chain(connection)
            connection.commit()

    @staticmethod
    def _normalize_ddl(ddl: str) -> str:
        return " ".join(ddl.split())

    @classmethod
    def _verify_schema(cls, connection: sqlite3.Connection) -> None:
        expected: dict[tuple[str, str], str] = {}
        for name, ddl in _TABLE_DDL.items():
            expected[("table", name)] = cls._normalize_ddl(ddl)
        for name, ddl in _INDEX_DDL.items():
            expected[("index", name)] = cls._normalize_ddl(ddl)
        for name, ddl in _TRIGGER_DDL.items():
            expected[("trigger", name)] = cls._normalize_ddl(ddl)
        rows = connection.execute(
            """
            SELECT type, name, sql
              FROM sqlite_master
             WHERE type IN ('table', 'index', 'trigger')
            """
        ).fetchall()
        actual = {
            (str(row["type"]), str(row["name"])): cls._normalize_ddl(str(row["sql"]))
            for row in rows
            if row["sql"] is not None and (str(row["type"]), str(row["name"])) in expected
        }
        if actual != expected:
            raise ControlStoreError("dashboard SQLite declared schema mismatch")
        table_rows = connection.execute("PRAGMA table_list").fetchall()
        strict_by_name = {str(row["name"]): int(row["strict"]) for row in table_rows}
        if any(strict_by_name.get(name) != 1 for name in _TABLE_DDL):
            raise ControlStoreError("dashboard SQLite tables must all be STRICT")
        foreign_keys = connection.execute("PRAGMA foreign_key_list(sessions)").fetchall()
        if len(foreign_keys) != 1 or (
            str(foreign_keys[0]["table"]),
            str(foreign_keys[0]["from"]),
            str(foreign_keys[0]["to"]),
            str(foreign_keys[0]["on_delete"]),
        ) != ("users", "user_id", "user_id", "CASCADE"):
            raise ControlStoreError("dashboard session foreign-key schema mismatch")

    def _append_audit(
        self,
        connection: sqlite3.Connection,
        *,
        actor: StoredUser,
        action: str,
        resource_type: str,
        resource_id: str,
        request_id: str,
        now_utc_ns: int,
        before: Mapping[str, object] | None,
        after: Mapping[str, object] | None,
    ) -> None:
        self._ensure_count_below(
            connection,
            "audit_log",
            self._limits.max_audit_records,
        )
        for name, value, maximum in (
            ("action", action, 100),
            ("resource_type", resource_type, 100),
            ("resource_id", resource_id, 128),
            ("request_id", request_id, 128),
        ):
            if not value or len(value) > maximum:
                raise ControlStoreError(f"{name} must be non-empty and bounded")
        before_json = _canonical_json(before)
        after_json = _canonical_json(after)
        for audit_json in (before_json, after_json):
            if (
                audit_json is not None
                and len(audit_json.encode("utf-8")) > self._limits.max_audit_json_bytes
            ):
                raise ControlStoreError("audit JSON exceeds max_audit_json_bytes")
        self._reject_sensitive_audit(before)
        self._reject_sensitive_audit(after)
        row = connection.execute(
            "SELECT audit_id, record_hash FROM audit_log ORDER BY audit_id DESC LIMIT 1"
        ).fetchone()
        audit_id = 1 if row is None else int(row["audit_id"]) + 1
        previous_hash = ZERO_HASH if row is None else str(row["record_hash"])
        content = {
            "action": action,
            "actor_email": actor.display_email,
            "actor_user_id": actor.user_id,
            "after_json": after_json,
            "audit_id": audit_id,
            "before_json": before_json,
            "occurred_utc_ns": now_utc_ns,
            "previous_hash": previous_hash,
            "request_id": request_id,
            "resource_id": resource_id,
            "resource_type": resource_type,
        }
        record_hash = sha256(
            json.dumps(
                content,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        connection.execute(
            """
            INSERT INTO audit_log(
                audit_id, occurred_utc_ns, actor_user_id, actor_email, action,
                resource_type, resource_id, request_id, before_json, after_json,
                previous_hash, record_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_id,
                now_utc_ns,
                actor.user_id,
                actor.display_email,
                action,
                resource_type,
                resource_id,
                request_id,
                before_json,
                after_json,
                previous_hash,
                record_hash,
            ),
        )

    @staticmethod
    def _reject_sensitive_audit(value: Mapping[str, object] | None) -> None:
        if value is None:
            return
        forbidden = (
            "csrf",
            "cookie",
            "credential",
            "id_token",
            "session_token",
            "secret",
            "google_sub",
        )

        def visit(item: object) -> None:
            if isinstance(item, Mapping):
                for key, child in item.items():
                    lowered = str(key).casefold()
                    if any(word in lowered for word in forbidden):
                        raise ControlStoreError("sensitive fields cannot enter audit data")
                    visit(child)
            elif isinstance(item, (list, tuple)):
                for child in item:
                    visit(child)

        visit(value)

    def _verify_audit_chain(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute("SELECT * FROM audit_log ORDER BY audit_id").fetchall()
        if len(rows) > self._limits.max_audit_records:
            raise ControlStoreError("audit rows exceed max_audit_records")
        previous_hash = ZERO_HASH
        expected_id = 1
        for row in rows:
            audit_id = int(row["audit_id"])
            if audit_id != expected_id or str(row["previous_hash"]) != previous_hash:
                raise ControlStoreError("audit chain sequence or predecessor mismatch")
            content = {
                "action": str(row["action"]),
                "actor_email": str(row["actor_email"]),
                "actor_user_id": str(row["actor_user_id"]),
                "after_json": row["after_json"],
                "audit_id": audit_id,
                "before_json": row["before_json"],
                "occurred_utc_ns": int(row["occurred_utc_ns"]),
                "previous_hash": previous_hash,
                "request_id": str(row["request_id"]),
                "resource_id": str(row["resource_id"]),
                "resource_type": str(row["resource_type"]),
            }
            expected_hash = sha256(
                json.dumps(
                    content,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            if not hmac.compare_digest(expected_hash, str(row["record_hash"])):
                raise ControlStoreError("audit record hash mismatch")
            previous_hash = str(row["record_hash"])
            expected_id += 1

    @staticmethod
    def _ensure_count_below(
        connection: sqlite3.Connection,
        table: str,
        maximum: int,
    ) -> None:
        query = _COUNT_SQL.get(table)
        if query is None:
            raise ControlStoreError("unsupported bounded table")
        count = int(connection.execute(query).fetchone()[0])
        if count >= maximum:
            raise ControlStoreError(f"{table} reached its configured row limit")

    @staticmethod
    def _require_admin(user: StoredUser) -> None:
        if not user.enabled or user.role is not Role.ADMIN:
            raise AuthorizationError("administrator access is required")

    @classmethod
    def _user_from_row(cls, row: sqlite3.Row) -> StoredUser:
        return StoredUser(
            user_id=str(row["user_id"]),
            invited_email=str(row["invited_email"]),
            display_email=str(row["display_email"]),
            google_sub=None if row["google_sub"] is None else str(row["google_sub"]),
            role=Role(str(row["role"])),
            enabled=bool(row["enabled"]),
            primary=bool(row["is_primary"]),
            created_utc_ns=int(row["created_utc_ns"]),
            updated_utc_ns=int(row["updated_utc_ns"]),
        )

    @classmethod
    def _user_by_id(cls, connection: sqlite3.Connection, user_id: str) -> StoredUser:
        row = connection.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            raise ControlStoreError("user not found")
        return cls._user_from_row(row)

    @staticmethod
    def _rotation_from_row(row: sqlite3.Row) -> StoredRotation:
        return StoredRotation(
            rotation_id=str(row["rotation_id"]),
            target=str(row["target"]),
            state=RotationState(str(row["state"])),
            requested_utc_ns=int(row["requested_utc_ns"]),
            updated_utc_ns=int(row["updated_utc_ns"]),
            requested_by_email=str(row["requested_by_email"]),
            detail=str(row["detail"]),
        )

    @classmethod
    def _rotation_by_id(
        cls,
        connection: sqlite3.Connection,
        rotation_id: str,
    ) -> StoredRotation:
        row = connection.execute(
            "SELECT * FROM key_rotations WHERE rotation_id = ?", (rotation_id,)
        ).fetchone()
        if row is None:
            raise ControlStoreError("rotation not found")
        return cls._rotation_from_row(row)

    @staticmethod
    def _rotation_public(rotation: StoredRotation) -> dict[str, object]:
        return {
            "detail": rotation.detail,
            "requested_at_utc": utc_string(rotation.requested_utc_ns),
            "requested_by_email": rotation.requested_by_email,
            "rotation_id": rotation.rotation_id,
            "state": rotation.state.value,
            "target": rotation.target,
            "updated_at_utc": utc_string(rotation.updated_utc_ns),
        }

    @staticmethod
    def _audit_from_row(row: sqlite3.Row) -> StoredAuditRecord:
        before = json.loads(str(row["before_json"])) if row["before_json"] is not None else None
        after = json.loads(str(row["after_json"])) if row["after_json"] is not None else None
        if before is not None and not isinstance(before, dict):
            raise ControlStoreError("audit before_json must decode to an object")
        if after is not None and not isinstance(after, dict):
            raise ControlStoreError("audit after_json must decode to an object")
        return StoredAuditRecord(
            audit_id=int(row["audit_id"]),
            occurred_utc_ns=int(row["occurred_utc_ns"]),
            actor_email=str(row["actor_email"]),
            action=str(row["action"]),
            resource_type=str(row["resource_type"]),
            resource_id=str(row["resource_id"]),
            request_id=str(row["request_id"]),
            before=before,
            after=after,
            record_hash=str(row["record_hash"]),
        )

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        return connection


__all__ = [
    "CONTROL_SCHEMA_VERSION",
    "PRIMARY_ADMIN_EMAIL",
    "PRIMARY_ADMIN_ID",
    "AuthenticationError",
    "AuthorizationError",
    "ControlLimits",
    "ControlStoreError",
    "DashboardStore",
    "PrimaryAdminError",
    "StoredAuditRecord",
    "StoredRotation",
    "StoredSession",
    "StoredUser",
    "normalize_email",
    "session_digest",
]
