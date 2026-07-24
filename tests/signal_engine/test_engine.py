from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from stoic_derived.market_data.model import FinalBar, InstrumentSpec, Timeframe
from stoic_derived.signal_engine.alignment import FinalizedSeriesBatch
from stoic_derived.signal_engine.compiler import (
    BarOperand,
    ComparisonPredicate,
    ConstantOperand,
    WindowPredicate,
    _lookback_by_role,
    _strategy_neutral_test_program,
)
from stoic_derived.signal_engine.engine import SignalEngine
from stoic_derived.signal_engine.model import (
    TIMEFRAME_PLANS,
    MarketLineage,
    Role,
    SetupType,
    SignalType,
    SignalValidationError,
)

FINGERPRINT = "a" * 64


def _bar(timeframe: Timeframe, end_ns: int, instrument_id: int = 101) -> FinalBar:
    start_ns = end_ns - (timeframe.duration_ns or 100)
    return FinalBar(
        source="market-test",
        instrument=InstrumentSpec("NQ", "NQ.c.0"),
        instrument_id=instrument_id,
        timeframe=timeframe,
        calendar_fingerprint=FINGERPRINT,
        aggregation_fingerprint=FINGERPRINT,
        start_ns=start_ns,
        end_ns=end_ns,
        trading_date=date(2026, 1, 2) if timeframe.is_session_based else None,
        open_ticks=2,
        high_ticks=2,
        low_ticks=2,
        close_ticks=2,
        volume=1,
        trade_count=1,
        first_event_ns=start_ns,
        last_event_ns=end_ns - 1,
    )


def test_blocked_release_has_no_engine_or_program() -> None:
    created = SignalEngine.from_release(None, None)

    assert created.engine is None
    assert created.program is None
    assert created.readiness.ready is False


@pytest.mark.parametrize("signal_type", list(SignalType))
def test_engine_emits_complete_records_once_per_rule_and_execute_bar(
    signal_type: SignalType,
) -> None:
    program = _strategy_neutral_test_program()
    program = replace(
        program,
        profiles=tuple(
            replace(
                profile,
                setup_type=SetupType.BREAK_AND_RETEST.value,
                trade_type=signal_type.value,
            )
            for profile in program.profiles
        ),
    )
    engine = SignalEngine._from_program_for_test(program)
    end_ns = 10_000_000_000_000
    bars = tuple(_bar(program_timeframe(signal_type, role), end_ns) for role in Role)
    batch = FinalizedSeriesBatch(MarketLineage.from_final_bar(bars[0]), end_ns + 1, bars)

    first = engine.ingest(batch)
    replay = engine.ingest(batch)

    assert len(first.signals) == 2
    assert not first.suppressions
    assert all(signal.source == "stoic-signal-engine/v1" for signal in first.signals)
    assert all(signal.signal_type is signal_type for signal in first.signals)
    assert all(len(signal.causal_bar_ids) == 3 for signal in first.signals)
    assert not replay.signals
    assert not replay.suppressions


def test_same_timestamp_on_distinct_contracts_is_not_deduplicated() -> None:
    program = _strategy_neutral_test_program()
    program = replace(
        program,
        profiles=tuple(
            replace(profile, setup_type=SetupType.BREAK_AND_RETEST.value)
            for profile in program.profiles
        ),
    )
    engine = SignalEngine._from_program_for_test(program)
    end_ns = 10_000_000_000_000

    def batch_for(instrument_id: int) -> FinalizedSeriesBatch:
        bars = tuple(
            _bar(program_timeframe(SignalType.SCALP, role), end_ns, instrument_id) for role in Role
        )
        return FinalizedSeriesBatch(MarketLineage.from_final_bar(bars[0]), end_ns + 1, bars)

    first = engine.ingest(batch_for(101))
    second = engine.ingest(batch_for(202))

    assert len(first.signals) == 2
    assert len(second.signals) == 2
    assert {signal.lineage.instrument_id for signal in first.signals} == {101}
    assert {signal.lineage.instrument_id for signal in second.signals} == {202}


def test_replay_after_history_trim_is_rejected_without_unbounded_engine_dedupe() -> None:
    program = _strategy_neutral_test_program()
    program = replace(
        program,
        profiles=tuple(
            replace(profile, setup_type=SetupType.BREAK_AND_RETEST.value)
            for profile in program.profiles
        ),
    )
    engine = SignalEngine._from_program_for_test(program)
    end_ns = 10_000_000_000_000
    bars = tuple(_bar(program_timeframe(SignalType.SCALP, role), end_ns) for role in Role)
    lineage = MarketLineage.from_final_bar(bars[0])
    first = FinalizedSeriesBatch(lineage, end_ns + 1, bars)
    engine.ingest(first)

    duration_ns = Timeframe.ONE_MINUTE.duration_ns
    assert duration_ns is not None
    for offset in range(1, 4):
        later_end = end_ns + offset * duration_ns
        engine.ingest(
            FinalizedSeriesBatch(
                lineage,
                later_end + 1,
                (_bar(Timeframe.ONE_MINUTE, later_end),),
            )
        )

    assert not hasattr(engine, "_emitted")
    with pytest.raises(SignalValidationError, match="monotonic"):
        engine.ingest(first)


def test_active_lineages_are_hard_bounded_and_explicitly_retired() -> None:
    program = _strategy_neutral_test_program()
    program = replace(
        program,
        profiles=tuple(
            replace(profile, setup_type=SetupType.BREAK_AND_RETEST.value)
            for profile in program.profiles
        ),
    )
    engine = SignalEngine._from_program_for_test(program)
    end_ns = 10_000_000_000_000

    def batch_for(instrument_id: int) -> FinalizedSeriesBatch:
        bars = tuple(
            _bar(program_timeframe(SignalType.SCALP, role), end_ns, instrument_id) for role in Role
        )
        return FinalizedSeriesBatch(MarketLineage.from_final_bar(bars[0]), end_ns + 1, bars)

    batches = tuple(batch_for(instrument_id) for instrument_id in range(101, 106))
    for batch in batches[:4]:
        engine.ingest(batch)

    assert len(engine.active_lineages) == 4
    with pytest.raises(SignalValidationError, match="active lineage bound"):
        engine.ingest(batches[4])

    retired = batches[0].lineage
    assert engine.retire_lineage(retired) is True
    assert engine.retire_lineage(retired) is False
    engine.ingest(batches[4])
    assert len(engine.active_lineages) == 4


def test_suppression_is_pinned_to_the_program_release() -> None:
    program = _strategy_neutral_test_program()
    program = replace(
        program,
        profiles=(
            replace(
                program.profiles[0],
                setup_type=SetupType.BREAK_AND_RETEST.value,
                rearm_policy="unsupported_test_policy",
            ),
        ),
    )
    engine = SignalEngine._from_program_for_test(program)
    end_ns = 10_000_000_000_000
    bars = tuple(_bar(program_timeframe(SignalType.SCALP, role), end_ns) for role in Role)
    batch = FinalizedSeriesBatch(MarketLineage.from_final_bar(bars[0]), end_ns + 1, bars)

    result = engine.ingest(batch)

    assert len(result.suppressions) == 1
    suppression = result.suppressions[0]
    assert suppression.release_file_sha256 == program.release_sha256
    assert suppression.rulebook_version == program.rulebook_version
    assert suppression.engine_version == "signal-engine/v1"


def test_signed_market_data_binding_is_enforced() -> None:
    program = _strategy_neutral_test_program()
    profile = replace(
        program.profiles[0],
        setup_type=SetupType.BREAK_AND_RETEST.value,
        market_data_binding=replace(
            program.profiles[0].market_data_binding,
            calendar_fingerprint="b" * 64,
        ),
    )
    program = replace(program, profiles=(profile,))
    engine = SignalEngine._from_program_for_test(program)
    end_ns = 10_000_000_000_000
    bars = tuple(_bar(program_timeframe(SignalType.SCALP, role), end_ns) for role in Role)
    lineage = MarketLineage.from_final_bar(bars[0])

    result = engine.ingest(FinalizedSeriesBatch(lineage, end_ns + 1, bars))

    assert not result.signals
    assert len(result.suppressions) == 1
    assert result.suppressions[0].code.value == "lineage_mismatch"


def test_temporal_program_warms_up_then_emits_with_full_history() -> None:
    program = _strategy_neutral_test_program()
    profile = replace(
        program.profiles[0],
        setup_type=SetupType.BREAK_AND_RETEST.value,
        predicate=WindowPredicate(
            "consecutive",
            3,
            ComparisonPredicate(
                "gt",
                BarOperand("execute", "close", 0),
                ConstantOperand(Decimal("0")),
            ),
        ),
    )
    program = replace(
        program,
        profiles=(profile,),
        lookback_by_role=_lookback_by_role((profile,)),
    )
    engine = SignalEngine._from_program_for_test(program)
    base_ns = 10_000_000_000_000
    first_bars = tuple(_bar(program_timeframe(SignalType.SCALP, role), base_ns) for role in Role)
    lineage = MarketLineage.from_final_bar(first_bars[0])

    first = engine.ingest(FinalizedSeriesBatch(lineage, base_ns + 1, first_bars))
    duration_ns = Timeframe.ONE_MINUTE.duration_ns
    assert duration_ns is not None
    second_end = base_ns + duration_ns
    second_bar = _bar(Timeframe.ONE_MINUTE, second_end)
    second = engine.ingest(FinalizedSeriesBatch(lineage, second_end + 1, (second_bar,)))
    third_end = second_end + duration_ns
    third_bar = _bar(Timeframe.ONE_MINUTE, third_end)
    third = engine.ingest(FinalizedSeriesBatch(lineage, third_end + 1, (third_bar,)))

    assert not first.signals and len(first.suppressions) == 1
    assert not second.signals and len(second.suppressions) == 1
    assert len(third.signals) == 1 and not third.suppressions
    assert len(third.signals[0].causal_bar_ids) == 5


def test_full_engine_same_end_batch_permutations_are_byte_identical() -> None:
    program = _strategy_neutral_test_program()
    program = replace(
        program,
        profiles=tuple(
            replace(profile, setup_type=SetupType.BREAK_AND_RETEST.value)
            for profile in program.profiles
        ),
    )
    end_ns = 10_000_000_000_000
    bars = tuple(_bar(program_timeframe(SignalType.SCALP, role), end_ns) for role in Role)
    lineage = MarketLineage.from_final_bar(bars[0])

    forward = SignalEngine._from_program_for_test(program).ingest(
        FinalizedSeriesBatch(lineage, end_ns + 1, bars)
    )
    reverse = SignalEngine._from_program_for_test(program).ingest(
        FinalizedSeriesBatch(lineage, end_ns + 1, tuple(reversed(bars)))
    )

    assert forward.canonical_bytes() == reverse.canonical_bytes()


def test_maximum_compiled_lookback_constructs_a_bounded_engine() -> None:
    program = _strategy_neutral_test_program()
    profile = replace(
        program.profiles[0],
        setup_type=SetupType.BREAK_AND_RETEST.value,
        predicate=ComparisonPredicate(
            "gt",
            BarOperand("execute", "close", 1_000),
            ConstantOperand(Decimal("0")),
        ),
    )
    program = replace(
        program,
        profiles=(profile,),
        lookback_by_role=_lookback_by_role((profile,)),
    )
    engine = SignalEngine._from_program_for_test(program)
    end_ns = 10_000_000_000_000
    bars = tuple(_bar(program_timeframe(SignalType.SCALP, role), end_ns) for role in Role)
    lineage = MarketLineage.from_final_bar(bars[0])

    result = engine.ingest(FinalizedSeriesBatch(lineage, end_ns + 1, bars))

    assert not result.signals
    assert len(result.suppressions) == 1
    assert result.suppressions[0].code.value == "insufficient_lookback"


def program_timeframe(signal_type: SignalType, role: Role) -> Timeframe:
    return TIMEFRAME_PLANS[signal_type].for_role(role)
