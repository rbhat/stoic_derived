from __future__ import annotations

from pathlib import Path

from stoic_derived.dashboard.projection import (
    ProductionLedgerAuthority,
    exact_r_display,
    project_reconciliation,
)
from stoic_derived.ledger.model import (
    LedgerRecord,
    LedgerState,
    LedgerView,
    ReconciliationResult,
)
from stoic_derived.ledger.outbox import LedgerOutbox
from stoic_derived.signal_engine.model import (
    Direction,
    MarketLineage,
    RationalR,
    SetupType,
    SignalRecord,
    SignalType,
)

GENERATED_NS = 1_774_099_800_000_000_000


def make_signal(
    signal_type: SignalType,
    direction: Direction,
    *,
    entry: int,
    stop: int,
    target: int,
    timestamp_ns: int,
) -> SignalRecord:
    return SignalRecord(
        signal_type=signal_type,
        direction=direction,
        entry_ticks=entry,
        stop_ticks=stop,
        target_ticks=target,
        risk_reward=RationalR.from_prices(direction, entry, stop, target),
        setup_type=SetupType.BREAK_AND_RETEST,
        entry_model="test-only-entry-model",
        confidence=75,
        signal_ts_ns=timestamp_ns,
        source="test-only-signal-source",
        release_file_sha256="a" * 64,
        rulebook_version="test-release",
        rule_id="test-rule",
        engine_version="test-engine",
        lineage=MarketLineage(
            source="test-market",
            root="NQ",
            continuous_symbol="NQ.c.0",
            instrument_id=1,
            calendar_fingerprint="b" * 64,
            aggregation_fingerprint="c" * 64,
            market_data_schema="test-schema",
        ),
        causal_bar_ids=("d" * 64,),
    )


def make_result(records: tuple[LedgerRecord, ...]) -> ReconciliationResult:
    views = tuple(
        LedgerView(
            signal_type,
            tuple(
                sorted(
                    (record for record in records if record.signal.signal_type is signal_type),
                    key=lambda item: item.signal.signal_id,
                )
            ),
        )
        for signal_type in sorted(SignalType, key=lambda item: item.value)
    )
    return ReconciliationResult(views=views, conflicts=())


def test_closed_projection_calculates_exact_directional_ticks_r_and_hold_time() -> None:
    long_signal = make_signal(
        SignalType.SCALP,
        Direction.LONG,
        entry=100,
        stop=96,
        target=108,
        timestamp_ns=GENERATED_NS - 100_000_000_000,
    )
    short_signal = make_signal(
        SignalType.DAY,
        Direction.SHORT,
        entry=200,
        stop=204,
        target=194,
        timestamp_ns=GENERATED_NS - 100_000_000_000,
    )
    records = (
        LedgerRecord(
            signal=long_signal,
            state=LedgerState.CLOSED,
            current_semantic_id="1" * 64,
            contributing_event_ids=("2" * 64,),
            entry_observed_ts_ns=GENERATED_NS - 90_000_000_000,
            entry_price_ticks=100,
            close_observed_ts_ns=GENERATED_NS - 30_000_000_000,
            close_price_ticks=108,
            terminal_reason="target_observed",
        ),
        LedgerRecord(
            signal=short_signal,
            state=LedgerState.CLOSED,
            current_semantic_id="3" * 64,
            contributing_event_ids=("4" * 64,),
            entry_observed_ts_ns=GENERATED_NS - 80_000_000_000,
            entry_price_ticks=200,
            close_observed_ts_ns=GENERATED_NS - 20_000_000_000,
            close_price_ticks=202,
            terminal_reason="session_flatten_observed",
        ),
    )

    projected = project_reconciliation(make_result(records), generated_at_ns=GENERATED_NS)
    by_type = {item.signal_type: item for item in projected.closed_observations}

    assert by_type["Scalp"].observed_pnl_ticks == 8, "long target should gain eight ticks"
    assert by_type["Scalp"].observed_pnl_r is not None
    assert by_type["Scalp"].observed_pnl_r.display == "2", "eight over four risk is exact 2R"
    assert by_type["Day"].observed_pnl_ticks == -2, "short close above entry loses two ticks"
    assert by_type["Day"].observed_pnl_r is not None
    assert by_type["Day"].observed_pnl_r.display == "-0.5", "minus two over four is exact -0.5R"
    assert by_type["Day"].hold_seconds == 60, "hold time must use observed entry and close"


def test_pending_active_and_unresolved_never_fabricate_pnl() -> None:
    pending_signal = make_signal(
        SignalType.SCALP,
        Direction.LONG,
        entry=100,
        stop=96,
        target=108,
        timestamp_ns=GENERATED_NS - 100_000_000_000,
    )
    active_signal = make_signal(
        SignalType.SWING,
        Direction.LONG,
        entry=300,
        stop=296,
        target=308,
        timestamp_ns=GENERATED_NS - 100_000_000_000,
    )
    unresolved_signal = make_signal(
        SignalType.POSITION,
        Direction.SHORT,
        entry=400,
        stop=404,
        target=392,
        timestamp_ns=GENERATED_NS - 100_000_000_000,
    )
    records = (
        LedgerRecord(
            signal=pending_signal,
            state=LedgerState.PENDING,
            current_semantic_id="5" * 64,
            contributing_event_ids=("6" * 64,),
        ),
        LedgerRecord(
            signal=active_signal,
            state=LedgerState.ACTIVE,
            current_semantic_id="7" * 64,
            contributing_event_ids=("8" * 64,),
            entry_observed_ts_ns=GENERATED_NS - 40_000_000_000,
            entry_price_ticks=300,
        ),
        LedgerRecord(
            signal=unresolved_signal,
            state=LedgerState.UNRESOLVED,
            current_semantic_id="9" * 64,
            contributing_event_ids=("a" * 64,),
            terminal_reason="contract_roll",
        ),
    )

    projected = project_reconciliation(make_result(records), generated_at_ns=GENERATED_NS)

    assert len(projected.open_observations) == 2, "pending and active belong in open"
    assert len(projected.unresolved_observations) == 1, "unresolved must be separate"
    assert all(
        item.observed_pnl_ticks is None and item.observed_pnl_r is None
        for item in (*projected.open_observations, *projected.unresolved_observations)
    ), "non-closed records cannot carry fabricated P/L"
    active = next(item for item in projected.open_observations if item.state == "active")
    assert active.hold_seconds == 40, "active hold time should use snapshot time"


def test_nonterminating_rational_display_remains_an_exact_fraction() -> None:
    from fractions import Fraction

    assert exact_r_display(Fraction(1, 3)) == "1/3", "repeating decimal must remain exact"


class FailingDrive:
    def __init__(self) -> None:
        self.calls = 0

    def verify_acknowledged(self, outbox: LedgerOutbox) -> tuple[str, ...]:
        self.calls += 1
        raise AssertionError("Drive must not be touched before release readiness")

    def publish_pending(self, outbox: LedgerOutbox) -> tuple[str, ...]:
        self.calls += 1
        raise AssertionError("Drive must not be published before release readiness")


def test_blocked_release_returns_zero_before_any_drive_read(tmp_path: Path) -> None:
    outbox = LedgerOutbox(tmp_path / "outbox.sqlite3")
    drive = FailingDrive()
    authority = ProductionLedgerAuthority(
        outbox=outbox,
        drive_store=drive,  # type: ignore[arg-type]
        release_path=None,
        release_sha256=None,
        release_public_key=None,
    )

    snapshot = authority.snapshot(generated_at_ns=GENERATED_NS)
    published_snapshot, published_count = authority.publish(generated_at_ns=GENERATED_NS)

    assert snapshot.ledger.status == "blocked", "missing SP0 release must block dashboard ledger"
    assert snapshot.ledger.observation_count == 0
    assert published_snapshot.ledger.status == "blocked"
    assert published_count == 0
    assert drive.calls == 0, "blocked readiness must short-circuit before Drive"
