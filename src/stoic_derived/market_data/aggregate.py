"""Pure event-time aggregation from normalized trades to immutable bars."""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from typing import Protocol

from .model import (
    FinalBar,
    InstrumentSpec,
    IssueCode,
    MarketDataIssue,
    MarketDataValidationError,
    QualityState,
    Timeframe,
    TradeEvent,
    UnsupportedCalendarRangeError,
    canonical_json_bytes,
)


class Bucket(Protocol):
    """The calendar-owned interval shape needed by aggregation."""

    @property
    def start_ns(self) -> int: ...

    @property
    def end_ns(self) -> int: ...

    @property
    def trading_date(self) -> date | None: ...


class BarCalendar(Protocol):
    """Session calendar boundary used by the pure aggregator."""

    @property
    def fingerprint(self) -> str: ...

    def bucket_at(self, timestamp_ns: int, timeframe: Timeframe) -> Bucket | None: ...

    def buckets_at(
        self, timestamp_ns: int, timeframes: tuple[Timeframe, ...]
    ) -> tuple[Bucket, ...]: ...


@dataclass(frozen=True, slots=True)
class AggregationSpec:
    """Versioned deterministic bar-build settings."""

    timeframes: tuple[Timeframe, ...] = tuple(Timeframe)
    allowed_lateness_ns: int = 0
    algorithm_version: str = "direct-trades/v2"

    def __post_init__(self) -> None:
        if not self.timeframes:
            raise MarketDataValidationError("timeframes must not be empty")
        if len(set(self.timeframes)) != len(self.timeframes):
            raise MarketDataValidationError("timeframes must be unique")
        if any(not isinstance(timeframe, Timeframe) for timeframe in self.timeframes):
            raise MarketDataValidationError("timeframes must contain only Timeframe values")
        if (
            not isinstance(self.allowed_lateness_ns, int)
            or isinstance(self.allowed_lateness_ns, bool)
            or self.allowed_lateness_ns < 0
        ):
            raise MarketDataValidationError("allowed_lateness_ns must be a non-negative integer")
        if not isinstance(self.algorithm_version, str) or not self.algorithm_version:
            raise MarketDataValidationError("algorithm_version must be a non-empty string")

    @property
    def fingerprint(self) -> str:
        payload = {
            "algorithm_version": self.algorithm_version,
            "allowed_lateness_ns": self.allowed_lateness_ns,
            "timeframes": [timeframe.value for timeframe in self.timeframes],
        }
        return sha256(canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class AggregationBatch:
    """Newly finalized bars and quality facts from one state transition."""

    bars: tuple[FinalBar, ...] = ()
    issues: tuple[MarketDataIssue, ...] = ()


@dataclass(slots=True)
class _MutableBar:
    source: str
    instrument: InstrumentSpec
    instrument_id: int
    timeframe: Timeframe
    calendar_fingerprint: str
    aggregation_fingerprint: str
    start_ns: int
    end_ns: int
    trading_date: date | None
    open_ticks: int
    high_ticks: int
    low_ticks: int
    close_ticks: int
    volume: int
    trade_count: int
    first_event_ns: int
    last_event_ns: int
    first_order_key: TradeOrderKey
    last_order_key: TradeOrderKey

    @classmethod
    def from_trade(
        cls,
        trade: TradeEvent,
        timeframe: Timeframe,
        bucket: Bucket,
        calendar_fingerprint: str,
        aggregation_fingerprint: str,
    ) -> _MutableBar:
        return cls(
            source=trade.source,
            instrument=trade.instrument,
            instrument_id=trade.instrument_id,
            timeframe=timeframe,
            calendar_fingerprint=calendar_fingerprint,
            aggregation_fingerprint=aggregation_fingerprint,
            start_ns=bucket.start_ns,
            end_ns=bucket.end_ns,
            trading_date=bucket.trading_date,
            open_ticks=trade.price_ticks,
            high_ticks=trade.price_ticks,
            low_ticks=trade.price_ticks,
            close_ticks=trade.price_ticks,
            volume=trade.size,
            trade_count=1,
            first_event_ns=trade.ts_event_ns,
            last_event_ns=trade.ts_event_ns,
            first_order_key=_trade_order_key(trade),
            last_order_key=_trade_order_key(trade),
        )

    def add(self, trade: TradeEvent) -> None:
        if trade.source != self.source or trade.instrument != self.instrument:
            raise MarketDataValidationError("a bar cannot combine sources or instrument specs")
        self.high_ticks = max(self.high_ticks, trade.price_ticks)
        self.low_ticks = min(self.low_ticks, trade.price_ticks)
        order_key = _trade_order_key(trade)
        if order_key < self.first_order_key:
            self.first_order_key = order_key
            self.open_ticks = trade.price_ticks
        if order_key > self.last_order_key:
            self.last_order_key = order_key
            self.close_ticks = trade.price_ticks
        self.volume += trade.size
        self.trade_count += 1
        self.first_event_ns = min(self.first_event_ns, trade.ts_event_ns)
        self.last_event_ns = max(self.last_event_ns, trade.ts_event_ns)

    def freeze(self, *, quality: QualityState = QualityState.COMPLETE) -> FinalBar:
        # The concrete type is validated by FinalBar; keeping the builder private
        # avoids exposing a mutable contract to SP2/SP3.
        return FinalBar(
            source=self.source,
            instrument=self.instrument,
            instrument_id=self.instrument_id,
            timeframe=self.timeframe,
            calendar_fingerprint=self.calendar_fingerprint,
            aggregation_fingerprint=self.aggregation_fingerprint,
            start_ns=self.start_ns,
            end_ns=self.end_ns,
            trading_date=self.trading_date,
            open_ticks=self.open_ticks,
            high_ticks=self.high_ticks,
            low_ticks=self.low_ticks,
            close_ticks=self.close_ticks,
            volume=self.volume,
            trade_count=self.trade_count,
            first_event_ns=self.first_event_ns,
            last_event_ns=self.last_event_ns,
            quality=quality,
        )


SeriesKey = tuple[str, int]
BarKey = tuple[SeriesKey, Timeframe, int, int]
TradeOrderKey = tuple[int, int, int, bytes]
ResolvedBuckets = tuple[tuple[Timeframe, Bucket], ...]


def _trade_order_key(trade: TradeEvent) -> TradeOrderKey:
    """Provide a total, arrival-independent order while preserving duplicates."""
    return (
        trade.ts_event_ns,
        trade.sequence,
        trade.ts_recv_ns,
        trade.canonical_bytes(),
    )


class MultiTimeframeAggregator:
    """Bounded event-time reorder buffer and direct multi-timeframe bar builder."""

    def __init__(self, calendar: BarCalendar, spec: AggregationSpec | None = None) -> None:
        self._calendar = calendar
        self._spec = spec or AggregationSpec()
        self._heaps: dict[
            SeriesKey,
            list[tuple[TradeOrderKey, int, TradeEvent, ResolvedBuckets]],
        ] = {}
        self._max_seen: dict[SeriesKey, int] = {}
        self._finalized_end: dict[tuple[SeriesKey, Timeframe], int] = {}
        self._builders: dict[BarKey, _MutableBar] = {}
        self._arrival_ordinal = 0
        self._last_instrument_by_root: dict[str, int] = {}
        self._trusted_watermarks: dict[SeriesKey, int] = {}
        self._closed_series: set[SeriesKey] = set()
        self._finished = False

    @property
    def spec(self) -> AggregationSpec:
        return self._spec

    def push(self, trade: TradeEvent) -> AggregationBatch:
        """Accept one arrival and finalize every interval behind its watermark."""
        if self._finished:
            raise MarketDataValidationError("cannot push after the aggregator is finished")
        if not isinstance(trade, TradeEvent):
            raise MarketDataValidationError("trade must be a TradeEvent")

        issues: list[MarketDataIssue] = []
        series = (trade.instrument.root, trade.instrument_id)
        if series in self._closed_series:
            return AggregationBatch(
                issues=(
                    self._issue(
                        IssueCode.LATE_EVENT_AFTER_FINALIZATION,
                        trade,
                        "event belongs to a contract series that was explicitly closed",
                    ),
                )
            )
        try:
            raw_buckets = self._calendar.buckets_at(trade.ts_event_ns, self._spec.timeframes)
        except UnsupportedCalendarRangeError as exc:
            return AggregationBatch(
                issues=(
                    self._issue(
                        IssueCode.UNSUPPORTED_CALENDAR_RANGE,
                        trade,
                        str(exc),
                    ),
                )
            )
        resolved_buckets: ResolvedBuckets = (
            tuple(zip(self._spec.timeframes, raw_buckets, strict=True)) if raw_buckets else ()
        )
        previous_max = self._max_seen.get(series)
        if previous_max is not None and trade.ts_event_ns < previous_max:
            issues.append(
                self._issue(
                    IssueCode.EVENT_TIME_REGRESSION,
                    trade,
                    f"event time {trade.ts_event_ns} followed {previous_max}",
                )
            )

        trusted_watermark = self._trusted_watermarks.get(series)
        if trusted_watermark is not None and trade.ts_event_ns <= trusted_watermark:
            issues.append(
                self._issue(
                    IssueCode.EVENT_BEHIND_WATERMARK,
                    trade,
                    f"event time {trade.ts_event_ns} is at or behind trusted "
                    f"watermark {trusted_watermark}",
                )
            )
            return AggregationBatch(issues=tuple(issues))

        if self._is_late(series, resolved_buckets):
            issues.append(
                self._issue(
                    IssueCode.LATE_EVENT_AFTER_FINALIZATION,
                    trade,
                    "event belongs to an interval that was already finalized",
                )
            )
            return AggregationBatch(issues=tuple(issues))

        if previous_max is not None:
            previous_watermark = previous_max - self._spec.allowed_lateness_ns
            if trade.ts_event_ns < previous_watermark:
                issues.append(
                    self._issue(
                        IssueCode.EVENT_BEHIND_WATERMARK,
                        trade,
                        f"event time {trade.ts_event_ns} is behind watermark {previous_watermark}",
                    )
                )
                return AggregationBatch(issues=tuple(issues))

        if not resolved_buckets:
            issues.append(
                self._issue(
                    IssueCode.TRADE_OUTSIDE_SESSION,
                    trade,
                    "event does not belong to a declared trading interval",
                )
            )
            return AggregationBatch(issues=tuple(issues))

        previous_instrument = self._last_instrument_by_root.get(trade.instrument.root)
        roll_bars: tuple[FinalBar, ...] = ()
        if previous_instrument is not None and previous_instrument != trade.instrument_id:
            roll_bars = self.close_series(trade.instrument.root, previous_instrument).bars
            issues.append(
                self._issue(
                    IssueCode.CONTRACT_BOUNDARY,
                    trade,
                    f"instrument changed from {previous_instrument} to {trade.instrument_id}",
                )
            )
        self._last_instrument_by_root[trade.instrument.root] = trade.instrument_id

        self._arrival_ordinal += 1
        heapq.heappush(
            self._heaps.setdefault(series, []),
            (_trade_order_key(trade), self._arrival_ordinal, trade, resolved_buckets),
        )
        current_max = max(previous_max if previous_max is not None else 0, trade.ts_event_ns)
        self._max_seen[series] = current_max
        watermark = current_max - self._spec.allowed_lateness_ns
        self._apply_ready(series, watermark)
        bars = self._finalize_ready(series, watermark)
        return AggregationBatch(bars=roll_bars + tuple(bars), issues=tuple(issues))

    def advance_watermark(
        self, root: str, instrument_id: int, watermark_ns: int
    ) -> AggregationBatch:
        """Advance one series only from a trusted source-progress signal."""
        if self._finished:
            raise MarketDataValidationError("cannot advance after the aggregator is finished")
        series = self._validated_series(root, instrument_id)
        if series in self._closed_series:
            raise MarketDataValidationError("cannot advance a closed contract series")
        if not isinstance(watermark_ns, int) or isinstance(watermark_ns, bool) or watermark_ns < 0:
            raise MarketDataValidationError("watermark_ns must be a non-negative integer")
        previous = self._trusted_watermarks.get(series)
        if previous is not None and watermark_ns < previous:
            raise MarketDataValidationError("trusted watermark cannot move backward")
        self._trusted_watermarks[series] = watermark_ns
        self._apply_ready(series, watermark_ns)
        bars = self._finalize_ready(series, watermark_ns)
        return AggregationBatch(bars=tuple(bars))

    def close_series(self, root: str, instrument_id: int) -> AggregationBatch:
        """Flush and retire one physical contract at an explicit roll boundary."""
        if self._finished:
            raise MarketDataValidationError("cannot close a series after finish")
        series = self._validated_series(root, instrument_id)
        if series in self._closed_series:
            return AggregationBatch()
        self._apply_ready(series, None)
        ready_keys = [key for key in self._builders if key[0] == series]
        bars = [
            self._builders.pop(key).freeze(quality=QualityState.DEGRADED)
            for key in sorted(ready_keys, key=self._bar_key_order)
        ]
        for bar in bars:
            self._remember_finalized(bar)
        self._closed_series.add(series)
        self._heaps.pop(series, None)
        return AggregationBatch(bars=tuple(bars))

    def finish(self) -> AggregationBatch:
        """Flush a finite historical stream without consulting wall-clock time."""
        if self._finished:
            return AggregationBatch()
        for series in sorted(self._heaps):
            self._apply_ready(series, None)
        bars = [
            self._builders.pop(key).freeze(quality=QualityState.DEGRADED)
            for key in sorted(self._builders, key=self._bar_key_order)
        ]
        for bar in bars:
            self._remember_finalized(bar)
        self._finished = True
        return AggregationBatch(bars=tuple(bars))

    @staticmethod
    def _validated_series(root: str, instrument_id: int) -> SeriesKey:
        if root not in {"NQ", "ES"}:
            raise MarketDataValidationError("root must be NQ or ES")
        if (
            not isinstance(instrument_id, int)
            or isinstance(instrument_id, bool)
            or instrument_id <= 0
        ):
            raise MarketDataValidationError("instrument_id must be a positive integer")
        return (root, instrument_id)

    def _is_late(self, series: SeriesKey, buckets: ResolvedBuckets) -> bool:
        for timeframe, bucket in buckets:
            finalized_end = self._finalized_end.get((series, timeframe))
            if finalized_end is not None and bucket.end_ns <= finalized_end:
                return True
        return False

    def _apply_ready(self, series: SeriesKey, watermark: int | None) -> None:
        heap = self._heaps.get(series, [])
        while heap and (watermark is None or heap[0][0][0] <= watermark):
            _, _, trade, buckets = heapq.heappop(heap)
            self._apply_trade(series, trade, buckets)

    def _apply_trade(self, series: SeriesKey, trade: TradeEvent, buckets: ResolvedBuckets) -> None:
        for timeframe, bucket in buckets:
            key = (series, timeframe, bucket.start_ns, bucket.end_ns)
            builder = self._builders.get(key)
            if builder is None:
                self._builders[key] = _MutableBar.from_trade(
                    trade,
                    timeframe,
                    bucket,
                    self._calendar.fingerprint,
                    self._spec.fingerprint,
                )
            else:
                builder.add(trade)

    def _finalize_ready(self, series: SeriesKey, watermark: int) -> list[FinalBar]:
        ready_keys = [key for key in self._builders if key[0] == series and key[3] <= watermark]
        bars = [
            self._builders.pop(key).freeze() for key in sorted(ready_keys, key=self._bar_key_order)
        ]
        for bar in bars:
            self._remember_finalized(bar)
        return bars

    def _remember_finalized(self, bar: FinalBar) -> None:
        series = (bar.instrument.root, bar.instrument_id)
        key = (series, bar.timeframe)
        self._finalized_end[key] = max(self._finalized_end.get(key, 0), bar.end_ns)

    @staticmethod
    def _issue(code: IssueCode, trade: TradeEvent, detail: str) -> MarketDataIssue:
        return MarketDataIssue(
            code=code,
            source=trade.source,
            detail=detail,
            instrument_id=trade.instrument_id,
            ts_event_ns=trade.ts_event_ns,
        )

    @staticmethod
    def _bar_key_order(key: BarKey) -> tuple[int, int, str, int, str]:
        series, timeframe, start_ns, end_ns = key
        return (end_ns, start_ns, series[0], series[1], timeframe.value)
