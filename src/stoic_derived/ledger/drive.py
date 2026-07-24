"""Google Drive authority adapter for immutable ledger event objects."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Any, Protocol, cast

from stoic_derived.signal_engine.model import SignalType

from .codec import decode_event
from .model import SCHEMA_VERSION, LedgerError, LedgerEvent, LedgerLimits
from .outbox import LedgerOutbox, PendingDelivery

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
EVENT_MIME_TYPE = "application/json"


class DriveLedgerError(LedgerError):
    """Raised when Drive cannot be proven to contain exact ledger evidence."""


class DriveHTTPError(DriveLedgerError):
    """A sanitized Drive HTTP failure with retry-relevant status."""

    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        super().__init__(f"Drive HTTP {status}: {detail}")


class OwnershipMode(StrEnum):
    """Explicitly supported Drive ownership arrangements."""

    SHARED_DRIVE_SERVICE_ACCOUNT = "shared_drive_service_account"
    DELEGATED_USER = "delegated_user"


@dataclass(frozen=True, slots=True)
class DriveLedgerConfig:
    """Pinned authority boundary and four Type folders."""

    ownership_mode: OwnershipMode
    root_folder_id: str
    type_folders: tuple[tuple[SignalType, str], ...]
    shared_drive_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.ownership_mode, OwnershipMode):
            raise DriveLedgerError("ownership_mode must be an OwnershipMode")
        if not isinstance(self.root_folder_id, str) or not self.root_folder_id:
            raise DriveLedgerError("root_folder_id must be non-empty")
        expected_order = tuple(sorted(SignalType, key=lambda item: item.value))
        if tuple(item[0] for item in self.type_folders) != expected_order:
            raise DriveLedgerError("type_folders must contain every Type in canonical order")
        if any(not folder_id for _, folder_id in self.type_folders):
            raise DriveLedgerError("Type folder IDs must be non-empty")
        folder_ids = tuple(folder_id for _, folder_id in self.type_folders)
        if len(set(folder_ids)) != len(folder_ids):
            raise DriveLedgerError("Type folder IDs must be distinct")
        if self.root_folder_id in folder_ids:
            raise DriveLedgerError("root and Type folder IDs must be distinct")
        if self.ownership_mode is OwnershipMode.SHARED_DRIVE_SERVICE_ACCOUNT:
            if not self.shared_drive_id:
                raise DriveLedgerError("shared-drive mode requires shared_drive_id")
        elif self.shared_drive_id is not None:
            raise DriveLedgerError("delegated-user mode cannot claim a shared_drive_id")

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> DriveLedgerConfig:
        """Parse environment-shaped config without reading process globals."""
        try:
            mode = OwnershipMode(values["STOIC_DRIVE_OWNERSHIP_MODE"])
            root = values["STOIC_DRIVE_ROOT_FOLDER_ID"]
            folders = tuple(
                (
                    signal_type,
                    values[f"STOIC_DRIVE_{signal_type.name}_FOLDER_ID"],
                )
                for signal_type in sorted(SignalType, key=lambda item: item.value)
            )
        except (KeyError, ValueError) as exc:
            raise DriveLedgerError("Drive ownership and all four folder IDs are required") from exc
        shared_drive_id = values.get("STOIC_DRIVE_SHARED_DRIVE_ID")
        return cls(mode, root, folders, shared_drive_id)

    @classmethod
    def from_environment(cls) -> DriveLedgerConfig:
        return cls.from_mapping(os.environ)

    def folder_for(self, signal_type: SignalType) -> str:
        for candidate, folder_id in self.type_folders:
            if candidate is signal_type:
                return folder_id
        raise DriveLedgerError("missing configured Type folder")  # pragma: no cover


@dataclass(frozen=True, slots=True)
class DriveReadiness:
    """Secret-free capability result for the configured Drive boundary."""

    ready: bool
    principal: str | None
    blockers: tuple[str, ...]


class DriveTransport(Protocol):
    """Owned wrapper around the third-party REST API."""

    def about(self) -> Mapping[str, object]: ...

    def generate_file_id(self) -> str: ...

    def create_file(
        self,
        *,
        file_id: str,
        name: str,
        parent_id: str,
        app_properties: Mapping[str, str],
        payload: bytes,
    ) -> Mapping[str, object]: ...

    def get_file(self, file_id: str) -> Mapping[str, object]: ...

    def download_file(self, file_id: str, *, max_bytes: int) -> bytes: ...

    def list_children(
        self,
        parent_id: str,
        *,
        shared_drive_id: str | None,
        page_token: str | None,
    ) -> tuple[tuple[Mapping[str, object], ...], str | None]: ...


class GoogleDriveTransport:
    """Minimal Drive v3 REST client authenticated through ADC."""

    def __init__(self, session: object) -> None:
        self._session = session

    @classmethod
    def from_adc(cls) -> GoogleDriveTransport:
        """Create an authorized session without accepting credential files in APIs."""
        try:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession
        except ImportError as exc:  # pragma: no cover - packaging verification covers install
            raise DriveLedgerError("google-auth is required for Drive ADC") from exc
        credentials, _ = google.auth.default(scopes=[DRIVE_SCOPE])
        return cls(AuthorizedSession(credentials))  # type: ignore[no-untyped-call]

    def about(self) -> Mapping[str, object]:
        response = self._request(
            "GET",
            f"{DRIVE_API}/about",
            params={"fields": "user(emailAddress,permissionId,displayName)"},
        )
        return self._json_object(response)

    def generate_file_id(self) -> str:
        response = self._request(
            "GET",
            f"{DRIVE_API}/files/generateIds",
            params={"count": "1", "space": "drive", "type": "files"},
        )
        payload = self._json_object(response)
        ids = payload.get("ids")
        if not isinstance(ids, list) or len(ids) != 1 or not isinstance(ids[0], str):
            raise DriveLedgerError("Drive generateIds returned an invalid response")
        return ids[0]

    def create_file(
        self,
        *,
        file_id: str,
        name: str,
        parent_id: str,
        app_properties: Mapping[str, str],
        payload: bytes,
    ) -> Mapping[str, object]:
        metadata = json.dumps(
            {
                "appProperties": dict(sorted(app_properties.items())),
                "id": file_id,
                "mimeType": EVENT_MIME_TYPE,
                "name": name,
                "parents": [parent_id],
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        boundary = f"stoic_{sha256(payload).hexdigest()}"
        while boundary.encode("ascii") in payload:
            boundary = f"{boundary}_x"
        body = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
            + metadata
            + f"\r\n--{boundary}\r\nContent-Type: {EVENT_MIME_TYPE}\r\n\r\n".encode()
            + payload
            + f"\r\n--{boundary}--\r\n".encode()
        )
        response = self._request(
            "POST",
            f"{DRIVE_UPLOAD_API}/files",
            params={
                "fields": (
                    "id,name,mimeType,parents,driveId,appProperties,size,md5Checksum,"
                    "capabilities(canDownload),trashed"
                ),
                "supportsAllDrives": "true",
                "uploadType": "multipart",
            },
            data=body,
            headers={"Content-Type": f'multipart/related; boundary="{boundary}"'},
        )
        return self._json_object(response)

    def get_file(self, file_id: str) -> Mapping[str, object]:
        response = self._request(
            "GET",
            f"{DRIVE_API}/files/{file_id}",
            params={
                "fields": (
                    "id,name,mimeType,parents,driveId,appProperties,size,md5Checksum,"
                    "capabilities(canAddChildren,canDownload),trashed"
                ),
                "supportsAllDrives": "true",
            },
        )
        return self._json_object(response)

    def download_file(self, file_id: str, *, max_bytes: int) -> bytes:
        response = self._request(
            "GET",
            f"{DRIVE_API}/files/{file_id}",
            params={"alt": "media", "supportsAllDrives": "true"},
            stream=True,
        )
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise DriveLedgerError("Drive download exceeds max_download_bytes")
            chunks.append(bytes(chunk))
        return b"".join(chunks)

    def list_children(
        self,
        parent_id: str,
        *,
        shared_drive_id: str | None,
        page_token: str | None,
    ) -> tuple[tuple[Mapping[str, object], ...], str | None]:
        params = {
            "fields": (
                "nextPageToken,files(id,name,mimeType,parents,driveId,appProperties,"
                "size,md5Checksum,capabilities(canDownload),trashed)"
            ),
            "includeItemsFromAllDrives": "true",
            "pageSize": "1000",
            "q": f"'{parent_id}' in parents and trashed = false",
            "spaces": "drive",
            "supportsAllDrives": "true",
        }
        if shared_drive_id is not None:
            params["corpora"] = "drive"
            params["driveId"] = shared_drive_id
        if page_token is not None:
            params["pageToken"] = page_token
        response = self._request("GET", f"{DRIVE_API}/files", params=params)
        payload = self._json_object(response)
        files = payload.get("files")
        if not isinstance(files, list) or any(not isinstance(item, dict) for item in files):
            raise DriveLedgerError("Drive files.list returned invalid files")
        next_token = payload.get("nextPageToken")
        if next_token is not None and not isinstance(next_token, str):
            raise DriveLedgerError("Drive files.list returned invalid nextPageToken")
        return tuple(cast(Mapping[str, object], item) for item in files), next_token

    def _request(self, method: str, url: str, **kwargs: object) -> Any:
        request = getattr(self._session, "request", None)
        if request is None:
            raise DriveLedgerError("authorized Drive session has no request method")
        try:
            response = request(method, url, timeout=30, **kwargs)
        except Exception as exc:
            raise DriveHTTPError(0, exc.__class__.__name__) from exc
        status = getattr(response, "status_code", None)
        if not isinstance(status, int):
            raise DriveLedgerError("Drive response has no status code")
        if status < 200 or status >= 300:
            detail = "request failed"
            try:
                body = response.json()
                error = body.get("error") if isinstance(body, dict) else None
                if isinstance(error, dict) and isinstance(error.get("message"), str):
                    detail = str(error["message"])[:200]
            except TypeError, ValueError:
                pass
            raise DriveHTTPError(status, detail)
        return response

    @staticmethod
    def _json_object(response: object) -> Mapping[str, object]:
        try:
            payload = response.json()  # type: ignore[attr-defined]
        except (AttributeError, TypeError, ValueError) as exc:
            raise DriveLedgerError("Drive returned invalid JSON") from exc
        if not isinstance(payload, dict) or any(not isinstance(key, str) for key in payload):
            raise DriveLedgerError("Drive JSON response must be an object")
        return cast(Mapping[str, object], payload)


class DriveLedgerStore:
    """Verified immutable publication and reconciliation source."""

    def __init__(
        self,
        transport: DriveTransport,
        config: DriveLedgerConfig,
        *,
        limits: LedgerLimits | None = None,
        sleep: Callable[[float], None] = time.sleep,
        retry_delays: tuple[float, ...] = (0.0, 1.0, 2.0, 4.0, 8.0),
    ) -> None:
        self._transport = transport
        self._config = config
        self._limits = limits or LedgerLimits()
        self._sleep = sleep
        if not retry_delays or any(delay < 0 for delay in retry_delays):
            raise DriveLedgerError("retry_delays must be non-empty and non-negative")
        self._retry_delays = retry_delays

    @property
    def config(self) -> DriveLedgerConfig:
        return self._config

    def readiness(self) -> DriveReadiness:
        """Verify principal, ownership boundary, and four append destinations."""
        blockers: list[str] = []
        principal: str | None = None
        try:
            about = self._transport.about()
            user = about.get("user")
            if isinstance(user, Mapping) and isinstance(user.get("emailAddress"), str):
                principal = str(user["emailAddress"])
                is_service_account = principal.endswith(".gserviceaccount.com")
                if (
                    self._config.ownership_mode is OwnershipMode.SHARED_DRIVE_SERVICE_ACCOUNT
                    and not is_service_account
                ):
                    blockers.append(
                        "shared-drive mode requires an authenticated service-account principal"
                    )
                if (
                    self._config.ownership_mode is OwnershipMode.DELEGATED_USER
                    and is_service_account
                ):
                    blockers.append(
                        "delegated-user mode requires an authenticated delegated-user principal"
                    )
            else:
                blockers.append("Drive about response has no authenticated principal")
            root = self._transport.get_file(self._config.root_folder_id)
            blockers.extend(self._folder_blockers(root, is_root=True))
            for signal_type, folder_id in self._config.type_folders:
                metadata = self._transport.get_file(folder_id)
                blockers.extend(
                    self._folder_blockers(
                        metadata,
                        is_root=False,
                        expected_parent=self._config.root_folder_id,
                        label=signal_type.value,
                    )
                )
        except DriveLedgerError as exc:
            blockers.append(str(exc))
        return DriveReadiness(not blockers, principal, tuple(sorted(set(blockers))))

    def publish_pending(
        self,
        outbox: LedgerOutbox,
        *,
        limit: int | None = None,
    ) -> tuple[str, ...]:
        """Publish committed deliveries and acknowledge only exact remote bytes."""
        readiness = self.readiness()
        if not readiness.ready:
            raise DriveLedgerError(
                f"Drive ledger configuration is blocked: {'; '.join(readiness.blockers)}"
            )
        self.verify_acknowledged(outbox)
        published: list[str] = []
        for delivery in outbox.pending(limit=limit):
            self._publish_one(outbox, delivery)
            published.append(delivery.event_id)
        return tuple(published)

    def read_events(self) -> tuple[LedgerEvent, ...]:
        """Read, verify, and deduplicate the complete bounded Drive event set."""
        readiness = self.readiness()
        if not readiness.ready:
            raise DriveLedgerError(
                f"Drive ledger configuration is blocked: {'; '.join(readiness.blockers)}"
            )
        by_id: dict[str, LedgerEvent] = {}
        object_count = 0
        for signal_type, folder_id in self._config.type_folders:
            page_token: str | None = None
            pages = 0
            while True:
                pages += 1
                if pages > self._limits.max_drive_pages:
                    raise DriveLedgerError("Drive listing exceeds max_drive_pages")
                files, page_token = self._transport.list_children(
                    folder_id,
                    shared_drive_id=self._config.shared_drive_id,
                    page_token=page_token,
                )
                object_count += len(files)
                if object_count > self._limits.max_events_per_reconcile:
                    raise DriveLedgerError("Drive objects exceed max_events_per_reconcile")
                for metadata in files:
                    event = self._event_from_remote(metadata, folder_id)
                    if event.signal_type is not signal_type:
                        raise DriveLedgerError("Drive event is placed in the wrong Type folder")
                    existing = by_id.setdefault(event.event_id, event)
                    if existing.canonical_bytes() != event.canonical_bytes():
                        raise DriveLedgerError("duplicate event ID has different Drive bytes")
                if page_token is None:
                    break
        return tuple(by_id[event_id] for event_id in sorted(by_id))

    def verify_acknowledged(self, outbox: LedgerOutbox) -> tuple[str, ...]:
        """Prove every local delivery acknowledgement still matches Drive authority."""
        verified: list[str] = []
        for delivery in outbox.acknowledged():
            event = decode_event(delivery.payload, limits=self._limits)
            if event.event_id != delivery.event_id:
                raise DriveLedgerError("acknowledged outbox event ID mismatch")
            if event.signal_type.value != delivery.signal_type:
                raise DriveLedgerError("acknowledged outbox Type mismatch")
            if event.source_partition != delivery.source_partition:
                raise DriveLedgerError("acknowledged outbox source partition mismatch")
            self._verify_remote(
                delivery.remote_file_id,
                self._config.folder_for(event.signal_type),
                self._event_name(event),
                self._event_properties(event),
                delivery.payload,
            )
            verified.append(event.event_id)
        return tuple(verified)

    def _publish_one(self, outbox: LedgerOutbox, delivery: PendingDelivery) -> None:
        event = decode_event(delivery.payload, limits=self._limits)
        if event.event_id != delivery.event_id:
            raise DriveLedgerError("outbox event ID does not match canonical bytes")
        folder_id = self._config.folder_for(event.signal_type)
        remote_file_id = delivery.remote_file_id
        if remote_file_id is None:
            remote_file_id = self._transport.generate_file_id()
            remote_file_id = outbox.reserve_remote_file_id(event.event_id, remote_file_id)
        expected_name = self._event_name(event)
        properties = self._event_properties(event)

        last_error: DriveLedgerError | None = None
        for delay in self._retry_delays:
            if delay:
                self._sleep(delay)
            try:
                outbox.record_attempt(event.event_id, error=None)
                self._transport.create_file(
                    file_id=remote_file_id,
                    name=expected_name,
                    parent_id=folder_id,
                    app_properties=properties,
                    payload=delivery.payload,
                )
                self._verify_remote(
                    remote_file_id,
                    folder_id,
                    expected_name,
                    properties,
                    delivery.payload,
                )
                outbox.mark_delivered(event.event_id)
                return
            except DriveHTTPError as exc:
                if exc.status == 409:
                    self._verify_remote(
                        remote_file_id,
                        folder_id,
                        expected_name,
                        properties,
                        delivery.payload,
                    )
                    outbox.mark_delivered(event.event_id)
                    return
                last_error = exc
                outbox.record_error(event.event_id, error=str(exc))
                if not _transient_status(exc.status):
                    raise
            except DriveLedgerError as exc:
                last_error = exc
                raise
        assert last_error is not None
        raise last_error

    def _event_from_remote(
        self,
        metadata: Mapping[str, object],
        folder_id: str,
    ) -> LedgerEvent:
        file_id = _metadata_string(metadata, "id")
        payload = self._transport.download_file(file_id, max_bytes=self._limits.max_download_bytes)
        event = decode_event(payload, limits=self._limits)
        self._verify_metadata(
            metadata,
            file_id,
            folder_id,
            self._event_name(event),
            self._event_properties(event),
            payload,
        )
        return event

    def _verify_remote(
        self,
        remote_file_id: str,
        folder_id: str,
        expected_name: str,
        properties: Mapping[str, str],
        payload: bytes,
    ) -> None:
        metadata = self._transport.get_file(remote_file_id)
        self._verify_metadata(
            metadata,
            remote_file_id,
            folder_id,
            expected_name,
            properties,
            payload,
        )
        remote_payload = self._transport.download_file(
            remote_file_id, max_bytes=self._limits.max_download_bytes
        )
        if remote_payload != payload:
            raise DriveLedgerError("Drive event bytes differ from committed outbox bytes")

    def _verify_metadata(
        self,
        metadata: Mapping[str, object],
        expected_file_id: str,
        folder_id: str,
        expected_name: str,
        properties: Mapping[str, str],
        payload: bytes,
    ) -> None:
        if _metadata_string(metadata, "id") != expected_file_id:
            raise DriveLedgerError("Drive event file ID mismatch")
        if metadata.get("trashed") is not False:
            raise DriveLedgerError("Drive event is trashed or trash state is unknown")
        if _metadata_string(metadata, "name") != expected_name:
            raise DriveLedgerError("Drive event name mismatch")
        if _metadata_string(metadata, "mimeType") != EVENT_MIME_TYPE:
            raise DriveLedgerError("Drive event MIME type mismatch")
        parents = metadata.get("parents")
        if not isinstance(parents, list) or parents != [folder_id]:
            raise DriveLedgerError("Drive event parent mismatch")
        remote_properties = metadata.get("appProperties")
        if not isinstance(remote_properties, Mapping) or any(
            remote_properties.get(key) != value for key, value in properties.items()
        ):
            raise DriveLedgerError("Drive event appProperties mismatch")
        size = metadata.get("size")
        if isinstance(size, bool) or not isinstance(size, (int, str)):
            raise DriveLedgerError("Drive event size is invalid")
        try:
            parsed_size = int(size)
        except ValueError as exc:
            raise DriveLedgerError("Drive event size is invalid") from exc
        if parsed_size != len(payload):
            raise DriveLedgerError("Drive event size mismatch")

    def _folder_blockers(
        self,
        metadata: Mapping[str, object],
        *,
        is_root: bool,
        expected_parent: str | None = None,
        label: str = "root",
    ) -> list[str]:
        blockers: list[str] = []
        if metadata.get("trashed") is not False:
            blockers.append(f"{label} folder is trashed or trash state is unknown")
        if metadata.get("mimeType") != FOLDER_MIME_TYPE:
            blockers.append(f"{label} ID is not a Drive folder")
        capabilities = metadata.get("capabilities")
        if not isinstance(capabilities, Mapping) or capabilities.get("canAddChildren") is not True:
            blockers.append(f"{label} folder does not permit immutable child creation")
        if expected_parent is not None:
            parents = metadata.get("parents")
            if not isinstance(parents, list) or expected_parent not in parents:
                blockers.append(f"{label} folder is not under the configured root")
        drive_id = metadata.get("driveId")
        if self._config.ownership_mode is OwnershipMode.SHARED_DRIVE_SERVICE_ACCOUNT:
            if drive_id != self._config.shared_drive_id:
                blockers.append(f"{label} folder is not in the configured shared drive")
        elif drive_id is not None:
            blockers.append(f"{label} delegated-user folder must be ordinary My Drive")
        if is_root and expected_parent is not None:  # pragma: no cover - call contract guard
            blockers.append("root folder cannot have an expected ledger parent")
        return blockers

    @staticmethod
    def _event_name(event: LedgerEvent) -> str:
        return f"{event.source_partition}--{event.event_id}.json"

    @staticmethod
    def _event_properties(event: LedgerEvent) -> dict[str, str]:
        return {
            "event_id": event.event_id,
            "ledger_schema": SCHEMA_VERSION,
            "payload_sha256": sha256(event.canonical_bytes()).hexdigest(),
            "signal_id": event.signal_id,
            "signal_type": event.signal_type.value,
            "source_partition": event.source_partition,
        }


def _metadata_string(metadata: Mapping[str, object], key: str) -> str:
    value = metadata.get(key)
    if not isinstance(value, str) or not value:
        raise DriveLedgerError(f"Drive metadata {key} is invalid")
    return value


def _transient_status(status: int) -> bool:
    return status in {0, 403, 429, 500, 502, 503, 504}


__all__ = [
    "DRIVE_SCOPE",
    "DriveHTTPError",
    "DriveLedgerConfig",
    "DriveLedgerError",
    "DriveLedgerStore",
    "DriveReadiness",
    "DriveTransport",
    "GoogleDriveTransport",
    "OwnershipMode",
]
