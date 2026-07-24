"""Strict request and response contracts for the SP5 JSON API."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

API_SCHEMA_VERSION = "dashboard-api/v1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Role(StrEnum):
    ADMIN = "admin"
    VIEWER = "viewer"


class ComponentState(StrEnum):
    RUNNING = "running"
    READY = "ready"
    BLOCKED = "blocked"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"
    STALE = "stale"


class OperationState(StrEnum):
    COMPLETE = "complete"
    BLOCKED = "blocked"
    FAILED = "failed"


class RotationState(StrEnum):
    REQUESTED = "requested"
    VERIFIED = "verified"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AuthConfigResponse(StrictModel):
    schema_version: Literal["dashboard-api/v1"] = "dashboard-api/v1"
    client_id: str
    login_uri: str
    ux_mode: Literal["redirect"] = "redirect"


class UserResponse(StrictModel):
    schema_version: Literal["dashboard-api/v1"] = "dashboard-api/v1"
    user_id: str
    email: str
    role: Role
    enabled: bool
    primary: bool
    identity_bound: bool


class SessionResponse(StrictModel):
    schema_version: Literal["dashboard-api/v1"] = "dashboard-api/v1"
    user: UserResponse
    csrf_token: str
    expires_at_utc: str


class MessageResponse(StrictModel):
    schema_version: Literal["dashboard-api/v1"] = "dashboard-api/v1"
    message: str


class ExactRResponse(StrictModel):
    numerator: int
    denominator: int = Field(gt=0)
    display: str


class ConflictResponse(StrictModel):
    code: str
    detail: str


class ObservationResponse(StrictModel):
    signal_id: str
    instrument: Literal["NQ", "ES"]
    signal_type: Literal["Scalp", "Day", "Swing", "Position"]
    state: Literal["pending", "active", "closed", "unresolved"]
    direction: Literal["long", "short"]
    setup_type: str
    confidence: int = Field(ge=0, le=100)
    signal_ts_utc: str
    planned_entry_price_ticks: int = Field(gt=0)
    planned_stop_price_ticks: int = Field(gt=0)
    planned_target_price_ticks: int = Field(gt=0)
    entry_observed_ts_utc: str | None
    entry_observed_price_ticks: int | None
    close_observed_ts_utc: str | None
    close_observed_price_ticks: int | None
    terminal_reason: str | None
    observed_pnl_ticks: int | None
    observed_pnl_r: ExactRResponse | None
    hold_seconds: int | None
    conflicts: tuple[ConflictResponse, ...]
    execution: Literal[False] = False
    orders_placed: Literal[0] = 0


class LedgerReady(StrictModel):
    status: Literal["ready"] = "ready"
    open_observations: tuple[ObservationResponse, ...]
    closed_observations: tuple[ObservationResponse, ...]
    unresolved_observations: tuple[ObservationResponse, ...]
    source: Literal["verified_drive_plus_undelivered_outbox"] = (
        "verified_drive_plus_undelivered_outbox"
    )
    execution: Literal[False] = False
    orders_placed: Literal[0] = 0


class LedgerBlocked(StrictModel):
    status: Literal["blocked"] = "blocked"
    blockers: tuple[str, ...]
    observation_count: Literal[0] = 0
    execution: Literal[False] = False
    orders_placed: Literal[0] = 0


class LedgerErrorState(StrictModel):
    status: Literal["error"] = "error"
    detail: str
    observation_count: Literal[0] = 0
    execution: Literal[False] = False
    orders_placed: Literal[0] = 0


LedgerStateResponse = Annotated[
    LedgerReady | LedgerBlocked | LedgerErrorState,
    Field(discriminator="status"),
]


class LedgerSnapshotResponse(StrictModel):
    schema_version: Literal["dashboard-api/v1"] = "dashboard-api/v1"
    generated_at_utc: str
    ledger: LedgerStateResponse


class ComponentStatusResponse(StrictModel):
    component: str
    state: ComponentState
    detail: str
    observed_at_utc: str | None = None


class OutboxStatusResponse(StrictModel):
    state: ComponentState
    pending_count: int = Field(ge=0)
    acknowledged_count: int = Field(ge=0)
    maximum_pending_attempts: int = Field(ge=0)
    detail: str


class LastDriveSuccessResponse(StrictModel):
    observed_at_utc: str | None
    affected_count: int = Field(ge=0)


class DriveActivityResponse(StrictModel):
    refresh: LastDriveSuccessResponse
    publish: LastDriveSuccessResponse


class OperationsStatusResponse(StrictModel):
    schema_version: Literal["dashboard-api/v1"] = "dashboard-api/v1"
    generated_at_utc: str
    process_started_at_utc: str
    components: tuple[ComponentStatusResponse, ...]
    outbox: OutboxStatusResponse
    drive_activity: DriveActivityResponse
    execution: Literal[False] = False
    orders_placed: Literal[0] = 0


class UserListResponse(StrictModel):
    schema_version: Literal["dashboard-api/v1"] = "dashboard-api/v1"
    users: tuple[UserResponse, ...]


class InviteUserRequest(StrictModel):
    email: str = Field(min_length=3, max_length=320)
    role: Annotated[Role, Field(strict=False)]


class UpdateUserRequest(StrictModel):
    role: Annotated[Role, Field(strict=False)] | None = None
    enabled: bool | None = None

    @model_validator(mode="after")
    def require_change(self) -> UpdateUserRequest:
        if self.role is None and self.enabled is None:
            raise ValueError("at least one user change is required")
        return self


class ConnectionTestRequest(StrictModel):
    target: Literal["market_data", "drive"]


class OperationResponse(StrictModel):
    schema_version: Literal["dashboard-api/v1"] = "dashboard-api/v1"
    operation_id: str
    operation: str
    state: OperationState
    detail: str
    affected_count: int = Field(ge=0)
    observed_at_utc: str
    execution: Literal[False] = False
    orders_placed: Literal[0] = 0


class CreateRotationRequest(StrictModel):
    target: Literal["databento"]


class RotationResponse(StrictModel):
    schema_version: Literal["dashboard-api/v1"] = "dashboard-api/v1"
    rotation_id: str
    target: Literal["databento"]
    state: RotationState
    requested_at_utc: str
    updated_at_utc: str
    requested_by_email: str
    detail: str


class RotationListResponse(StrictModel):
    schema_version: Literal["dashboard-api/v1"] = "dashboard-api/v1"
    rotations: tuple[RotationResponse, ...]


class AuditRecordResponse(StrictModel):
    audit_id: int = Field(gt=0)
    occurred_at_utc: str
    actor_email: str
    action: str
    resource_type: str
    resource_id: str
    request_id: str
    before: dict[str, object] | None
    after: dict[str, object] | None
    record_hash: str


class AuditListResponse(StrictModel):
    schema_version: Literal["dashboard-api/v1"] = "dashboard-api/v1"
    records: tuple[AuditRecordResponse, ...]


__all__ = [
    "API_SCHEMA_VERSION",
    "AuditListResponse",
    "AuditRecordResponse",
    "AuthConfigResponse",
    "ComponentState",
    "ComponentStatusResponse",
    "ConnectionTestRequest",
    "CreateRotationRequest",
    "DriveActivityResponse",
    "ExactRResponse",
    "InviteUserRequest",
    "LastDriveSuccessResponse",
    "LedgerBlocked",
    "LedgerErrorState",
    "LedgerReady",
    "LedgerSnapshotResponse",
    "MessageResponse",
    "ObservationResponse",
    "OperationResponse",
    "OperationState",
    "OperationsStatusResponse",
    "OutboxStatusResponse",
    "Role",
    "RotationListResponse",
    "RotationResponse",
    "RotationState",
    "SessionResponse",
    "UpdateUserRequest",
    "UserListResponse",
    "UserResponse",
]
