"""SP3 canonical evidence-codec tests."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from hashlib import sha256
from io import BytesIO

import pytest

from stoic_derived.backtest.codec import (
    BATCH_CODEC_SCHEMA_VERSION,
    CodecError,
    batch_identity,
    batch_projection,
    canonical_batch_bytes,
    decode_batch,
    decode_batches_jsonl,
    encode_batch_jsonl,
    normalize_batches,
    read_batches_jsonl,
)
from stoic_derived.market_data.model import (
    FinalBar,
    InstrumentSpec,
    QualityState,
    Timeframe,
)
from stoic_derived.signal_engine.alignment import FinalizedSeriesBatch
from stoic_derived.signal_engine.model import CoverageGap, MarketLineage


def _bar(
    *,
    end_ns: int = 120,
    close_ticks: int = 80_002,
    timeframe: Timeframe = Timeframe.ONE_MINUTE,
    quality: QualityState = QualityState.COMPLETE,
    instrument_id: int = 101,
) -> FinalBar:
    return FinalBar(
        source="databento:GLBX.MDP3:trades",
        instrument=InstrumentSpec("NQ", "NQ.c.0"),
        instrument_id=instrument_id,
        timeframe=timeframe,
        calendar_fingerprint="a" * 64,
        aggregation_fingerprint="b" * 64,
        start_ns=end_ns - 60,
        end_ns=end_ns,
        trading_date=date(2026, 7, 24) if timeframe is Timeframe.DAILY else None,
        open_ticks=80_000,
        high_ticks=80_004,
        low_ticks=79_998,
        close_ticks=close_ticks,
        volume=7,
        trade_count=3,
        first_event_ns=end_ns - 50,
        last_event_ns=end_ns - 1,
        quality=quality,
    )


def _batch(
    *,
    end_ns: int = 120,
    close_ticks: int = 80_002,
    quality: QualityState = QualityState.COMPLETE,
    with_gap: bool = False,
    watermark: int | None = None,
) -> FinalizedSeriesBatch:
    bar = _bar(end_ns=end_ns, close_ticks=close_ticks, quality=quality)
    lineage = MarketLineage.from_final_bar(bar)
    gaps = (
        (CoverageGap(lineage, Timeframe.FIVE_MINUTES, 10, 20, "vendor coverage gap"),)
        if with_gap
        else ()
    )
    return FinalizedSeriesBatch(lineage, watermark or end_ns, (bar,), gaps)


def test_codec_round_trip_reconstructs_full_physical_lineage_bars_and_gaps() -> None:
    batch = _batch(quality=QualityState.DEGRADED, with_gap=True)

    encoded = encode_batch_jsonl((batch,))
    decoded = decode_batches_jsonl(encoded)

    assert decoded == (batch,)
    assert decoded[0].bars[0].instrument == InstrumentSpec("NQ", "NQ.c.0")
    assert decoded[0].lineage.instrument_id == 101
    assert decoded[0].bars[0].quality is QualityState.DEGRADED
    assert decoded[0].gaps[0].lineage == decoded[0].lineage
    assert read_batches_jsonl(BytesIO(encoded)) == (batch,)


def test_codec_projection_bytes_and_identity_are_stable_and_content_addressed() -> None:
    batch = _batch(with_gap=True)
    projection = batch_projection(batch)

    assert projection["schema_version"] == BATCH_CODEC_SCHEMA_VERSION
    assert canonical_batch_bytes(batch) == canonical_batch_bytes(
        decode_batch(canonical_batch_bytes(batch))
    )
    assert batch_identity(batch) == sha256(canonical_batch_bytes(batch)).hexdigest()
    assert batch_identity(batch) != batch_identity(_batch(close_ticks=80_003))
    assert b"path" not in canonical_batch_bytes(batch)


def test_codec_rejects_descending_caller_order_instead_of_sorting() -> None:
    earlier = _batch(end_ns=120)
    later = _batch(end_ns=240)

    with pytest.raises(CodecError, match="canonical input order"):
        normalize_batches((later, earlier))
    with pytest.raises(CodecError, match="canonical input order"):
        encode_batch_jsonl((later, earlier))


def test_codec_normalizes_exact_duplicate_identity_but_rejects_conflicting_interval_content() -> (
    None
):
    original = _batch(watermark=120)
    duplicate = decode_batch(canonical_batch_bytes(original))
    conflict = _batch(close_ticks=80_003, watermark=121)

    assert normalize_batches((original, duplicate)) == (original,)
    assert decode_batches_jsonl(encode_batch_jsonl((original, duplicate))) == (original,)
    with pytest.raises(CodecError, match="conflicting bars"):
        normalize_batches((original, conflict))


def test_codec_rejects_extra_and_malformed_fields_and_noncanonical_nested_order() -> None:
    batch = _batch(with_gap=True)
    payload = json.loads(canonical_batch_bytes(batch))
    payload["path"] = "/private/raw.dbn"
    with pytest.raises(CodecError, match="unknown path"):
        decode_batch(payload)

    payload = json.loads(canonical_batch_bytes(batch))
    payload["finalized_through_ns"] = True
    with pytest.raises(CodecError, match="non-negative integer"):
        decode_batch(payload)

    payload = json.loads(canonical_batch_bytes(batch))
    payload["bars"].append(payload["bars"][0])
    with pytest.raises(CodecError, match="canonical-order"):
        decode_batch(payload)

    with pytest.raises(CodecError, match="duplicate JSON key"):
        decode_batch(
            '{"bars":[],"bars":[],"finalized_through_ns":0,"gaps":[],"lineage":{},"schema_version":"backtest-batch/v1"}'
        )
    canonical_line = canonical_batch_bytes(batch)
    with pytest.raises(CodecError, match="end with a newline"):
        decode_batches_jsonl(canonical_line)
    with pytest.raises(CodecError, match="exact canonical encoding"):
        decode_batches_jsonl(b" " + canonical_line + b"\n")


def test_codec_rejects_conflicting_gap_content_for_same_physical_interval() -> None:
    first = _batch(with_gap=True, watermark=120)
    second_gap = replace(first.gaps[0], reason="other vendor account")
    second = FinalizedSeriesBatch(first.lineage, 121, (), (second_gap,))

    with pytest.raises(CodecError, match="conflicting gaps"):
        normalize_batches((first, second))
