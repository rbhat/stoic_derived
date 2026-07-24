"""Truthful operational state and constrained management workflows."""

from __future__ import annotations

import os
import re
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from stoic_derived.ledger.runner import readiness
from stoic_derived.market_data.live import DATASET

from .models import (
    ComponentState,
    ComponentStatusResponse,
    DriveActivityResponse,
    LastDriveSuccessResponse,
    OperationResponse,
    OperationsStatusResponse,
    OperationState,
    OutboxStatusResponse,
    RotationState,
)
from .projection import LedgerAuthority, utc_string
from .settings import DashboardSettings
from .store import ControlStoreError, DashboardStore, StoredRotation, StoredUser

_PRINCIPAL_PATTERN = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,128}@[A-Za-z0-9.-]{1,190}$")


@dataclass(frozen=True, slots=True)
class ProbeResult:
    ready: bool
    detail: str


class ConnectionProbe(Protocol):
    def run(self) -> ProbeResult: ...


class DatabentoConnectionProbe:
    """One bounded read-only metadata request with no secret-bearing output."""

    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        self._environment = environment if environment is not None else os.environ

    def run(self) -> ProbeResult:
        key = self._environment.get("DATABENTO_API_KEY")
        if key is None or not key:
            return ProbeResult(False, "Databento credential is not configured")
        try:
            import databento as db

            client = db.Historical(key)
            client.metadata.get_dataset_range(dataset=DATASET)
        except Exception:
            return ProbeResult(False, "Databento metadata connection failed")
        return ProbeResult(True, "Databento metadata connection succeeded")


class DriveConnectionProbe:
    def __init__(self, authority: LedgerAuthority) -> None:
        self._authority = authority

    def run(self) -> ProbeResult:
        ready, _, _ = self._authority.drive_status()
        return ProbeResult(
            ready,
            (
                "Drive authority connection succeeded"
                if ready
                else "Drive authority connection failed"
            ),
        )


class OperationsService:
    def __init__(
        self,
        *,
        settings: DashboardSettings,
        store: DashboardStore,
        authority: LedgerAuthority,
        probes: Mapping[str, ConnectionProbe],
        process_started_utc_ns: int,
        clock: Callable[[], int] = time.time_ns,
    ) -> None:
        if set(probes) != {"market_data", "drive"}:
            raise ValueError("operations probes must contain market_data and drive")
        self._settings = settings
        self._store = store
        self._authority = authority
        self._probes = dict(probes)
        self._process_started_utc_ns = process_started_utc_ns
        self._clock = clock

    def status(self) -> OperationsStatusResponse:
        now = self._clock()
        preflight = readiness(
            self._settings.release_path,
            self._settings.release_sha256,
            self._settings.release_public_key,
        )
        release_ready = preflight.status == "complete"
        release_detail = (
            "Signed production strategy release is ready"
            if release_ready
            else "; ".join(
                sorted({f"{item['code']}: {item['message']}" for item in preflight.blockers})
            )
        )
        drive_ready, _, principal = self._authority.drive_status()
        display_principal = _sanitized_principal(principal)
        drive_detail = (
            "Drive authority is verified" if drive_ready else "Drive authority verification failed"
        )
        if drive_ready and display_principal is not None:
            drive_detail = f"{drive_detail} for {display_principal}"

        recorded = self._store.connection_status()
        market_component = self._recorded_component("market_data", recorded.get("market_data"))
        drive_probe_component = self._recorded_component(
            "drive_connection",
            recorded.get("drive"),
        )
        if recorded.get("drive") is None:
            drive_probe_component = ComponentStatusResponse(
                component="drive_connection",
                state=ComponentState.READY if drive_ready else ComponentState.BLOCKED,
                detail=drive_detail,
            )

        pending, acknowledged, maximum_attempts = self._authority.outbox_status()
        drive_success = self._store.drive_success_status()
        outbox_state = ComponentState.READY if pending == 0 else ComponentState.DEGRADED
        outbox_detail = (
            "Every committed local event is acknowledged on Drive"
            if pending == 0
            else f"{pending} committed event(s) await verified Drive publication"
        )
        watchdog_state = ComponentState.BLOCKED if not release_ready else ComponentState.UNKNOWN
        watchdog_detail = (
            "Watchdog is blocked while production strategy readiness is blocked"
            if not release_ready
            else "No current-session watchdog heartbeat is available through SP4 evidence"
        )
        components = (
            ComponentStatusResponse(
                component="api",
                state=ComponentState.RUNNING,
                detail="Dashboard JSON/control API process is running",
                observed_at_utc=utc_string(now),
            ),
            ComponentStatusResponse(
                component="release",
                state=ComponentState.READY if release_ready else ComponentState.BLOCKED,
                detail=release_detail,
                observed_at_utc=utc_string(now),
            ),
            ComponentStatusResponse(
                component="drive",
                state=ComponentState.READY if drive_ready else ComponentState.BLOCKED,
                detail=drive_detail,
                observed_at_utc=utc_string(now),
            ),
            market_component,
            drive_probe_component,
            ComponentStatusResponse(
                component="watchdog",
                state=watchdog_state,
                detail=watchdog_detail,
                observed_at_utc=utc_string(now),
            ),
            ComponentStatusResponse(
                component="sync",
                state=outbox_state,
                detail=outbox_detail,
                observed_at_utc=utc_string(now),
            ),
        )
        return OperationsStatusResponse(
            generated_at_utc=utc_string(now),
            process_started_at_utc=utc_string(self._process_started_utc_ns),
            components=components,
            outbox=OutboxStatusResponse(
                state=outbox_state,
                pending_count=pending,
                acknowledged_count=acknowledged,
                maximum_pending_attempts=maximum_attempts,
                detail=outbox_detail,
            ),
            drive_activity=DriveActivityResponse(
                refresh=self._last_drive_success(drive_success.get("drive_refresh")),
                publish=self._last_drive_success(drive_success.get("drive_publish")),
            ),
        )

    def test_connection(
        self,
        *,
        actor: StoredUser,
        target: str,
        request_id: str,
    ) -> OperationResponse:
        if target not in self._probes:
            raise ValueError("unsupported connection target")
        operation_id = secrets.token_hex(16)
        started = self._clock()
        operation = f"connection_test.{target}"
        self._store.record_operation_intent(
            actor=actor,
            operation_id=operation_id,
            operation=operation,
            now_utc_ns=started,
            request_id=request_id,
        )
        try:
            result = self._probes[target].run()
            state = OperationState.COMPLETE if result.ready else OperationState.BLOCKED
            detail = _connection_detail(target, ready=result.ready)
        except Exception:
            state = OperationState.FAILED
            detail = f"{target.replace('_', ' ').title()} connection test failed"
        finished = self._clock()
        self._store.record_operation_result(
            actor=actor,
            operation_id=operation_id,
            operation=operation,
            state=state.value,
            detail=detail,
            now_utc_ns=finished,
            request_id=request_id,
            connection_target=target,
        )
        return OperationResponse(
            operation_id=operation_id,
            operation=operation,
            state=state,
            detail=detail,
            affected_count=0,
            observed_at_utc=utc_string(finished),
        )

    def refresh_drive(self, *, actor: StoredUser, request_id: str) -> OperationResponse:
        return self._drive_operation(
            actor=actor,
            request_id=request_id,
            operation="drive_refresh",
            publish=False,
        )

    def publish_drive(self, *, actor: StoredUser, request_id: str) -> OperationResponse:
        return self._drive_operation(
            actor=actor,
            request_id=request_id,
            operation="drive_publish",
            publish=True,
        )

    def verify_rotation(
        self,
        *,
        actor: StoredUser,
        rotation_id: str,
        request_id: str,
    ) -> StoredRotation:
        current = self._store.get_rotation(rotation_id)
        if current.state is not RotationState.REQUESTED:
            raise ControlStoreError("rotation is already terminal")
        operation_id = secrets.token_hex(16)
        operation = "key_rotation_verify"
        self._store.record_operation_intent(
            actor=actor,
            operation_id=operation_id,
            operation=operation,
            now_utc_ns=self._clock(),
            request_id=request_id,
        )
        try:
            result = self._probes["market_data"].run()
        except Exception:
            result = ProbeResult(False, "Databento credential verification failed")
        result_detail = _connection_detail("market_data", ready=result.ready)
        self._store.record_operation_result(
            actor=actor,
            operation_id=operation_id,
            operation=operation,
            state="complete" if result.ready else "failed",
            detail=result_detail,
            now_utc_ns=self._clock(),
            request_id=request_id,
            connection_target="market_data",
        )
        return self._store.finish_rotation(
            actor=actor,
            rotation_id=rotation_id,
            state=RotationState.VERIFIED if result.ready else RotationState.FAILED,
            detail=(
                "Active Databento credential was verified"
                if result.ready
                else "Active Databento credential could not be verified"
            ),
            now_utc_ns=self._clock(),
            request_id=request_id,
        )

    def _drive_operation(
        self,
        *,
        actor: StoredUser,
        request_id: str,
        operation: str,
        publish: bool,
    ) -> OperationResponse:
        operation_id = secrets.token_hex(16)
        started = self._clock()
        self._store.record_operation_intent(
            actor=actor,
            operation_id=operation_id,
            operation=operation,
            now_utc_ns=started,
            request_id=request_id,
        )
        try:
            if publish:
                snapshot, affected = self._authority.publish(generated_at_ns=self._clock())
            else:
                snapshot = self._authority.refresh(generated_at_ns=self._clock())
                affected = self._observation_count(snapshot)
            ledger_state = snapshot.ledger.status
            if ledger_state == "ready":
                state = OperationState.COMPLETE
                detail = (
                    f"Published {affected} committed event(s) and refreshed Drive authority"
                    if publish
                    else f"Refreshed {affected} verified ledger observation(s)"
                )
            elif ledger_state == "blocked":
                state = OperationState.BLOCKED
                detail = "Drive operation is blocked by production readiness"
                affected = 0
            else:
                state = OperationState.FAILED
                detail = "Verified ledger authority is unavailable"
                affected = 0
        except Exception:
            state = OperationState.FAILED
            detail = "Drive operation failed"
            affected = 0
        finished = self._clock()
        self._store.record_operation_result(
            actor=actor,
            operation_id=operation_id,
            operation=operation,
            state=state.value,
            detail=detail,
            now_utc_ns=finished,
            request_id=request_id,
            affected_count=affected,
        )
        return OperationResponse(
            operation_id=operation_id,
            operation=operation,
            state=state,
            detail=detail,
            affected_count=affected,
            observed_at_utc=utc_string(finished),
        )

    @staticmethod
    def _observation_count(snapshot: object) -> int:
        ledger = getattr(snapshot, "ledger", None)
        if getattr(ledger, "status", None) != "ready":
            return 0
        return sum(
            len(getattr(ledger, name))
            for name in (
                "open_observations",
                "closed_observations",
                "unresolved_observations",
            )
        )

    @staticmethod
    def _last_drive_success(
        recorded: tuple[int, int] | None,
    ) -> LastDriveSuccessResponse:
        if recorded is None:
            return LastDriveSuccessResponse(observed_at_utc=None, affected_count=0)
        observed_ns, affected_count = recorded
        return LastDriveSuccessResponse(
            observed_at_utc=utc_string(observed_ns),
            affected_count=affected_count,
        )

    @staticmethod
    def _recorded_component(
        component: str,
        recorded: tuple[str, str, int] | None,
    ) -> ComponentStatusResponse:
        if recorded is None:
            return ComponentStatusResponse(
                component=component,
                state=ComponentState.UNKNOWN,
                detail="No connection test has been recorded",
            )
        state, detail, checked_ns = recorded
        mapping = {
            "ready": ComponentState.READY,
            "blocked": ComponentState.BLOCKED,
            "failed": ComponentState.DEGRADED,
        }
        return ComponentStatusResponse(
            component=component,
            state=mapping[state],
            detail=detail,
            observed_at_utc=utc_string(checked_ns),
        )


def _connection_detail(target: str, *, ready: bool) -> str:
    if target == "market_data":
        return (
            "Databento metadata connection succeeded"
            if ready
            else "Databento metadata connection failed"
        )
    return "Drive authority connection succeeded" if ready else "Drive authority connection failed"


def _sanitized_principal(principal: str | None) -> str | None:
    if principal is None:
        return None
    normalized = principal.strip()
    if (
        len(normalized) > 320
        or ".." in normalized
        or _PRINCIPAL_PATTERN.fullmatch(normalized) is None
    ):
        return None
    local, _, domain = normalized.rpartition("@")
    return f"{local[0]}***@{domain.casefold()}"


__all__ = [
    "ConnectionProbe",
    "DatabentoConnectionProbe",
    "DriveConnectionProbe",
    "OperationsService",
    "ProbeResult",
]
