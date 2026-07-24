from __future__ import annotations

import json

import pytest

from stoic_derived.ledger.codec import (
    LedgerCodecError,
    decode_event,
    decode_events_jsonl,
    encode_events_jsonl,
)
from stoic_derived.ledger.model import LedgerEvent, LedgerLimits


def test_event_round_trip_is_exact(make_signal) -> None:
    event = LedgerEvent.for_signal(make_signal(), source="writer")

    decoded = decode_event(event.canonical_bytes())

    assert decoded == event
    assert decoded.canonical_bytes() == event.canonical_bytes()


def test_tampered_claimed_identity_is_rejected(make_signal) -> None:
    event = LedgerEvent.for_signal(make_signal(), source="writer")
    payload = event.canonical_dict()
    payload["event_id"] = "f" * 64

    with pytest.raises(LedgerCodecError, match="event_id"):
        decode_event(json.dumps(payload))


def test_duplicate_json_key_is_rejected() -> None:
    with pytest.raises(LedgerCodecError, match="duplicate JSON key"):
        decode_event('{"event_id":"a","event_id":"b"}')


def test_event_jsonl_requires_canonical_order(make_signal) -> None:
    signal = make_signal()
    first = LedgerEvent.for_signal(signal, source="a")
    second = LedgerEvent.for_signal(signal, source="b")
    ordered = sorted((first, second), key=lambda event: event.event_id)
    reversed_bytes = b"\n".join(event.canonical_bytes() for event in reversed(ordered)) + b"\n"

    with pytest.raises(LedgerCodecError, match="ordered"):
        decode_events_jsonl(reversed_bytes)


def test_exact_duplicate_events_encode_once(make_signal) -> None:
    event = LedgerEvent.for_signal(make_signal(), source="writer")

    encoded = encode_events_jsonl((event, event))

    assert decode_events_jsonl(encoded) == (event,)


def test_event_bytes_are_bounded_before_decode(make_signal) -> None:
    event = LedgerEvent.for_signal(make_signal(), source="writer")
    limits = LedgerLimits(max_event_bytes=10, max_download_bytes=10)

    with pytest.raises(LedgerCodecError, match="max_event_bytes"):
        decode_event(event.canonical_bytes(), limits=limits)
