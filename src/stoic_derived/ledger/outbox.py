"""Crash-tolerant SQLite outbox and local watchdog fencing."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .model import LedgerError, LedgerEvent, LedgerLimits

OUTBOX_SCHEMA_VERSION = 1

_TABLE_DDL = {
    "events": """
        CREATE TABLE events(
            event_id TEXT PRIMARY KEY,
            signal_type TEXT NOT NULL,
            source_partition TEXT NOT NULL,
            payload BLOB NOT NULL,
            payload_sha256 TEXT NOT NULL
        ) STRICT
    """,
    "deliveries": """
        CREATE TABLE deliveries(
            event_id TEXT PRIMARY KEY REFERENCES events(event_id),
            remote_file_id TEXT,
            delivered INTEGER NOT NULL DEFAULT 0 CHECK(delivered IN (0, 1)),
            attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
            last_error TEXT
        ) STRICT
    """,
    "leases": """
        CREATE TABLE leases(
            lease_key TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            fence_token INTEGER NOT NULL CHECK(fence_token > 0),
            expires_utc_ns INTEGER NOT NULL CHECK(expires_utc_ns >= 0)
        ) STRICT
    """,
}


class OutboxError(LedgerError):
    """Raised when durable local transport state cannot be trusted."""


class LeaseBusyError(OutboxError):
    """Raised when another live local watchdog holder owns the lease."""


class StaleFenceError(OutboxError):
    """Raised when a stale watchdog attempts to enqueue events."""


@dataclass(frozen=True, slots=True)
class PendingDelivery:
    """One committed event awaiting verified Drive publication."""

    event_id: str
    signal_type: str
    source_partition: str
    payload: bytes
    remote_file_id: str | None
    attempts: int


@dataclass(frozen=True, slots=True)
class AcknowledgedDelivery:
    """One locally acknowledged event that must still exist at its exact Drive ID."""

    event_id: str
    signal_type: str
    source_partition: str
    payload: bytes
    remote_file_id: str


class LedgerOutbox:
    """SQLite-backed atomic event and delivery queue."""

    def __init__(self, path: Path, *, limits: LedgerLimits | None = None) -> None:
        if not isinstance(path, Path):
            raise OutboxError("path must be a pathlib.Path")
        self._path = path
        self._limits = limits or LedgerLimits()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @property
    def path(self) -> Path:
        return self._path

    def enqueue(
        self,
        events: Iterable[LedgerEvent],
        *,
        lease_key: str | None = None,
        fence_token: int | None = None,
    ) -> tuple[str, ...]:
        """Atomically commit immutable event bytes and outbound deliveries."""
        values = tuple(events)
        if any(not isinstance(event, LedgerEvent) for event in values):
            raise OutboxError("events must contain LedgerEvent values")
        if (lease_key is None) != (fence_token is None):
            raise OutboxError("lease_key and fence_token must be supplied together")
        ordered = tuple(
            sorted(
                {event.event_id: event for event in values}.values(),
                key=lambda event: event.event_id,
            )
        )
        for event in ordered:
            if len(event.canonical_bytes()) > self._limits.max_event_bytes:
                raise OutboxError("event exceeds max_event_bytes")

        inserted: list[str] = []
        with self._transaction() as connection:
            if lease_key is not None and fence_token is not None:
                self._assert_fence(connection, lease_key, fence_token)
            current_count = int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])
            missing_count = 0
            for event in ordered:
                row = connection.execute(
                    "SELECT payload FROM events WHERE event_id = ?", (event.event_id,)
                ).fetchone()
                if row is None:
                    missing_count += 1
                elif bytes(row[0]) != event.canonical_bytes():
                    raise OutboxError("event_id collision with different durable bytes")
            if current_count + missing_count > self._limits.max_outbox_rows:
                raise OutboxError("outbox rows exceed max_outbox_rows")

            for event in ordered:
                payload = event.canonical_bytes()
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO events(
                        event_id, signal_type, source_partition, payload, payload_sha256
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.signal_type.value,
                        event.source_partition,
                        payload,
                        sha256(payload).hexdigest(),
                    ),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO deliveries(
                        event_id, remote_file_id, delivered, attempts, last_error
                    ) VALUES (?, NULL, 0, 0, NULL)
                    """,
                    (event.event_id,),
                )
                if cursor.rowcount:
                    inserted.append(event.event_id)
        return tuple(inserted)

    def pending(self, *, limit: int | None = None) -> tuple[PendingDelivery, ...]:
        """Return a stable bounded delivery batch without changing its state."""
        selected_limit = limit or self._limits.max_dispatch_batch
        if (
            not isinstance(selected_limit, int)
            or isinstance(selected_limit, bool)
            or selected_limit <= 0
            or selected_limit > self._limits.max_dispatch_batch
        ):
            raise OutboxError("limit must be within max_dispatch_batch")
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT e.event_id, e.signal_type, e.source_partition, e.payload,
                       d.remote_file_id, d.attempts
                  FROM events AS e
                  JOIN deliveries AS d USING(event_id)
                 WHERE d.delivered = 0
                 ORDER BY e.event_id
                 LIMIT ?
                """,
                (selected_limit,),
            ).fetchall()
        return tuple(
            PendingDelivery(
                event_id=str(row[0]),
                signal_type=str(row[1]),
                source_partition=str(row[2]),
                payload=bytes(row[3]),
                remote_file_id=None if row[4] is None else str(row[4]),
                attempts=int(row[5]),
            )
            for row in rows
        )

    def acknowledged(self) -> tuple[AcknowledgedDelivery, ...]:
        """Return every delivered event for remote-authority re-verification."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT e.event_id, e.signal_type, e.source_partition, e.payload,
                       e.payload_sha256, d.remote_file_id
                  FROM events AS e
                  JOIN deliveries AS d USING(event_id)
                 WHERE d.delivered = 1
                 ORDER BY e.event_id
                """
            ).fetchall()
        if len(rows) > self._limits.max_outbox_rows:
            raise OutboxError("acknowledged rows exceed max_outbox_rows")
        deliveries: list[AcknowledgedDelivery] = []
        for row in rows:
            payload_value = row[3]
            if not isinstance(payload_value, bytes):
                raise OutboxError("durable event payload is not a SQLite BLOB")
            payload = payload_value
            if sha256(payload).hexdigest() != str(row[4]):
                raise OutboxError("durable event payload checksum mismatch")
            remote_file_id = row[5]
            if not isinstance(remote_file_id, str) or not remote_file_id:
                raise OutboxError("acknowledged delivery has no remote file ID")
            deliveries.append(
                AcknowledgedDelivery(
                    event_id=str(row[0]),
                    signal_type=str(row[1]),
                    source_partition=str(row[2]),
                    payload=payload,
                    remote_file_id=remote_file_id,
                )
            )
        return tuple(deliveries)

    def reserve_remote_file_id(self, event_id: str, remote_file_id: str) -> str:
        """Persist the retry identity before any upload begins."""
        if not event_id or not remote_file_id:
            raise OutboxError("event_id and remote_file_id must be non-empty")
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT remote_file_id, delivered FROM deliveries WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if row is None:
                raise OutboxError("unknown event_id")
            existing = None if row[0] is None else str(row[0])
            if existing is not None and existing != remote_file_id:
                raise OutboxError("remote file ID is immutable once reserved")
            if existing is None:
                connection.execute(
                    "UPDATE deliveries SET remote_file_id = ? WHERE event_id = ?",
                    (remote_file_id, event_id),
                )
            return existing or remote_file_id

    def record_attempt(self, event_id: str, *, error: str | None) -> int:
        """Durably count one bounded upload attempt and retain its error."""
        if error is not None and not error:
            raise OutboxError("error must be non-empty or None")
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT attempts, delivered FROM deliveries WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if row is None:
                raise OutboxError("unknown event_id")
            if int(row[1]) == 1:
                raise OutboxError("delivered events cannot be attempted again")
            attempts = int(row[0]) + 1
            if attempts > self._limits.max_delivery_attempts:
                raise OutboxError("delivery attempts exceed max_delivery_attempts")
            connection.execute(
                "UPDATE deliveries SET attempts = ?, last_error = ? WHERE event_id = ?",
                (attempts, error, event_id),
            )
            return attempts

    def record_error(self, event_id: str, *, error: str) -> None:
        """Attach an error to the current attempt without double-counting it."""
        if not error:
            raise OutboxError("error must be non-empty")
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT delivered FROM deliveries WHERE event_id = ?", (event_id,)
            ).fetchone()
            if row is None:
                raise OutboxError("unknown event_id")
            if int(row[0]) == 1:
                raise OutboxError("delivered events cannot retain delivery errors")
            connection.execute(
                "UPDATE deliveries SET last_error = ? WHERE event_id = ?",
                (error, event_id),
            )

    def mark_delivered(self, event_id: str) -> None:
        """Acknowledge only an externally verified immutable object."""
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT remote_file_id FROM deliveries WHERE event_id = ?", (event_id,)
            ).fetchone()
            if row is None:
                raise OutboxError("unknown event_id")
            if row[0] is None:
                raise OutboxError("cannot deliver without a reserved remote file ID")
            connection.execute(
                """
                UPDATE deliveries
                   SET delivered = 1, last_error = NULL
                 WHERE event_id = ?
                """,
                (event_id,),
            )

    def event_bytes(self, event_id: str) -> bytes:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT payload, payload_sha256 FROM events WHERE event_id = ?", (event_id,)
            ).fetchone()
        if row is None:
            raise OutboxError("unknown event_id")
        payload = bytes(row[0])
        if sha256(payload).hexdigest() != str(row[1]):
            raise OutboxError("durable event payload checksum mismatch")
        return payload

    def all_event_bytes(self) -> tuple[bytes, ...]:
        """Return every committed local event in canonical event-ID order."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT payload, payload_sha256 FROM events ORDER BY event_id"
            ).fetchall()
        return self._verified_payloads(rows)

    def undelivered_event_bytes(self) -> tuple[bytes, ...]:
        """Return only locally authoritative events not yet acknowledged on Drive."""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT e.payload, e.payload_sha256
                  FROM events AS e
                  JOIN deliveries AS d USING(event_id)
                 WHERE d.delivered = 0
                 ORDER BY e.event_id
                """
            ).fetchall()
        return self._verified_payloads(rows)

    @staticmethod
    def _verified_payloads(rows: list[tuple[object, ...]]) -> tuple[bytes, ...]:
        payloads: list[bytes] = []
        for payload_value, claimed_sha256 in rows:
            if not isinstance(payload_value, bytes):
                raise OutboxError("durable event payload is not a SQLite BLOB")
            payload = payload_value
            if sha256(payload).hexdigest() != str(claimed_sha256):
                raise OutboxError("durable event payload checksum mismatch")
            payloads.append(payload)
        return tuple(payloads)

    def acquire_lease(
        self,
        lease_key: str,
        *,
        owner: str,
        now_utc_ns: int,
        ttl_ns: int,
    ) -> int:
        """Acquire or renew one local lease and return its fencing token."""
        if not lease_key or not owner:
            raise OutboxError("lease_key and owner must be non-empty")
        if not isinstance(now_utc_ns, int) or isinstance(now_utc_ns, bool) or now_utc_ns < 0:
            raise OutboxError("now_utc_ns must be a non-negative integer")
        if not isinstance(ttl_ns, int) or isinstance(ttl_ns, bool) or ttl_ns <= 0:
            raise OutboxError("ttl_ns must be a positive integer")
        expires = now_utc_ns + ttl_ns
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT owner, fence_token, expires_utc_ns
                  FROM leases
                 WHERE lease_key = ?
                """,
                (lease_key,),
            ).fetchone()
            if row is None:
                token = 1
                connection.execute(
                    """
                    INSERT INTO leases(lease_key, owner, fence_token, expires_utc_ns)
                    VALUES (?, ?, ?, ?)
                    """,
                    (lease_key, owner, token, expires),
                )
                return token
            current_owner = str(row[0])
            current_token = int(row[1])
            current_expiry = int(row[2])
            if current_owner == owner and now_utc_ns < current_expiry:
                connection.execute(
                    "UPDATE leases SET expires_utc_ns = ? WHERE lease_key = ?",
                    (expires, lease_key),
                )
                return current_token
            if now_utc_ns < current_expiry:
                raise LeaseBusyError("watchdog lease is held by another local owner")
            token = current_token + 1
            connection.execute(
                """
                UPDATE leases
                   SET owner = ?, fence_token = ?, expires_utc_ns = ?
                 WHERE lease_key = ?
                """,
                (owner, token, expires, lease_key),
            )
            return token

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            journal_mode = str(connection.execute("PRAGMA journal_mode=WAL").fetchone()[0])
            if journal_mode.lower() != "wal":
                raise OutboxError("SQLite outbox requires WAL journal mode")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            for ddl in _TABLE_DDL.values():
                connection.execute(ddl.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1))
            self._verify_schema(connection)
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version not in {0, OUTBOX_SCHEMA_VERSION}:
                raise OutboxError("unsupported SQLite outbox schema version")
            connection.execute(f"PRAGMA user_version={OUTBOX_SCHEMA_VERSION}")
            connection.commit()

    @staticmethod
    def _verify_schema(connection: sqlite3.Connection) -> None:
        declared_rows = connection.execute(
            """
            SELECT name, sql
              FROM sqlite_master
             WHERE type = 'table'
               AND name IN ('events', 'deliveries', 'leases')
            """
        ).fetchall()
        declared_by_name = {
            str(name): LedgerOutbox._normalize_ddl(str(ddl))
            for name, ddl in declared_rows
            if ddl is not None
        }
        expected_ddl = {name: LedgerOutbox._normalize_ddl(ddl) for name, ddl in _TABLE_DDL.items()}
        if declared_by_name != expected_ddl:
            raise OutboxError("SQLite outbox declared schema mismatch")

        expected = {
            "events": (
                ("event_id", "TEXT", 1, 1),
                ("signal_type", "TEXT", 1, 0),
                ("source_partition", "TEXT", 1, 0),
                ("payload", "BLOB", 1, 0),
                ("payload_sha256", "TEXT", 1, 0),
            ),
            "deliveries": (
                ("event_id", "TEXT", 1, 1),
                ("remote_file_id", "TEXT", 0, 0),
                ("delivered", "INTEGER", 1, 0),
                ("attempts", "INTEGER", 1, 0),
                ("last_error", "TEXT", 0, 0),
            ),
            "leases": (
                ("lease_key", "TEXT", 1, 1),
                ("owner", "TEXT", 1, 0),
                ("fence_token", "INTEGER", 1, 0),
                ("expires_utc_ns", "INTEGER", 1, 0),
            ),
        }
        table_rows = connection.execute("PRAGMA table_list").fetchall()
        strict_by_name = {str(row[1]): int(row[5]) for row in table_rows}
        for table_name, expected_columns in expected.items():
            rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
            actual_columns = tuple(
                (str(row[1]), str(row[2]).upper(), int(row[3]), int(row[5])) for row in rows
            )
            if actual_columns != expected_columns or strict_by_name.get(table_name) != 1:
                raise OutboxError(f"SQLite outbox {table_name} schema mismatch")
        foreign_keys = connection.execute("PRAGMA foreign_key_list(deliveries)").fetchall()
        expected_foreign_key = ("events", "event_id", "event_id")
        if len(foreign_keys) != 1 or tuple(str(value) for value in foreign_keys[0][2:5]) != (
            expected_foreign_key
        ):
            raise OutboxError("SQLite outbox delivery foreign-key schema mismatch")

    @staticmethod
    def _normalize_ddl(ddl: str) -> str:
        """Normalize insignificant authored whitespace for sqlite_master comparison."""
        return " ".join(ddl.split())

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
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @staticmethod
    def _assert_fence(
        connection: sqlite3.Connection,
        lease_key: str,
        fence_token: int,
    ) -> None:
        row = connection.execute(
            "SELECT fence_token FROM leases WHERE lease_key = ?", (lease_key,)
        ).fetchone()
        if row is None or int(row[0]) != fence_token:
            raise StaleFenceError("watchdog fencing token is stale")


__all__ = [
    "OUTBOX_SCHEMA_VERSION",
    "AcknowledgedDelivery",
    "LeaseBusyError",
    "LedgerOutbox",
    "OutboxError",
    "PendingDelivery",
    "StaleFenceError",
]
