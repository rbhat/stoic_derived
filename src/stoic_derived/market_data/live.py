"""Thin, injectable Databento live-trades adapter with deterministic recovery."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, cast

from .databento import CANONICAL_SOURCE
from .model import (
    NANOS_PER_TICK,
    InstrumentSpec,
    MarketDataValidationError,
    ResumeCursor,
    TradeEvent,
)

DATASET = "GLBX.MDP3"
SCHEMA = "trades"
STYPE_IN = "continuous"
CONTINUOUS_SYMBOLS = ("NQ.c.0", "ES.c.0")
LIVE_SOURCE = CANONICAL_SOURCE
_SKIPPED_RECORDS_AFTER_SLOW_READING = 7


class LiveAdapterError(MarketDataValidationError):
    """Raised when a live record cannot safely enter the normalized stream."""


class LiveStatusKind(StrEnum):
    """Provider connection facts that are not market events."""

    SYMBOL_MAPPING = "symbol_mapping"
    HEARTBEAT = "heartbeat"
    REPLAY_COMPLETED = "replay_completed"
    SYSTEM = "system"
    ERROR = "error"
    HARD_GAP = "hard_gap"
    REPLAY_DISCARDED = "replay_discarded"
    UNSUPPORTED_RECORD = "unsupported_record"


@dataclass(frozen=True, slots=True)
class LiveStatus:
    """A secret-safe status record emitted for non-trade live messages."""

    kind: LiveStatusKind
    detail: str
    instrument_id: int | None = None
    source_progress_ns: int | None = None
    system_code: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, LiveStatusKind):
            raise LiveAdapterError("kind must be a LiveStatusKind")
        if not isinstance(self.detail, str) or not self.detail:
            raise LiveAdapterError("detail must be a non-empty string")
        if self.instrument_id is not None and (
            not isinstance(self.instrument_id, int)
            or isinstance(self.instrument_id, bool)
            or self.instrument_id <= 0
        ):
            raise LiveAdapterError("instrument_id must be a positive integer or None")
        for name in ("source_progress_ns", "system_code"):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise LiveAdapterError(f"{name} must be a non-negative integer or None")
        progress_kinds = {LiveStatusKind.HEARTBEAT, LiveStatusKind.REPLAY_COMPLETED}
        if (self.kind in progress_kinds) != (self.source_progress_ns is not None):
            raise LiveAdapterError(
                "only heartbeat and replay-completed statuses carry source progress"
            )


@dataclass(frozen=True, slots=True)
class LiveWatermark:
    """A provider-progress boundary ready for the pure aggregator."""

    root: str
    instrument_id: int
    watermark_ns: int

    def __post_init__(self) -> None:
        if self.root not in {"NQ", "ES"}:
            raise LiveAdapterError("watermark root must be NQ or ES")
        if (
            not isinstance(self.instrument_id, int)
            or isinstance(self.instrument_id, bool)
            or self.instrument_id <= 0
        ):
            raise LiveAdapterError("watermark instrument_id must be positive")
        if (
            not isinstance(self.watermark_ns, int)
            or isinstance(self.watermark_ns, bool)
            or self.watermark_ns < 0
        ):
            raise LiveAdapterError("watermark_ns must be non-negative")


@dataclass(frozen=True, slots=True)
class LiveRecordResult:
    """One normalized trade, status fact, or an explicit replay discard."""

    trade: TradeEvent | None = None
    status: LiveStatus | None = None
    dropped_replay: bool = False

    def __post_init__(self) -> None:
        if self.trade is not None and self.status is not None:
            raise LiveAdapterError("a live result may contain either a trade or a status")
        if self.trade is None and self.status is None:
            raise LiveAdapterError("a live result requires a trade or a status")
        if self.dropped_replay and self.trade is not None:
            raise LiveAdapterError("a dropped replay record cannot contain a trade")


class LiveClient(Protocol):
    """The intentionally tiny Databento client surface used by this adapter."""

    def subscribe(
        self,
        *,
        dataset: str,
        schema: str,
        symbols: tuple[str, str],
        stype_in: str,
        start: int | None = None,
    ) -> object: ...

    def stop(self) -> object: ...

    def __iter__(self) -> Iterator[object]: ...


LiveClientFactory = Callable[[str | None], LiveClient]


def _default_live_client_factory(key: str | None) -> LiveClient:
    """Create the vendor client lazily so portable unit tests need no network."""
    import databento as db

    return cast(LiveClient, db.Live(key=key, heartbeat_interval_s=5, reconnect_policy="none"))


def _record_value(record: object, name: str) -> object:
    if not hasattr(record, name):
        raise LiveAdapterError(f"Databento live record is missing {name}")
    value = getattr(record, name)
    return getattr(value, "value", value)


def _record_text(record: object, name: str) -> str:
    value = _record_value(record, name)
    if not isinstance(value, str) or not value:
        raise LiveAdapterError(f"Databento live record {name} must be a non-empty string")
    return value


def _record_int(record: object, name: str, *, positive: bool = False) -> int:
    value = _record_value(record, name)
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        or (positive and value <= 0)
    ):
        qualifier = "positive" if positive else "non-negative"
        raise LiveAdapterError(f"Databento live record {name} must be a {qualifier} integer")
    return value


class DatabentoLiveSession:
    """One provider session; a mapping must arrive before any trade is normalized."""

    def __init__(
        self,
        client: LiveClient,
        cursors: Sequence[ResumeCursor] = (),
        redactions: Sequence[str] = (),
        recovery_roots: Mapping[int, str] | None = None,
    ) -> None:
        self._client = client
        self._redactions = tuple(redaction for redaction in redactions if redaction)
        self._instruments: dict[int, InstrumentSpec] = {}
        self._root_instrument_ids: dict[str, int] = {}
        self._cursors: dict[int, ResumeCursor] = {}
        self._replay_remaining: dict[int, int] = {}
        self._pending_acks: dict[int, deque[TradeEvent]] = {}
        self._hard_gap_detail: str | None = None
        self._recovery_roots = dict(recovery_roots or {})
        for cursor in cursors:
            if not isinstance(cursor, ResumeCursor) or cursor.source != LIVE_SOURCE:
                raise LiveAdapterError("cursors must be live ResumeCursor values")
            if cursor.instrument_id in self._cursors:
                raise LiveAdapterError("cursors must have unique instrument_id values")
            self._cursors[cursor.instrument_id] = cursor
            self._replay_remaining[cursor.instrument_id] = cursor.records_at_timestamp
        if any(
            not isinstance(instrument_id, int)
            or instrument_id not in self._cursors
            or root not in {"NQ", "ES"}
            for instrument_id, root in self._recovery_roots.items()
        ):
            raise LiveAdapterError("recovery_roots must map cursor instrument IDs to NQ or ES")

    @property
    def cursors(self) -> tuple[ResumeCursor, ...]:
        """Return current per-instrument replay checkpoints in a stable order."""
        return tuple(self._cursors[instrument_id] for instrument_id in sorted(self._cursors))

    @property
    def replay_start_ns(self) -> int | None:
        """Return the earliest committed or uncommitted event needed for lossless recovery."""
        candidates = [cursor.ts_event_ns for cursor in self._cursors.values()]
        candidates.extend(
            pending[0].ts_event_ns for pending in self._pending_acks.values() if pending
        )
        return min(candidates) if candidates else None

    @property
    def recovery_roots(self) -> dict[int, str]:
        """Return root knowledge needed to retire stale cursors after a roll."""
        roots = dict(self._recovery_roots)
        roots.update(
            {
                instrument_id: instrument.root
                for instrument_id, instrument in self._instruments.items()
                if instrument_id in self._cursors
            }
        )
        return roots

    @property
    def is_halted(self) -> bool:
        """Return whether a provider-declared unrecoverable gap poisoned this session."""
        return self._hard_gap_detail is not None

    @property
    def pending_ack_count(self) -> int:
        """Return the number of emitted trades not yet durably acknowledged."""
        return sum(len(pending) for pending in self._pending_acks.values())

    def watermarks(self, status: LiveStatus) -> tuple[LiveWatermark, ...]:
        """Project trusted provider progress onto every currently mapped contract."""
        if not isinstance(status, LiveStatus):
            raise LiveAdapterError("status must be a LiveStatus")
        if status.source_progress_ns is None:
            return ()
        return tuple(
            LiveWatermark(
                root=instrument.root,
                instrument_id=instrument_id,
                watermark_ns=status.source_progress_ns,
            )
            for instrument_id, instrument in sorted(self._instruments.items())
        )

    def close(self) -> None:
        """Stop this session before explicitly opening a replacement session."""
        self._client.stop()

    def results(self) -> Iterator[LiveRecordResult]:
        """Yield normalized records from the active client without exposing SDK types."""
        for record in self._client:
            yield self.process(record)

    def ack(self, trade: TradeEvent) -> ResumeCursor:
        """Advance recovery state only after the downstream consumer durably commits a trade."""
        if not isinstance(trade, TradeEvent) or trade.source != LIVE_SOURCE:
            raise LiveAdapterError("ack requires a normalized live TradeEvent")
        if self._instruments.get(trade.instrument_id) != trade.instrument:
            raise LiveAdapterError("ack trade does not belong to this mapped live session")
        pending = self._pending_acks.get(trade.instrument_id)
        if pending is None or not pending or pending[0] != trade:
            raise LiveAdapterError("ack must match the next uncommitted trade for this session")
        self._advance_cursor(trade)
        pending.popleft()
        return self._cursors[trade.instrument_id]

    def process(self, record: object) -> LiveRecordResult:
        """Normalize a single provider record without leaking provider types outward."""
        if hasattr(record, "stype_in_symbol") and hasattr(record, "stype_out_symbol"):
            return self._process_mapping(record)
        if hasattr(record, "err"):
            detail = self._safe_detail(_record_text(record, "err"))
            code = _record_int(record, "code")
            if code == _SKIPPED_RECORDS_AFTER_SLOW_READING:
                self._hard_gap_detail = detail
                return LiveRecordResult(
                    status=LiveStatus(
                        LiveStatusKind.HARD_GAP,
                        f"live session halted after skipped records: {detail}",
                    )
                )
            return LiveRecordResult(status=LiveStatus(LiveStatusKind.ERROR, detail))
        if hasattr(record, "msg"):
            code = _record_int(record, "code")
            heartbeat = getattr(record, "is_heartbeat", None)
            is_heartbeat = bool(heartbeat()) if callable(heartbeat) else code == 0
            if is_heartbeat:
                kind = LiveStatusKind.HEARTBEAT
            elif code == 3:
                kind = LiveStatusKind.REPLAY_COMPLETED
            else:
                kind = LiveStatusKind.SYSTEM
            source_progress_ns = (
                _record_int(record, "ts_event")
                if kind in {LiveStatusKind.HEARTBEAT, LiveStatusKind.REPLAY_COMPLETED}
                else None
            )
            return LiveRecordResult(
                status=LiveStatus(
                    kind,
                    self._safe_detail(_record_text(record, "msg")),
                    source_progress_ns=source_progress_ns,
                    system_code=code,
                )
            )
        if hasattr(record, "price"):
            if self._hard_gap_detail is not None:
                raise LiveAdapterError(
                    "live session is halted after a skipped-record gap; "
                    "recover from the durable replay cursor before accepting trades"
                )
            return self._process_trade(record)
        return LiveRecordResult(
            status=LiveStatus(
                LiveStatusKind.UNSUPPORTED_RECORD,
                f"unsupported Databento live record: {type(record).__name__}",
            )
        )

    def _safe_detail(self, detail: str) -> str:
        for secret in self._redactions:
            detail = detail.replace(secret, "[redacted]")
        return detail

    def _process_mapping(self, record: object) -> LiveRecordResult:
        instrument_id = _record_int(record, "instrument_id", positive=True)
        continuous_symbol = _record_text(record, "stype_in_symbol")
        _record_text(record, "stype_out_symbol")
        root_by_symbol = {"NQ.c.0": "NQ", "ES.c.0": "ES"}
        try:
            root = root_by_symbol[continuous_symbol]
        except KeyError as exc:
            raise LiveAdapterError("SymbolMappingMsg must resolve NQ.c.0 or ES.c.0") from exc
        previous_id = self._root_instrument_ids.get(root)
        if previous_id is not None and previous_id != instrument_id:
            raise LiveAdapterError(
                "continuous mapping changed; open a new session before accepting a new instrument"
            )
        previous_instrument = self._instruments.get(instrument_id)
        if previous_instrument is not None and previous_instrument.root != root:
            raise LiveAdapterError("one instrument_id cannot map to multiple logical roots")
        retired_ids = [
            retired_id
            for retired_id, retired_root in self._recovery_roots.items()
            if retired_root == root and retired_id != instrument_id
        ]
        for retired_id in retired_ids:
            self._cursors.pop(retired_id, None)
            self._replay_remaining.pop(retired_id, None)
            self._pending_acks.pop(retired_id, None)
            self._recovery_roots.pop(retired_id, None)
        self._root_instrument_ids[root] = instrument_id
        self._instruments[instrument_id] = InstrumentSpec(root, continuous_symbol)
        if instrument_id in self._cursors:
            self._recovery_roots[instrument_id] = root
        return LiveRecordResult(
            status=LiveStatus(
                LiveStatusKind.SYMBOL_MAPPING,
                f"{continuous_symbol} mapped to instrument {instrument_id}",
                instrument_id=instrument_id,
            )
        )

    def _process_trade(self, record: object) -> LiveRecordResult:
        instrument_id = _record_int(record, "instrument_id", positive=True)
        instrument = self._instruments.get(instrument_id)
        if instrument is None:
            raise LiveAdapterError("SymbolMappingMsg is required before normalizing a trade")
        price_nanos = _record_int(record, "price", positive=True)
        if price_nanos % NANOS_PER_TICK:
            raise LiveAdapterError("Databento live trade price is not aligned to the NQ/ES tick")
        action = _record_value(record, "action")
        if action != "T":
            raise LiveAdapterError("Databento live record action must be T (trade)")
        side = _record_value(record, "side")
        sides = {"A": "ask", "B": "bid", "N": "none"}
        if side not in sides:
            raise LiveAdapterError("Databento live trade side is unsupported")
        ts_event_ns = _record_int(record, "ts_event")
        ts_recv_ns = _record_int(record, "ts_recv")
        if ts_recv_ns < ts_event_ns:
            raise LiveAdapterError("Databento live trade ts_recv must not precede ts_event")
        trade = TradeEvent(
            source=LIVE_SOURCE,
            instrument=instrument,
            publisher_id=_record_int(record, "publisher_id", positive=True),
            instrument_id=instrument_id,
            ts_event_ns=ts_event_ns,
            ts_recv_ns=ts_recv_ns,
            price_ticks=price_nanos // NANOS_PER_TICK,
            size=_record_int(record, "size", positive=True),
            action="trade",
            aggressor_side=sides[side],
            flags=_record_int(record, "flags"),
            depth=_record_int(record, "depth"),
            sequence=_record_int(record, "sequence"),
        )
        if self._discard_replayed_trade(trade):
            return LiveRecordResult(
                status=LiveStatus(
                    LiveStatusKind.REPLAY_DISCARDED,
                    "trade was already processed before reconnect",
                    instrument_id=instrument_id,
                ),
                dropped_replay=True,
            )
        self._pending_acks.setdefault(instrument_id, deque()).append(trade)
        return LiveRecordResult(trade=trade)

    def _discard_replayed_trade(self, trade: TradeEvent) -> bool:
        cursor = self._cursors.get(trade.instrument_id)
        if cursor is None:
            return False
        if trade.ts_event_ns < cursor.ts_event_ns:
            return True
        if trade.ts_event_ns > cursor.ts_event_ns:
            return False
        remaining = self._replay_remaining.get(trade.instrument_id, 0)
        if remaining > 0:
            self._replay_remaining[trade.instrument_id] = remaining - 1
            return True
        return False

    def _advance_cursor(self, trade: TradeEvent) -> None:
        previous = self._cursors.get(trade.instrument_id)
        if previous is None or trade.ts_event_ns > previous.ts_event_ns:
            records_at_timestamp = 1
        elif trade.ts_event_ns == previous.ts_event_ns:
            records_at_timestamp = previous.records_at_timestamp + 1
        else:
            raise LiveAdapterError("accepted trade cannot precede its resume cursor")
        self._cursors[trade.instrument_id] = ResumeCursor(
            source=LIVE_SOURCE,
            instrument_id=trade.instrument_id,
            ts_event_ns=trade.ts_event_ns,
            records_at_timestamp=records_at_timestamp,
        )
        self._replay_remaining[trade.instrument_id] = 0


class DatabentoLiveAdapter:
    """Create explicitly scoped live sessions without exposing credentials or SDK types."""

    def __init__(
        self,
        *,
        client_factory: LiveClientFactory | None = None,
        key: str | None = None,
    ) -> None:
        if key is not None and (not isinstance(key, str) or not key):
            raise LiveAdapterError("key must be a non-empty string or None")
        self._client_factory = client_factory or _default_live_client_factory
        self._key = key

    def __repr__(self) -> str:
        return "DatabentoLiveAdapter(key_configured=" + str(self._key is not None) + ")"

    def open_session(
        self,
        *,
        start_ns: int | None = None,
        cursors: Sequence[ResumeCursor] = (),
        recovery_roots: Mapping[int, str] | None = None,
    ) -> DatabentoLiveSession:
        """Create one subscription with an optional inclusive replay start."""
        if start_ns is not None and (
            not isinstance(start_ns, int) or isinstance(start_ns, bool) or start_ns < 0
        ):
            raise LiveAdapterError("start_ns must be a non-negative UTC nanosecond integer or None")
        validated_cursors = tuple(cursors)
        if any(
            not isinstance(cursor, ResumeCursor) or cursor.source != LIVE_SOURCE
            for cursor in validated_cursors
        ):
            raise LiveAdapterError("cursors must be live ResumeCursor values")
        if len({cursor.instrument_id for cursor in validated_cursors}) != len(validated_cursors):
            raise LiveAdapterError("cursors must have unique instrument_id values")
        cursor_start = (
            min(cursor.ts_event_ns for cursor in validated_cursors) if validated_cursors else None
        )
        if start_ns is not None and cursor_start is not None and start_ns > cursor_start:
            raise LiveAdapterError("start_ns cannot be later than a recovery cursor")
        replay_start: int | None
        replay_start = start_ns if start_ns is not None else cursor_start
        client = self._client_factory(self._key)
        if replay_start is not None:
            client.subscribe(
                dataset=DATASET,
                schema=SCHEMA,
                symbols=CONTINUOUS_SYMBOLS,
                stype_in=STYPE_IN,
                start=replay_start,
            )
        else:
            client.subscribe(
                dataset=DATASET,
                schema=SCHEMA,
                symbols=CONTINUOUS_SYMBOLS,
                stype_in=STYPE_IN,
            )
        redactions = (self._key,) if self._key is not None else ()
        return DatabentoLiveSession(
            client,
            validated_cursors,
            redactions,
            recovery_roots=recovery_roots,
        )

    def reconnect(self, session: DatabentoLiveSession) -> DatabentoLiveSession:
        """Explicitly reconnect from the session's durable timestamp-and-count state."""
        if not isinstance(session, DatabentoLiveSession):
            raise LiveAdapterError("session must be a DatabentoLiveSession")
        cursors = session.cursors
        replay_start_ns = session.replay_start_ns
        if session.is_halted and replay_start_ns is None:
            raise LiveAdapterError(
                "halted live session has no durable replay point; explicit backfill is required"
            )
        session.close()
        if cursors:
            return self.open_session(
                cursors=cursors,
                start_ns=replay_start_ns,
                recovery_roots=session.recovery_roots,
            )
        return self.open_session(start_ns=replay_start_ns)

    def resubscribe_for_continuous_roll(
        self, session: DatabentoLiveSession
    ) -> DatabentoLiveSession:
        """Require a new session so fresh SymbolMappingMsg records establish the next contract."""
        if session.pending_ack_count:
            raise LiveAdapterError("cannot roll while emitted trades await durable acknowledgement")
        return self.reconnect(session)
