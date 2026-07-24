"""SP2 immutable signal-contract tests."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from hashlib import sha256

import pytest

from stoic_derived.market_data.model import Timeframe
from stoic_derived.signal_engine.model import (
    FIXED_TIMEFRAME_PLANS,
    CoverageGap,
    Decision,
    Direction,
    EvaluationBatch,
    MarketLineage,
    RationalR,
    Role,
    SetupType,
    SignalBatch,
    SignalRecord,
    SignalType,
    SignalValidationError,
    Suppression,
    SuppressionCode,
    timeframe_from_release_value,
)


def _lineage(*, instrument_id: int = 101) -> MarketLineage:
    return MarketLineage(
        source="databento:GLBX.MDP3:trades",
        root="NQ",
        continuous_symbol="NQ.c.0",
        instrument_id=instrument_id,
        calendar_fingerprint="a" * 64,
        aggregation_fingerprint="b" * 64,
        market_data_schema="market-data/v1",
    )


def _signal(
    *,
    direction: Direction = Direction.LONG,
    causal_bar_ids: tuple[str, ...] = ("a" * 64, "b" * 64),
    lineage: MarketLineage | None = None,
) -> SignalRecord:
    if direction is Direction.LONG:
        entry_ticks, stop_ticks, target_ticks = 80_000, 79_996, 80_006
    else:
        entry_ticks, stop_ticks, target_ticks = 80_000, 80_004, 79_994
    return SignalRecord(
        signal_type=SignalType.SCALP,
        direction=direction,
        entry_ticks=entry_ticks,
        stop_ticks=stop_ticks,
        target_ticks=target_ticks,
        risk_reward=RationalR.from_prices(direction, entry_ticks, stop_ticks, target_ticks),
        setup_type=SetupType.BREAK_AND_RETEST,
        entry_model="sbs_model_1",
        confidence=73,
        signal_ts_ns=1_700_000_000_000_000_000,
        source="signal-engine",
        release_file_sha256="c" * 64,
        rulebook_version="1.2.3",
        rule_id="retest-long-v1",
        engine_version="1.0.0",
        lineage=lineage or _lineage(),
        causal_bar_ids=causal_bar_ids,
    )


def test_fixed_timeframe_plans_exactly_match_the_vision_and_translate_sp0_values() -> None:
    assert {
        signal_type.value: plan.canonical_dict()
        for signal_type, plan in FIXED_TIMEFRAME_PLANS.items()
    } == {
        "Scalp": {
            "signal_type": "Scalp",
            "htf": "15m",
            "setup": "5m",
            "execute": "1m",
            "manage": "5m",
        },
        "Day": {
            "signal_type": "Day",
            "htf": "60m",
            "setup": "5m",
            "execute": "1m",
            "manage": "5m",
        },
        "Swing": {
            "signal_type": "Swing",
            "htf": "D",
            "setup": "60m",
            "execute": "15m",
            "manage": "60m",
        },
        "Position": {
            "signal_type": "Position",
            "htf": "W",
            "setup": "D",
            "execute": "60m",
            "manage": "D",
        },
    }
    assert FIXED_TIMEFRAME_PLANS[SignalType.POSITION].for_role(Role.HTF) is Timeframe.WEEKLY
    assert timeframe_from_release_value("1d") is Timeframe.DAILY
    assert timeframe_from_release_value("1w") is Timeframe.WEEKLY
    with pytest.raises(SignalValidationError, match="release timeframe"):
        timeframe_from_release_value("D")


def test_rational_r_is_reduced_fractional_tick_math_for_both_orientations() -> None:
    long_r = RationalR.from_prices(Direction.LONG, 80_000, 79_996, 80_006)
    short_r = RationalR.from_prices(Direction.SHORT, 80_000, 80_004, 79_994)

    assert long_r == RationalR(numerator=3, denominator=2)
    assert long_r.fraction == Fraction(3, 2)
    assert long_r.decimal_string == "1.5"
    assert short_r == long_r
    assert RationalR(numerator=1, denominator=3).decimal_string == "1/3"
    with pytest.raises(SignalValidationError, match="reduced"):
        RationalR(numerator=2, denominator=4)
    with pytest.raises(SignalValidationError, match="long orientation"):
        RationalR.from_prices(Direction.LONG, 80_000, 80_004, 79_994)


def test_signal_record_is_complete_immutable_and_content_addressed() -> None:
    signal = _signal()

    assert signal.instrument == "NQ"
    assert signal.signal_id == sha256(signal._content_bytes()).hexdigest()
    assert signal.canonical_dict()["signal_id"] == signal.signal_id
    assert signal.canonical_bytes() == (
        b'{"causal_bar_ids":["aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
        b'"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"],'
        b'"confidence":73,"direction":"long","engine_version":"1.0.0",'
        b'"entry_model":"sbs_model_1","entry_ticks":80000,'
        b'"lineage":{"aggregation_fingerprint":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",'
        b'"calendar_fingerprint":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
        b'"continuous_symbol":"NQ.c.0","instrument_id":101,"market_data_schema":"market-data/v1",'
        b'"root":"NQ","source":"databento:GLBX.MDP3:trades"},'
        b'"release_file_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",'
        b'"risk_reward":{"decimal":"1.5","denominator":2,"numerator":3},'
        b'"rule_id":"retest-long-v1","rulebook_version":"1.2.3","schema_version":"signal-engine/v1",'
        b'"setup_type":"break_and_retest","signal_id":"' + signal.signal_id.encode() + b'",'
        b'"signal_ts_ns":1700000000000000000,"signal_type":"Scalp","source":"signal-engine",'
        b'"stop_ticks":79996,"target_ticks":80006,'
        b'"timeframe_plan":{"execute":"1m","htf":"15m","manage":"5m","setup":"5m","signal_type":"Scalp"}}'
    )
    with pytest.raises(AttributeError):
        signal.confidence = 20  # type: ignore[misc]


def test_same_market_values_with_different_provenance_have_distinct_signal_ids() -> None:
    first = _signal(causal_bar_ids=("a" * 64, "b" * 64))
    replay = _signal(causal_bar_ids=("a" * 64, "b" * 64))
    different_bars = _signal(causal_bar_ids=("a" * 64, "c" * 64))
    different_contract = _signal(lineage=_lineage(instrument_id=102))

    assert replay.signal_id == first.signal_id
    assert different_bars.signal_id != first.signal_id
    assert different_contract.signal_id != first.signal_id


def test_signal_rejects_partial_provenance_and_an_inexact_r_multiple() -> None:
    with pytest.raises(SignalValidationError, match="causal_bar_ids"):
        _signal(causal_bar_ids=())

    with pytest.raises(SignalValidationError, match="risk_reward"):
        replace(_signal(), risk_reward=RationalR(1, 1))


def test_lineage_gaps_and_output_batches_are_canonical_and_fail_closed() -> None:
    lineage = _lineage()
    gap = CoverageGap(
        lineage=lineage,
        timeframe=Timeframe.FIVE_MINUTES,
        start_ns=10,
        end_ns=20,
        reason="vendor_gap",
    )
    suppression = Suppression(
        code=SuppressionCode.COVERAGE_GAP,
        detail="setup context crossed a known coverage gap",
        source="signal-engine",
        release_file_sha256="f" * 64,
        rulebook_version="1.0.0",
        engine_version="1.0.0",
        signal_type=SignalType.SCALP,
        signal_ts_ns=20,
        lineage=lineage,
        references=(gap.identity,),
    )
    signal = _signal(lineage=lineage)
    ordered_signals = tuple(sorted((signal,), key=lambda record: record.signal_id))
    ordered_suppressions = tuple(sorted((suppression,), key=lambda fact: fact.identity))
    batch = SignalBatch(lineage, 20, ordered_signals, ordered_suppressions)
    decision = Decision(suppression=suppression)
    evaluation = EvaluationBatch(lineage, 20, (decision,))

    assert gap.canonical_dict()["timeframe"] == "5m"
    assert (
        batch.canonical_bytes()
        == SignalBatch(lineage, 20, ordered_signals, ordered_suppressions).canonical_bytes()
    )
    assert evaluation.canonical_dict()["decisions"][0]["kind"] == "suppression"
    with pytest.raises(SignalValidationError, match="batch lineage"):
        SignalBatch(_lineage(instrument_id=102), 20, ordered_signals)
    with pytest.raises(SignalValidationError, match="exactly one"):
        Decision(signal=signal, suppression=suppression)
