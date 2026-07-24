from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from stoic_derived.market_data.model import FinalBar, InstrumentSpec, QualityState, Timeframe
from stoic_derived.signal_engine.alignment import (
    CausalAligner,
    FinalizedSeriesBatch,
)
from stoic_derived.signal_engine.model import (
    FIXED_TIMEFRAME_PLANS,
    CoverageGap,
    MarketLineage,
    Role,
    SignalType,
    SignalValidationError,
    SuppressionCode,
)

FINGERPRINT = "a" * 64
OTHER_FINGERPRINT = "b" * 64


def _bar(
    timeframe: Timeframe,
    end_ns: int,
    *,
    instrument_id: int = 101,
    source: str = "test",
    calendar_fingerprint: str = FINGERPRINT,
    aggregation_fingerprint: str = FINGERPRINT,
    quality: QualityState = QualityState.COMPLETE,
) -> FinalBar:
    start_ns = end_ns - (timeframe.duration_ns or 100)
    return FinalBar(
        source=source,
        instrument=InstrumentSpec("NQ", "NQ.c.0"),
        instrument_id=instrument_id,
        timeframe=timeframe,
        calendar_fingerprint=calendar_fingerprint,
        aggregation_fingerprint=aggregation_fingerprint,
        start_ns=start_ns,
        end_ns=end_ns,
        trading_date=date(2026, 1, 2) if timeframe.is_session_based else None,
        open_ticks=100,
        high_ticks=102,
        low_ticks=99,
        close_ticks=101,
        volume=1,
        trade_count=1,
        first_event_ns=start_ns,
        last_event_ns=end_ns - 1,
        quality=quality,
    )


def _batch(
    *bars: FinalBar,
    gaps: tuple[CoverageGap, ...] = (),
    finalized_through_ns: int | None = None,
) -> FinalizedSeriesBatch:
    lineage = MarketLineage.from_final_bar(bars[0])
    watermark = finalized_through_ns or max(bar.end_ns for bar in bars) + 1
    return FinalizedSeriesBatch(
        lineage=lineage,
        finalized_through_ns=watermark,
        bars=bars,
        gaps=gaps,
    )


def _role_bars(plan_type: SignalType, end_ns: int = 10_000_000_000_000) -> tuple[FinalBar, ...]:
    plan = FIXED_TIMEFRAME_PLANS[plan_type]
    return tuple(_bar(plan.for_role(role), end_ns) for role in Role)


def test_batch_rejects_foreign_lineage_and_future_bar() -> None:
    first = _bar(Timeframe.ONE_MINUTE, 1_000_000_000_000)
    foreign = _bar(Timeframe.FIVE_MINUTES, 1_000_000_000_000, instrument_id=202)
    lineage = MarketLineage.from_final_bar(first)

    with pytest.raises(SignalValidationError, match="lineage"):
        FinalizedSeriesBatch(lineage, 1_000_000_000_000, (first, foreign))
    with pytest.raises(SignalValidationError, match="finalized_through"):
        FinalizedSeriesBatch(lineage, 999_999_999_999, (first,))


@pytest.mark.parametrize("signal_type", list(SignalType))
def test_all_fixed_maps_create_role_bound_complete_snapshot(signal_type: SignalType) -> None:
    plan = FIXED_TIMEFRAME_PLANS[signal_type]
    bars = _role_bars(signal_type)
    aligner = CausalAligner(plan)

    outcomes = aligner.ingest(_batch(*bars))

    assert len(outcomes) == 1
    snapshot = outcomes[0].snapshot
    assert snapshot is not None
    assert snapshot.execute_bar.timeframe is plan.execute
    assert {role: history[-1].timeframe for role, history in snapshot.history.items()} == {
        role: plan.for_role(role) for role in Role
    }


def test_future_bar_never_leaks_into_an_earlier_execute_snapshot() -> None:
    plan = FIXED_TIMEFRAME_PLANS[SignalType.SCALP]
    execute = _bar(plan.execute, 10_000_000_000_000)
    setup = _bar(plan.setup, 10_000_000_000_000)
    htf_current = _bar(plan.htf, 10_000_000_000_000)
    htf_future = _bar(plan.htf, 20_000_000_000_000)
    aligner = CausalAligner(plan)

    outcome = aligner.ingest(_batch(execute, setup, htf_current, htf_future))[0]

    assert outcome.failure is None
    assert outcome.snapshot is not None
    assert outcome.snapshot.bars_for(Role.HTF) == (htf_current,)
    assert all(
        bar.end_ns <= outcome.snapshot.execute_bar.end_ns
        for history in outcome.snapshot.history.values()
        for bar in history
    )


def test_same_end_permutations_are_identical_and_replay_is_idempotent() -> None:
    plan = FIXED_TIMEFRAME_PLANS[SignalType.SCALP]
    bars = _role_bars(SignalType.SCALP)
    forward = CausalAligner(plan).ingest(_batch(*bars))
    reverse_aligner = CausalAligner(plan)
    reverse = reverse_aligner.ingest(_batch(*reversed(bars)))

    assert forward == reverse
    assert reverse_aligner.ingest(_batch(*bars)) == ()


def test_same_end_fragments_wait_for_watermark_to_advance() -> None:
    plan = FIXED_TIMEFRAME_PLANS[SignalType.SCALP]
    bars = _role_bars(SignalType.SCALP)
    execute = next(bar for bar in bars if bar.timeframe is plan.execute)
    context = tuple(bar for bar in bars if bar.timeframe is not plan.execute)
    lineage = MarketLineage.from_final_bar(execute)
    aligner = CausalAligner(plan)

    assert aligner.ingest(FinalizedSeriesBatch(lineage, execute.end_ns, (execute,))) == ()
    assert aligner.ingest(FinalizedSeriesBatch(lineage, execute.end_ns, context)) == ()
    outcomes = aligner.ingest(FinalizedSeriesBatch(lineage, execute.end_ns + 1))

    assert len(outcomes) == 1
    assert outcomes[0].snapshot is not None


def test_late_gap_cannot_invalidate_an_already_evaluated_window() -> None:
    plan = FIXED_TIMEFRAME_PLANS[SignalType.SCALP]
    bars = _role_bars(SignalType.SCALP)
    execute = next(bar for bar in bars if bar.timeframe is plan.execute)
    lineage = MarketLineage.from_final_bar(execute)
    watermark = execute.end_ns + 1
    aligner = CausalAligner(plan)

    outcomes = aligner.ingest(FinalizedSeriesBatch(lineage, watermark, bars))
    assert len(outcomes) == 1
    assert outcomes[0].snapshot is not None

    late_gap = CoverageGap(
        lineage,
        plan.setup,
        execute.end_ns - 1,
        watermark,
        "late gap overlapping a sealed decision",
    )
    with pytest.raises(SignalValidationError, match="behind watermark"):
        aligner.ingest(
            FinalizedSeriesBatch(
                lineage,
                watermark,
                gaps=(late_gap,),
            )
        )


def test_roll_and_fingerprint_mixing_fail_closed() -> None:
    plan = FIXED_TIMEFRAME_PLANS[SignalType.SCALP]
    bars = _role_bars(SignalType.SCALP)
    aligner = CausalAligner(plan)
    aligner.ingest(_batch(*bars))
    rolled = _bar(plan.execute, 20_000_000_000_000, instrument_id=202)
    changed_calendar = _bar(
        plan.execute, 20_000_000_000_000, calendar_fingerprint=OTHER_FINGERPRINT
    )

    with pytest.raises(SignalValidationError, match="lineage"):
        aligner.ingest(_batch(rolled))
    with pytest.raises(SignalValidationError, match="lineage"):
        aligner.ingest(_batch(changed_calendar))


def test_degraded_missing_and_overlapping_gap_produce_typed_failure() -> None:
    plan = FIXED_TIMEFRAME_PLANS[SignalType.SCALP]
    execute = _bar(plan.execute, 10_000_000_000_000)
    setup = _bar(plan.setup, 10_000_000_000_000)
    degraded = _bar(plan.htf, 10_000_000_000_000, quality=QualityState.DEGRADED)
    degraded_outcome = CausalAligner(plan).ingest(_batch(execute, setup, degraded))[0]
    assert degraded_outcome.failure is not None
    assert degraded_outcome.failure.code is SuppressionCode.DEGRADED_DATA

    missing_outcome = CausalAligner(plan).ingest(_batch(execute, setup))[0]
    assert missing_outcome.failure is not None
    assert missing_outcome.failure.code is SuppressionCode.MISSING_CONTEXT

    complete = _bar(plan.htf, 10_000_000_000_000)
    lineage = MarketLineage.from_final_bar(execute)
    gap = CoverageGap(
        lineage,
        plan.setup,
        9_999_999_999_999,
        10_000_000_000_000,
        "known missing coverage",
    )
    gap_outcome = CausalAligner(plan).ingest(_batch(execute, setup, complete, gaps=(gap,)))[0]
    assert gap_outcome.failure is not None
    assert gap_outcome.failure.code is SuppressionCode.COVERAGE_GAP


def test_exact_duplicate_is_idempotent_but_conflicting_interval_is_a_hard_error() -> None:
    plan = FIXED_TIMEFRAME_PLANS[SignalType.SCALP]
    bars = _role_bars(SignalType.SCALP)
    execute = next(bar for bar in bars if bar.timeframe is plan.execute)
    conflicting = replace(execute, close_ticks=102)
    aligner = CausalAligner(plan)
    aligner.ingest(_batch(*bars))

    assert aligner.ingest(_batch(*bars)) == ()
    with pytest.raises(SignalValidationError, match="conflicting"):
        aligner.ingest(_batch(conflicting))


def test_watermark_is_monotonic_and_failed_transaction_does_not_mutate_state() -> None:
    plan = FIXED_TIMEFRAME_PLANS[SignalType.SCALP]
    bars = _role_bars(SignalType.SCALP)
    aligner = CausalAligner(plan)
    aligner.ingest(_batch(*bars))
    execute = next(bar for bar in bars if bar.timeframe is plan.execute)
    conflicting = replace(execute, close_ticks=102)
    future = _bar(plan.htf, 20_000_000_000_000)

    with pytest.raises(SignalValidationError, match="conflicting"):
        aligner.ingest(_batch(conflicting, future))
    assert aligner.finalized_through_ns == 10_000_000_000_001
    assert aligner.ingest(_batch(*bars)) == ()

    lineage = MarketLineage.from_final_bar(execute)
    with pytest.raises(SignalValidationError, match="monotonic"):
        aligner.ingest(FinalizedSeriesBatch(lineage, 9_999_999_999_999))


def test_gap_pressure_cannot_discard_a_still_relevant_role_gap() -> None:
    plan = FIXED_TIMEFRAME_PLANS[SignalType.SCALP]
    bars = _role_bars(SignalType.SCALP)
    execute = next(bar for bar in bars if bar.timeframe is plan.execute)
    lineage = MarketLineage.from_final_bar(execute)
    setup_start = next(bar.start_ns for bar in bars if bar.timeframe is plan.setup)
    relevant = CoverageGap(
        lineage,
        plan.setup,
        setup_start,
        execute.end_ns,
        "relevant setup gap",
    )
    decoys = (
        CoverageGap(lineage, Timeframe.WEEKLY, 1, 2, "decoy one"),
        CoverageGap(lineage, Timeframe.WEEKLY, 3, 4, "decoy two"),
    )
    aligner = CausalAligner(plan, history_limit=2)

    assert (
        aligner.ingest(
            FinalizedSeriesBatch(
                lineage,
                execute.end_ns,
                gaps=(relevant, *decoys),
            )
        )
        == ()
    )
    outcome = aligner.ingest(_batch(*bars))[0]

    assert outcome.failure is not None
    assert outcome.failure.code is SuppressionCode.COVERAGE_GAP


def test_long_horizon_gap_state_is_pruned_only_after_retained_history_passes_it() -> None:
    plan = FIXED_TIMEFRAME_PLANS[SignalType.SCALP]
    base_end = 10_000_000_000_000
    initial = _role_bars(SignalType.SCALP, base_end)
    lineage = MarketLineage.from_final_bar(initial[0])
    aligner = CausalAligner(plan, history_limit=2)
    previous_watermark = base_end

    for offset in range(12):
        end_ns = base_end + offset * 900_000_000_000
        bars = _role_bars(SignalType.SCALP, end_ns)
        gap = CoverageGap(
            lineage,
            plan.execute,
            previous_watermark,
            end_ns + 1,
            f"bounded recurrent gap {offset}",
        )
        aligner.ingest(
            FinalizedSeriesBatch(
                lineage,
                end_ns + 1,
                bars,
                (gap,),
            )
        )
        previous_watermark = end_ns + 1

    assert aligner.retained_gap_count <= 3


def test_overlapping_timeframe_bars_are_rejected_before_gap_pruning() -> None:
    first = _bar(Timeframe.ONE_MINUTE, 10_000_000_000_000)
    overlapping = _bar(Timeframe.ONE_MINUTE, 10_000_000_030_000)
    lineage = MarketLineage.from_final_bar(first)

    with pytest.raises(SignalValidationError, match="cannot overlap"):
        FinalizedSeriesBatch(
            lineage,
            overlapping.end_ns + 1,
            (first, overlapping),
        )


def test_pathological_gap_growth_fails_before_mutating_aligner_state() -> None:
    plan = FIXED_TIMEFRAME_PLANS[SignalType.SCALP]
    bar = _bar(plan.execute, 10_000_000_000_000)
    lineage = MarketLineage.from_final_bar(bar)
    aligner = CausalAligner(plan, history_limit=1)
    gaps = tuple(
        CoverageGap(lineage, plan.execute, index * 2, index * 2 + 1, f"gap {index}")
        for index in range(65)
    )

    with pytest.raises(SignalValidationError, match="coverage-gap bound"):
        aligner.ingest(FinalizedSeriesBatch(lineage, 1_000, gaps=gaps))

    assert aligner.retained_gap_count == 0
    assert aligner.finalized_through_ns is None
