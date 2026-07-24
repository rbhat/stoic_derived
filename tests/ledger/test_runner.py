from __future__ import annotations

from dataclasses import replace

from stoic_derived.ledger import runner as runner_module
from stoic_derived.ledger.outbox import LedgerOutbox
from stoic_derived.ledger.runner import readiness, run_release_ledger
from stoic_derived.signal_engine.compiler import (
    CompilationReadiness,
    _strategy_neutral_test_program,
)
from stoic_derived.signal_engine.engine import EngineCreation, SignalEngine
from stoic_derived.signal_engine.model import Role, SetupType, SignalType


def test_current_production_readiness_is_truthfully_blocked_and_zero() -> None:
    result = readiness()

    assert result.status == "blocked"
    assert result.signal_count == 0
    assert result.event_count == 0
    assert result.execution is False
    assert result.orders_placed == 0
    assert result.ledger is None


def test_blocked_release_never_consumes_input_or_writes_outbox(tmp_path) -> None:
    outbox = LedgerOutbox(tmp_path / "ledger.sqlite3")

    def unsafe_input():
        raise AssertionError("blocked production must not consume market input")
        yield

    result = run_release_ledger(
        unsafe_input(),
        release_path=None,
        expected_sha256=None,
        public_key=None,
        outbox=outbox,
        remote_events=(),
    )

    assert result.status == "blocked"
    assert not outbox.all_event_bytes()


def test_ready_test_composition_uses_engine_output_and_restarts_idempotently(
    monkeypatch, tmp_path, make_bar, make_batch
) -> None:
    program = _strategy_neutral_test_program()
    program = replace(
        program,
        profiles=tuple(
            replace(profile, setup_type=SetupType.BREAK_AND_RETEST.value)
            for profile in program.profiles
        ),
    )

    def create_ready(*_args, **_kwargs) -> EngineCreation:
        engine = SignalEngine._from_program_for_test(program)
        return EngineCreation(engine, program, CompilationReadiness(True, ()))

    monkeypatch.setattr(runner_module.SignalEngine, "from_release", create_ready)
    end_ns = 10_000_000_000_000
    from stoic_derived.signal_engine.model import TIMEFRAME_PLANS

    scalp_plan = TIMEFRAME_PLANS[SignalType.SCALP]
    bars = tuple(
        make_bar(
            timeframe=scalp_plan.for_role(role),
            end_ns=end_ns,
            open_ticks=2,
            high_ticks=2,
            low_ticks=2,
            close_ticks=2,
        )
        for role in Role
    )
    batch = make_batch(bars=bars, finalized_through_ns=end_ns + 1)
    outbox = LedgerOutbox(tmp_path / "ledger.sqlite3")

    first = run_release_ledger(
        (batch,),
        release_path="release.json",
        expected_sha256="a" * 64,
        public_key=b"x" * 32,
        outbox=outbox,
        remote_events=(),
    )
    second = run_release_ledger(
        (batch,),
        release_path="release.json",
        expected_sha256="a" * 64,
        public_key=b"x" * 32,
        outbox=outbox,
        remote_events=(),
    )

    assert first.status == "complete"
    assert first.signal_count == 2
    assert first.event_count == 2
    assert second.signal_count == 2
    assert second.event_count == 0
    assert len(outbox.all_event_bytes()) == 2
