"""FastAPI JSON/control API for the static SP5 React application."""

from __future__ import annotations

import hmac
import os
import secrets
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    Form,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from google.auth.exceptions import GoogleAuthError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from stoic_derived.ledger.drive import (
    DriveLedgerError,
    DriveLedgerStore,
    GoogleDriveTransport,
)
from stoic_derived.ledger.outbox import LedgerOutbox

from .auth import (
    GoogleIdentityVerifier,
    IdentityVerificationError,
    IdentityVerifier,
    verify_gis_csrf,
)
from .models import (
    API_SCHEMA_VERSION,
    AuditListResponse,
    AuditRecordResponse,
    AuthConfigResponse,
    ConnectionTestRequest,
    CreateRotationRequest,
    InviteUserRequest,
    LedgerSnapshotResponse,
    MessageResponse,
    OperationResponse,
    OperationsStatusResponse,
    Role,
    RotationListResponse,
    RotationResponse,
    RotationState,
    SessionResponse,
    UpdateUserRequest,
    UserListResponse,
    UserResponse,
)
from .operations import (
    DatabentoConnectionProbe,
    DriveConnectionProbe,
    OperationsService,
)
from .projection import LedgerAuthority, ProductionLedgerAuthority, utc_string
from .settings import (
    SESSION_COOKIE_NAME,
    DashboardConfigError,
    DashboardSettings,
)
from .store import (
    AuthenticationError,
    AuthorizationError,
    ControlStoreError,
    DashboardStore,
    PrimaryAdminError,
    StoredAuditRecord,
    StoredRotation,
    StoredSession,
    StoredUser,
)

Clock = Callable[[], int]


class _RequestBodyTooLarge(Exception):
    pass


class RequestBodyLimitMiddleware:
    """Enforce the real streamed request size, not only a claimed header."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        lengths = [
            value for name, value in scope.get("headers", []) if name.lower() == b"content-length"
        ]
        if len(lengths) > 1:
            await _error_response(400, "Invalid request")(scope, receive, send)
            return
        if lengths:
            try:
                claimed_length = int(lengths[0].decode("ascii"))
            except (UnicodeDecodeError, ValueError):  # fmt: skip
                await _error_response(400, "Invalid request")(scope, receive, send)
                return
            if claimed_length < 0:
                await _error_response(400, "Invalid request")(scope, receive, send)
                return
            if claimed_length > self._max_bytes:
                await _error_response(413, "Request body is too large")(scope, receive, send)
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self._max_bytes:
                    raise _RequestBodyTooLarge
            return message

        try:
            await self._app(scope, limited_receive, send)
        except _RequestBodyTooLarge:
            await _error_response(413, "Request body is too large")(scope, receive, send)


@dataclass(frozen=True, slots=True)
class DashboardServices:
    settings: DashboardSettings
    store: DashboardStore
    identity_verifier: IdentityVerifier
    ledger_authority: LedgerAuthority
    operations: OperationsService
    clock: Clock


ServiceBuilder = Callable[[DashboardSettings], DashboardServices]


def build_production_services(settings: DashboardSettings) -> DashboardServices:
    clock = time.time_ns
    store = DashboardStore(settings.control_db_path)
    outbox = LedgerOutbox(settings.outbox_path)
    drive_store: DriveLedgerStore | None = None
    try:
        drive_config = settings.drive_config(os.environ)
        drive_store = DriveLedgerStore(
            GoogleDriveTransport.from_adc(),
            drive_config,
        )
    except DashboardConfigError, DriveLedgerError:
        drive_store = None
    except GoogleAuthError:
        drive_store = None
    authority = ProductionLedgerAuthority(
        outbox=outbox,
        drive_store=drive_store,
        release_path=settings.release_path,
        release_sha256=settings.release_sha256,
        release_public_key=settings.release_public_key,
    )
    operations = OperationsService(
        settings=settings,
        store=store,
        authority=authority,
        probes={
            "market_data": DatabentoConnectionProbe(),
            "drive": DriveConnectionProbe(authority),
        },
        process_started_utc_ns=clock(),
        clock=clock,
    )
    return DashboardServices(
        settings=settings,
        store=store,
        identity_verifier=GoogleIdentityVerifier(settings.google_web_client_id),
        ledger_authority=authority,
        operations=operations,
        clock=clock,
    )


def create_app(
    settings: DashboardSettings | None = None,
    *,
    service_builder: ServiceBuilder | None = None,
) -> FastAPI:
    selected_settings = settings or DashboardSettings.from_environment()
    selected_builder = service_builder or build_production_services

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        app.state.dashboard_services = selected_builder(selected_settings)
        try:
            yield
        finally:
            app.state.dashboard_services = None

    app = FastAPI(
        title="Stoic Derived Dashboard Control API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        openapi_tags=[
            {"name": "auth", "description": "Google authentication and current session"},
            {"name": "ledger", "description": "Verified observational ledger projection"},
            {"name": "operations", "description": "Operational state"},
            {"name": "admin", "description": "Audited administrator controls"},
        ],
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(selected_settings.allowed_hosts),
    )
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_bytes=selected_settings.max_request_bytes,
    )

    @app.middleware("http")
    async def control_api_headers(request: Request, call_next: Callable[..., Any]) -> Any:
        request.state.request_id = secrets.token_hex(16)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Request-ID"] = str(request.state.request_id)
        if selected_settings.public_origin.startswith("https://"):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    _install_error_handlers(app)
    app.include_router(_build_router())
    return app


def _install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return _error_response(exc.status_code, detail)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, __: RequestValidationError) -> JSONResponse:
        return _error_response(422, "Request validation failed")

    @app.exception_handler(AuthenticationError)
    async def authentication_error(_: Request, __: AuthenticationError) -> JSONResponse:
        return _error_response(401, "Authentication required")

    @app.exception_handler(AuthorizationError)
    async def authorization_error(_: Request, __: AuthorizationError) -> JSONResponse:
        return _error_response(403, "Administrator access required")

    @app.exception_handler(PrimaryAdminError)
    async def primary_error(_: Request, exc: PrimaryAdminError) -> JSONResponse:
        return _error_response(409, str(exc))

    @app.exception_handler(ControlStoreError)
    async def control_error(_: Request, exc: ControlStoreError) -> JSONResponse:
        return _error_response(400, str(exc))

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, __: Exception) -> JSONResponse:
        return _error_response(500, "Dashboard request failed")


def _error_response(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"schema_version": API_SCHEMA_VERSION, "detail": detail},
    )


def get_services(request: Request) -> DashboardServices:
    services = getattr(request.app.state, "dashboard_services", None)
    if not isinstance(services, DashboardServices):
        raise HTTPException(status_code=503, detail="Dashboard services are unavailable")
    return services


ServicesDependency = Annotated[DashboardServices, Depends(get_services)]


def current_session(
    request: Request,
    services: ServicesDependency,
) -> StoredSession:
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if raw_token is None:
        raise AuthenticationError("invalid session")
    return services.store.resolve_session(raw_token, now_utc_ns=services.clock())


SessionDependency = Annotated[StoredSession, Depends(current_session)]


def require_admin(session: SessionDependency) -> StoredSession:
    if session.user.role is not Role.ADMIN:
        raise AuthorizationError("administrator access is required")
    return session


AdminDependency = Annotated[StoredSession, Depends(require_admin)]


def require_mutation(
    request: Request,
    services: ServicesDependency,
    session: SessionDependency,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> StoredSession:
    origin = request.headers.get("origin")
    if origin != services.settings.public_origin:
        raise HTTPException(status_code=403, detail="Mutation origin is not allowed")
    if csrf_token is None or not hmac.compare_digest(csrf_token, session.csrf_token):
        raise HTTPException(status_code=403, detail="CSRF validation failed")
    return session


MutationDependency = Annotated[StoredSession, Depends(require_mutation)]


def require_admin_mutation(session: MutationDependency) -> StoredSession:
    if session.user.role is not Role.ADMIN:
        raise AuthorizationError("administrator access is required")
    return session


AdminMutationDependency = Annotated[StoredSession, Depends(require_admin_mutation)]
UserIdParameter = Annotated[
    str,
    Path(
        min_length=1,
        max_length=64,
        pattern=r"^(?:primary-admin|[0-9a-f]{32})$",
    ),
]
RotationIdParameter = Annotated[
    str,
    Path(min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$"),
]


def _build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get(
        "/auth/config",
        response_model=AuthConfigResponse,
        tags=["auth"],
        summary="Get public Google sign-in configuration",
    )
    def auth_config(services: ServicesDependency) -> AuthConfigResponse:
        return AuthConfigResponse(
            client_id=services.settings.google_web_client_id,
            login_uri=services.settings.google_login_uri,
        )

    @router.post(
        "/auth/google",
        response_class=RedirectResponse,
        status_code=status.HTTP_303_SEE_OTHER,
        tags=["auth"],
        summary="Receive a Google Identity Services credential",
    )
    def google_login(
        services: ServicesDependency,
        credential: Annotated[str, Form(min_length=100, max_length=16_384)],
        g_csrf_token: Annotated[str, Form(min_length=1, max_length=512)],
        request: Request,
    ) -> RedirectResponse:
        try:
            verify_gis_csrf(request.cookies.get("g_csrf_token"), g_csrf_token)
        except IdentityVerificationError as exc:
            raise HTTPException(status_code=403, detail="Invalid Google sign-in request") from exc
        try:
            identity = services.identity_verifier.verify(credential)
            now = services.clock()
            user = services.store.bind_google_identity(
                google_sub=identity.google_sub,
                authoritative_email=identity.authoritative_email,
                now_utc_ns=now,
            )
            raw_session = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(32)
            services.store.create_session(
                user=user,
                raw_session_token=raw_session,
                csrf_token=csrf,
                now_utc_ns=now,
                ttl_seconds=services.settings.session_ttl_seconds,
            )
        except AuthenticationError:
            return RedirectResponse(
                url=f"{services.settings.public_origin}/?auth_error=access_denied",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        response = RedirectResponse(
            url=services.settings.public_origin,
            status_code=status.HTTP_303_SEE_OTHER,
        )
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=raw_session,
            max_age=services.settings.session_ttl_seconds,
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )
        return response

    @router.get(
        "/session",
        response_model=SessionResponse,
        tags=["auth"],
        summary="Get the current server-side session",
    )
    def session_info(session: SessionDependency) -> SessionResponse:
        return SessionResponse(
            user=_user_response(session.user),
            csrf_token=session.csrf_token,
            expires_at_utc=utc_string(session.expires_utc_ns),
        )

    @router.post(
        "/session/logout",
        response_model=MessageResponse,
        tags=["auth"],
        summary="Revoke the current session",
    )
    def logout(
        request: Request,
        services: ServicesDependency,
        _: MutationDependency,
    ) -> JSONResponse:
        raw_session = request.cookies.get(SESSION_COOKIE_NAME)
        if raw_session is not None:
            services.store.revoke_session(raw_session)
        response = JSONResponse(
            content=MessageResponse(message="Session revoked").model_dump(mode="json")
        )
        response.delete_cookie(
            key=SESSION_COOKIE_NAME,
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )
        return response

    @router.get(
        "/ledger",
        response_model=LedgerSnapshotResponse,
        tags=["ledger"],
        summary="Get the verified observational ledger",
    )
    def ledger(
        services: ServicesDependency,
        _: SessionDependency,
    ) -> LedgerSnapshotResponse:
        return services.ledger_authority.snapshot(generated_at_ns=services.clock())

    @router.get(
        "/operations/status",
        response_model=OperationsStatusResponse,
        tags=["operations"],
        summary="Get operational readiness and connectivity",
    )
    def operations_status(
        services: ServicesDependency,
        _: SessionDependency,
    ) -> OperationsStatusResponse:
        return services.operations.status()

    @router.get(
        "/admin/users",
        response_model=UserListResponse,
        tags=["admin"],
        summary="List invited dashboard users",
    )
    def list_users(
        services: ServicesDependency,
        _: AdminDependency,
    ) -> UserListResponse:
        return UserListResponse(
            users=tuple(_user_response(user) for user in services.store.list_users())
        )

    @router.post(
        "/admin/users",
        response_model=UserResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["admin"],
        summary="Invite a dashboard user",
    )
    def invite_user(
        payload: InviteUserRequest,
        request: Request,
        services: ServicesDependency,
        session: AdminMutationDependency,
    ) -> UserResponse:
        user = services.store.invite_user(
            actor=session.user,
            email=payload.email,
            role=payload.role,
            now_utc_ns=services.clock(),
            request_id=_request_id(request),
        )
        return _user_response(user)

    @router.patch(
        "/admin/users/{user_id}",
        response_model=UserResponse,
        tags=["admin"],
        summary="Change a dashboard user's role or enabled state",
    )
    def update_user(
        user_id: UserIdParameter,
        payload: UpdateUserRequest,
        request: Request,
        services: ServicesDependency,
        session: AdminMutationDependency,
    ) -> UserResponse:
        user = services.store.update_user(
            actor=session.user,
            user_id=user_id,
            role=payload.role,
            enabled=payload.enabled,
            now_utc_ns=services.clock(),
            request_id=_request_id(request),
        )
        return _user_response(user)

    @router.delete(
        "/admin/users/{user_id}",
        response_model=MessageResponse,
        tags=["admin"],
        summary="Remove a non-primary dashboard user",
    )
    def delete_user(
        user_id: UserIdParameter,
        request: Request,
        services: ServicesDependency,
        session: AdminMutationDependency,
    ) -> MessageResponse:
        services.store.remove_user(
            actor=session.user,
            user_id=user_id,
            now_utc_ns=services.clock(),
            request_id=_request_id(request),
        )
        return MessageResponse(message="User removed")

    @router.post(
        "/admin/operations/connection-tests",
        response_model=OperationResponse,
        tags=["admin"],
        summary="Run a bounded read-only connection test",
    )
    def test_connection(
        payload: ConnectionTestRequest,
        request: Request,
        services: ServicesDependency,
        session: AdminMutationDependency,
    ) -> OperationResponse:
        return services.operations.test_connection(
            actor=session.user,
            target=payload.target,
            request_id=_request_id(request),
        )

    @router.post(
        "/admin/operations/drive-refresh",
        response_model=OperationResponse,
        tags=["admin"],
        summary="Refresh verified Drive ledger authority",
    )
    def refresh_drive(
        request: Request,
        services: ServicesDependency,
        session: AdminMutationDependency,
    ) -> OperationResponse:
        return services.operations.refresh_drive(
            actor=session.user,
            request_id=_request_id(request),
        )

    @router.post(
        "/admin/operations/drive-publish",
        response_model=OperationResponse,
        tags=["admin"],
        summary="Publish committed outbox events and verify Drive",
    )
    def publish_drive(
        request: Request,
        services: ServicesDependency,
        session: AdminMutationDependency,
    ) -> OperationResponse:
        return services.operations.publish_drive(
            actor=session.user,
            request_id=_request_id(request),
        )

    @router.get(
        "/admin/key-rotations",
        response_model=RotationListResponse,
        tags=["admin"],
        summary="List Databento key-rotation workflows",
    )
    def list_rotations(
        services: ServicesDependency,
        _: AdminDependency,
    ) -> RotationListResponse:
        return RotationListResponse(
            rotations=tuple(_rotation_response(item) for item in services.store.list_rotations())
        )

    @router.post(
        "/admin/key-rotations",
        response_model=RotationResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["admin"],
        summary="Start a secret-free Databento key-rotation workflow",
    )
    def create_rotation(
        payload: CreateRotationRequest,
        request: Request,
        services: ServicesDependency,
        session: AdminMutationDependency,
    ) -> RotationResponse:
        rotation = services.store.create_rotation(
            actor=session.user,
            target=payload.target,
            now_utc_ns=services.clock(),
            request_id=_request_id(request),
        )
        return _rotation_response(rotation)

    @router.post(
        "/admin/key-rotations/{rotation_id}/verify",
        response_model=RotationResponse,
        tags=["admin"],
        summary="Verify the externally updated Databento credential",
    )
    def verify_rotation(
        rotation_id: RotationIdParameter,
        request: Request,
        services: ServicesDependency,
        session: AdminMutationDependency,
    ) -> RotationResponse:
        return _rotation_response(
            services.operations.verify_rotation(
                actor=session.user,
                rotation_id=rotation_id,
                request_id=_request_id(request),
            )
        )

    @router.post(
        "/admin/key-rotations/{rotation_id}/cancel",
        response_model=RotationResponse,
        tags=["admin"],
        summary="Cancel an open Databento key-rotation workflow",
    )
    def cancel_rotation(
        rotation_id: RotationIdParameter,
        request: Request,
        services: ServicesDependency,
        session: AdminMutationDependency,
    ) -> RotationResponse:
        rotation = services.store.finish_rotation(
            actor=session.user,
            rotation_id=rotation_id,
            state=RotationState.CANCELLED,
            detail="Rotation workflow cancelled before verification",
            now_utc_ns=services.clock(),
            request_id=_request_id(request),
        )
        return _rotation_response(rotation)

    @router.get(
        "/admin/audit",
        response_model=AuditListResponse,
        tags=["admin"],
        summary="Get recent append-only dashboard audit evidence",
    )
    def list_audit(
        services: ServicesDependency,
        _: AdminDependency,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> AuditListResponse:
        return AuditListResponse(
            records=tuple(_audit_response(item) for item in services.store.list_audit(limit=limit))
        )

    return router


def _request_id(request: Request) -> str:
    return str(request.state.request_id)


def _user_response(user: StoredUser) -> UserResponse:
    return UserResponse(
        user_id=user.user_id,
        email=user.display_email,
        role=user.role,
        enabled=user.enabled,
        primary=user.primary,
        identity_bound=user.google_sub is not None,
    )


def _rotation_response(rotation: StoredRotation) -> RotationResponse:
    return RotationResponse(
        rotation_id=rotation.rotation_id,
        target="databento",
        state=rotation.state,
        requested_at_utc=utc_string(rotation.requested_utc_ns),
        updated_at_utc=utc_string(rotation.updated_utc_ns),
        requested_by_email=rotation.requested_by_email,
        detail=rotation.detail,
    )


def _audit_response(record: StoredAuditRecord) -> AuditRecordResponse:
    return AuditRecordResponse(
        audit_id=record.audit_id,
        occurred_at_utc=utc_string(record.occurred_utc_ns),
        actor_email=record.actor_email,
        action=record.action,
        resource_type=record.resource_type,
        resource_id=record.resource_id,
        request_id=record.request_id,
        before=record.before,
        after=record.after,
        record_hash=record.record_hash,
    )


__all__ = [
    "DashboardServices",
    "ServiceBuilder",
    "build_production_services",
    "create_app",
]
