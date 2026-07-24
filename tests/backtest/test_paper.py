"""Release-bound incremental paper observation tests."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

import pytest

from stoic_derived.backtest.model import (
    BacktestResult,
    BacktestStatus,
    EvidenceClass,
    HalfOpenInterval,
    SimulationPolicy,
)
from stoic_derived.backtest.paper import (
    PaperCheckpoint,
    PaperStatus,
    PaperValidationError,
    observe_paper,
)
from stoic_derived.signal_engine.alignment import FinalizedSeriesBatch
from stoic_derived.signal_engine.model import MarketLineage


def _policy(**changes: object) -> SimulationPolicy:
    values: dict[str, object] = {
        "entry_slippage_ticks": 1,
        "exit_slippage_ticks": 1,
        "fees_ticks_round_turn": 1,
        "zero_costs_declared": False,
        "max_active_observations": 2,
        "max_active_lineages": 2,
        "max_retained_gaps": 2,
        "max_accepted_batches": 2,
        "max_output_records": 16,
        "max_artifact_bytes": 4096,
    }
    values.update(changes)
    return SimulationPolicy(**values)  # type: ignore[arg-type]


def _observe(*, checkpoint: PaperCheckpoint | None = None, policy: SimulationPolicy | None = None):
    return observe_paper(
        None,
        None,
        None,
        (),
        policy or _policy(),
        HalfOpenInterval(10, 20),
        checkpoint=checkpoint,
    )


def _lineage() -> MarketLineage:
    return MarketLineage(
        source="databento:GLBX.MDP3:trades",
        root="NQ",
        continuous_symbol="NQ.c.0",
        instrument_id=101,
        calendar_fingerprint="a" * 64,
        aggregation_fingerprint="b" * 64,
        market_data_schema="market-data/v1",
    )


def _batch(watermark: int) -> FinalizedSeriesBatch:
    return FinalizedSeriesBatch(_lineage(), watermark)


def _ready_result() -> BacktestResult:
    return BacktestResult(
        evidence_class=EvidenceClass.PAPER_FORWARD,
        status=BacktestStatus.COMPLETE,
        plan_id="f" * 64,
    )


def test_blocked_release_is_zero_nonexecuting_paper_evidence() -> None:
    observation = _observe()

    assert observation.result.status.value == "blocked"
    assert observation.result.trades == ()
    assert observation.checkpoint.status == PaperStatus.BLOCKED
    assert observation.checkpoint.complete is False
    assert observation.checkpoint.execution is False
    assert observation.checkpoint.orders_placed == 0


def test_checkpoint_is_canonical_content_addressed_and_restart_idempotent() -> None:
    first = _observe()
    resumed = _observe(checkpoint=first.checkpoint)

    assert first.checkpoint.canonical_bytes() == resumed.checkpoint.canonical_bytes()
    assert first.checkpoint.checkpoint_id == resumed.checkpoint.checkpoint_id
    assert first.result.canonical_bytes() == resumed.result.canonical_bytes()
    assert b"release_path" not in first.checkpoint.canonical_bytes()


@pytest.mark.parametrize(
    "change",
    [
        pytest.param("release", id="release"),
        pytest.param("policy", id="policy"),
        pytest.param("horizon", id="horizon"),
    ],
)
def test_resume_rejects_identity_mismatch(change: str) -> None:
    first = _observe()
    if change == "release":
        with pytest.raises(PaperValidationError, match="release identity"):
            observe_paper(
                None,
                "a" * 64,
                None,
                (),
                _policy(),
                HalfOpenInterval(10, 20),
                checkpoint=first.checkpoint,
            )
    elif change == "policy":
        with pytest.raises(PaperValidationError, match="policy identity"):
            _observe(checkpoint=first.checkpoint, policy=_policy(max_accepted_batches=1))
    else:
        with pytest.raises(PaperValidationError, match="horizon"):
            observe_paper(
                None,
                None,
                None,
                (),
                _policy(),
                HalfOpenInterval(11, 20),
                checkpoint=first.checkpoint,
            )


def test_checkpoint_rejects_tampered_active_identity_and_execution_claims() -> None:
    checkpoint = _observe().checkpoint
    with pytest.raises(PaperValidationError, match="orders"):
        replace(checkpoint, orders_placed=1)
    with pytest.raises(PaperValidationError, match="PaperStatus"):
        replace(checkpoint, status="made_up")


def test_checkpoint_rejects_tampered_or_noncanonical_batch_evidence() -> None:
    first = observe_paper(
        None, None, None, (_batch(11), _batch(12)), _policy(), HalfOpenInterval(10, 20)
    )
    with pytest.raises(PaperValidationError, match="canonical"):
        replace(
            first.checkpoint, accepted_batches=tuple(reversed(first.checkpoint.accepted_batches))
        )


def test_resume_rejects_tampered_checkpoint_state() -> None:
    first = _observe()
    tampered = replace(first.checkpoint, observed_through_ns=1)
    with pytest.raises(PaperValidationError, match="does not reconcile"):
        _observe(checkpoint=tampered)


def test_resume_equals_one_shot_and_horizon_completion_censors_through_runner() -> None:
    first_batch, second_batch = _batch(15), _batch(20)
    with patch(
        "stoic_derived.backtest.paper._run_release_replay", return_value=_ready_result()
    ) as replay:
        initial = observe_paper(
            None, None, None, (first_batch,), _policy(), HalfOpenInterval(10, 20)
        )
        resumed = observe_paper(
            None,
            None,
            None,
            (second_batch,),
            _policy(),
            HalfOpenInterval(10, 20),
            checkpoint=initial.checkpoint,
        )
        one_shot = observe_paper(
            None, None, None, (first_batch, second_batch), _policy(), HalfOpenInterval(10, 20)
        )

    assert initial.checkpoint.status is PaperStatus.ACTIVE
    assert initial.checkpoint.complete is False
    assert resumed.checkpoint.status is PaperStatus.COMPLETE
    assert resumed.checkpoint.complete is True
    assert resumed.checkpoint.canonical_bytes() == one_shot.checkpoint.canonical_bytes()
    completion_calls = [
        call for call in replay.call_args_list if call.kwargs["terminal_reason"] is not None
    ]
    assert any(call.kwargs["terminal_reason"].value == "end_of_data" for call in completion_calls)
    assert completion_calls[0].kwargs["signal_interval"] == (10, 20)
    assert completion_calls[0].kwargs["observation_end_ns"] == 20
    assert resumed.result.execution is False
    assert resumed.result.orders_placed == 0


def test_order_bounds_and_post_completion_novel_evidence_fail_closed() -> None:
    first_batch, second_batch = _batch(15), _batch(20)
    with pytest.raises(PaperValidationError, match="canonical"):
        observe_paper(
            None, None, None, (second_batch, first_batch), _policy(), HalfOpenInterval(10, 20)
        )
    with pytest.raises(PaperValidationError, match="max_accepted_batches"):
        observe_paper(
            None,
            None,
            None,
            (first_batch, second_batch),
            _policy(max_accepted_batches=1),
            HalfOpenInterval(10, 20),
        )

    with patch("stoic_derived.backtest.paper._run_release_replay", return_value=_ready_result()):
        complete = observe_paper(
            None, None, None, (first_batch, second_batch), _policy(), HalfOpenInterval(10, 20)
        )
        with pytest.raises(PaperValidationError, match="complete paper horizon"):
            observe_paper(
                None,
                None,
                None,
                (_batch(21),),
                _policy(),
                HalfOpenInterval(10, 20),
                checkpoint=complete.checkpoint,
            )


def test_checkpoint_bytes_are_bounded_by_the_explicit_policy() -> None:
    with (
        patch("stoic_derived.backtest.paper._run_release_replay") as replay,
        pytest.raises(PaperValidationError, match="checkpoint byte bound"),
    ):
        _observe(policy=_policy(max_artifact_bytes=1))

    replay.assert_not_called()


def test_public_api_has_no_engine_or_signal_injection_surface() -> None:
    parameters = set(observe_paper.__annotations__)

    assert not {"engine", "program", "signal", "fixture", "strategy"} & parameters
