from __future__ import annotations

import sqlite3

import pytest

from stoic_derived.ledger.model import LedgerEvent, LedgerLimits
from stoic_derived.ledger.outbox import (
    LeaseBusyError,
    LedgerOutbox,
    OutboxError,
    StaleFenceError,
)


def test_event_and_delivery_survive_restart(tmp_path, make_signal) -> None:
    path = tmp_path / "ledger.sqlite3"
    event = LedgerEvent.for_signal(make_signal(), source="writer")
    first = LedgerOutbox(path)

    inserted = first.enqueue((event,))
    reopened = LedgerOutbox(path)

    assert inserted == (event.event_id,)
    assert reopened.all_event_bytes() == (event.canonical_bytes(),)
    assert reopened.pending()[0].event_id == event.event_id


def test_exact_reenqueue_is_idempotent(tmp_path, make_signal) -> None:
    outbox = LedgerOutbox(tmp_path / "ledger.sqlite3")
    event = LedgerEvent.for_signal(make_signal(), source="writer")

    first = outbox.enqueue((event,))
    second = outbox.enqueue((event, event))

    assert first == (event.event_id,)
    assert second == ()
    assert len(outbox.pending()) == 1


def test_remote_file_identity_is_durable_and_immutable(tmp_path, make_signal) -> None:
    outbox = LedgerOutbox(tmp_path / "ledger.sqlite3")
    event = LedgerEvent.for_signal(make_signal(), source="writer")
    outbox.enqueue((event,))

    first = outbox.reserve_remote_file_id(event.event_id, "drive-id-1")
    replay = outbox.reserve_remote_file_id(event.event_id, "drive-id-1")

    assert first == "drive-id-1"
    assert replay == "drive-id-1"
    with pytest.raises(OutboxError, match="immutable"):
        outbox.reserve_remote_file_id(event.event_id, "drive-id-2")


def test_delivery_ack_requires_reserved_remote_id(tmp_path, make_signal) -> None:
    outbox = LedgerOutbox(tmp_path / "ledger.sqlite3")
    event = LedgerEvent.for_signal(make_signal(), source="writer")
    outbox.enqueue((event,))

    with pytest.raises(OutboxError, match="reserved"):
        outbox.mark_delivered(event.event_id)


def test_attempts_are_bounded(tmp_path, make_signal) -> None:
    limits = LedgerLimits(max_delivery_attempts=2)
    outbox = LedgerOutbox(tmp_path / "ledger.sqlite3", limits=limits)
    event = LedgerEvent.for_signal(make_signal(), source="writer")
    outbox.enqueue((event,))
    outbox.reserve_remote_file_id(event.event_id, "drive-id")

    assert outbox.record_attempt(event.event_id, error=None) == 1
    assert outbox.record_attempt(event.event_id, error="retry") == 2
    with pytest.raises(OutboxError, match="attempts"):
        outbox.record_attempt(event.event_id, error="too many")


def test_competing_local_watchdogs_use_monotonic_fences(tmp_path, make_signal) -> None:
    outbox = LedgerOutbox(tmp_path / "ledger.sqlite3")
    event = LedgerEvent.for_signal(make_signal(), source="writer")
    first = outbox.acquire_lease("cutoff:key", owner="one", now_utc_ns=0, ttl_ns=10)

    with pytest.raises(LeaseBusyError):
        outbox.acquire_lease("cutoff:key", owner="two", now_utc_ns=5, ttl_ns=10)
    second = outbox.acquire_lease("cutoff:key", owner="two", now_utc_ns=10, ttl_ns=10)

    assert first == 1
    assert second == 2
    with pytest.raises(StaleFenceError):
        outbox.enqueue((event,), lease_key="cutoff:key", fence_token=first)
    assert outbox.enqueue((event,), lease_key="cutoff:key", fence_token=second)


def test_checksum_corruption_fails_closed(tmp_path, make_signal) -> None:
    path = tmp_path / "ledger.sqlite3"
    outbox = LedgerOutbox(path)
    event = LedgerEvent.for_signal(make_signal(), source="writer")
    outbox.enqueue((event,))
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE events SET payload = ? WHERE event_id = ?",
            (b"{}", event.event_id),
        )

    with pytest.raises(OutboxError, match="checksum"):
        outbox.all_event_bytes()


def test_undelivered_cache_excludes_acknowledged_drive_events(tmp_path, make_signal) -> None:
    outbox = LedgerOutbox(tmp_path / "ledger.sqlite3")
    event = LedgerEvent.for_signal(make_signal(), source="writer")
    outbox.enqueue((event,))

    assert outbox.undelivered_event_bytes() == (event.canonical_bytes(),)
    outbox.reserve_remote_file_id(event.event_id, "drive-id")
    outbox.mark_delivered(event.event_id)

    assert outbox.undelivered_event_bytes() == ()


def test_same_version_database_with_wrong_schema_is_rejected(tmp_path) -> None:
    path = tmp_path / "ledger.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE events(event_id TEXT PRIMARY KEY)")
        connection.execute("PRAGMA user_version=1")

    with pytest.raises(OutboxError, match="schema"):
        LedgerOutbox(path)


def test_same_version_database_with_weakened_checks_is_rejected(tmp_path) -> None:
    path = tmp_path / "ledger.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE events(
                event_id TEXT PRIMARY KEY,
                signal_type TEXT NOT NULL,
                source_partition TEXT NOT NULL,
                payload BLOB NOT NULL,
                payload_sha256 TEXT NOT NULL
            ) STRICT
            """
        )
        connection.execute(
            """
            CREATE TABLE deliveries(
                event_id TEXT PRIMARY KEY REFERENCES events(event_id),
                remote_file_id TEXT,
                delivered INTEGER NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT
            ) STRICT
            """
        )
        connection.execute(
            """
            CREATE TABLE leases(
                lease_key TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                fence_token INTEGER NOT NULL,
                expires_utc_ns INTEGER NOT NULL
            ) STRICT
            """
        )
        connection.execute("PRAGMA user_version=1")

    with pytest.raises(OutboxError, match="declared schema"):
        LedgerOutbox(path)
