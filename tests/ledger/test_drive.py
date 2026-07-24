from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256

import pytest

from stoic_derived.ledger.drive import (
    EVENT_MIME_TYPE,
    FOLDER_MIME_TYPE,
    DriveHTTPError,
    DriveLedgerConfig,
    DriveLedgerError,
    DriveLedgerStore,
    OwnershipMode,
)
from stoic_derived.ledger.model import SCHEMA_VERSION, LedgerEvent
from stoic_derived.ledger.outbox import LedgerOutbox
from stoic_derived.signal_engine.model import SignalType


class FakeDriveTransport:
    def __init__(self, config: DriveLedgerConfig) -> None:
        self.config = config
        self.principal = (
            "ledger@project.iam.gserviceaccount.com"
            if config.ownership_mode is OwnershipMode.SHARED_DRIVE_SERVICE_ACCOUNT
            else "ledger@example.com"
        )
        self.files: dict[str, tuple[dict[str, object], bytes]] = {}
        self.generated = 0
        self.fail_after_create_once = False
        self.create_calls = 0
        drive_id = config.shared_drive_id
        self.folders: dict[str, dict[str, object]] = {
            config.root_folder_id: self._folder(config.root_folder_id, [], drive_id)
        }
        for _, folder_id in config.type_folders:
            self.folders[folder_id] = self._folder(folder_id, [config.root_folder_id], drive_id)

    def about(self) -> Mapping[str, object]:
        return {"user": {"emailAddress": self.principal, "permissionId": "p1"}}

    def generate_file_id(self) -> str:
        self.generated += 1
        return f"generated-{self.generated}"

    def create_file(
        self,
        *,
        file_id: str,
        name: str,
        parent_id: str,
        app_properties: Mapping[str, str],
        payload: bytes,
    ) -> Mapping[str, object]:
        self.create_calls += 1
        if file_id in self.files:
            raise DriveHTTPError(409, "already exists")
        metadata: dict[str, object] = {
            "appProperties": dict(app_properties),
            "capabilities": {"canDownload": True},
            "driveId": self.config.shared_drive_id,
            "id": file_id,
            "mimeType": EVENT_MIME_TYPE,
            "name": name,
            "parents": [parent_id],
            "size": str(len(payload)),
            "trashed": False,
        }
        if self.config.shared_drive_id is None:
            metadata.pop("driveId")
        self.files[file_id] = (metadata, payload)
        if self.fail_after_create_once:
            self.fail_after_create_once = False
            raise DriveHTTPError(0, "connection lost")
        return metadata

    def get_file(self, file_id: str) -> Mapping[str, object]:
        if file_id in self.folders:
            return self.folders[file_id]
        if file_id in self.files:
            return self.files[file_id][0]
        raise DriveHTTPError(404, "not found")

    def download_file(self, file_id: str, *, max_bytes: int) -> bytes:
        payload = self.files[file_id][1]
        if len(payload) > max_bytes:
            raise DriveLedgerError("too large")
        return payload

    def list_children(
        self,
        parent_id: str,
        *,
        shared_drive_id: str | None,
        page_token: str | None,
    ) -> tuple[tuple[Mapping[str, object], ...], str | None]:
        assert shared_drive_id == self.config.shared_drive_id
        assert page_token is None
        children = tuple(
            metadata for metadata, _ in self.files.values() if metadata["parents"] == [parent_id]
        )
        return children, None

    @staticmethod
    def _folder(
        folder_id: str,
        parents: list[str],
        drive_id: str | None,
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "capabilities": {"canAddChildren": True},
            "driveId": drive_id,
            "id": folder_id,
            "mimeType": FOLDER_MIME_TYPE,
            "name": folder_id,
            "parents": parents,
            "trashed": False,
        }
        if drive_id is None:
            value.pop("driveId")
        return value


def _config(
    mode: OwnershipMode = OwnershipMode.SHARED_DRIVE_SERVICE_ACCOUNT,
) -> DriveLedgerConfig:
    shared_drive_id = (
        "shared-drive-1" if mode is OwnershipMode.SHARED_DRIVE_SERVICE_ACCOUNT else None
    )
    return DriveLedgerConfig(
        ownership_mode=mode,
        root_folder_id="ledger-root",
        type_folders=tuple(
            (signal_type, f"folder-{signal_type.name.lower()}")
            for signal_type in sorted(SignalType, key=lambda item: item.value)
        ),
        shared_drive_id=shared_drive_id,
    )


def _metadata_for_event(
    store: DriveLedgerStore,
    event: LedgerEvent,
    *,
    file_id: str,
) -> dict[str, object]:
    return {
        "appProperties": {
            "event_id": event.event_id,
            "ledger_schema": SCHEMA_VERSION,
            "payload_sha256": sha256(event.canonical_bytes()).hexdigest(),
            "signal_id": event.signal_id,
            "signal_type": event.signal_type.value,
            "source_partition": event.source_partition,
        },
        "capabilities": {"canDownload": True},
        "driveId": store.config.shared_drive_id,
        "id": file_id,
        "mimeType": EVENT_MIME_TYPE,
        "name": f"{event.source_partition}--{event.event_id}.json",
        "parents": [store.config.folder_for(event.signal_type)],
        "size": str(len(event.canonical_bytes())),
        "trashed": False,
    }


def test_configuration_requires_exactly_four_distinct_type_folders() -> None:
    with pytest.raises(DriveLedgerError, match="every Type"):
        DriveLedgerConfig(
            OwnershipMode.DELEGATED_USER,
            "root",
            ((SignalType.SCALP, "scalp"),),
        )


def test_readiness_verifies_shared_drive_ownership_and_capabilities() -> None:
    config = _config()
    transport = FakeDriveTransport(config)
    store = DriveLedgerStore(transport, config)

    ready = store.readiness()
    transport.folders[config.folder_for(SignalType.DAY)]["driveId"] = "wrong-drive"
    blocked = store.readiness()

    assert ready.ready is True
    assert ready.principal == "ledger@project.iam.gserviceaccount.com"
    assert blocked.ready is False
    assert "shared drive" in blocked.blockers[0]


def test_shared_drive_mode_requires_service_account_principal() -> None:
    config = _config()
    transport = FakeDriveTransport(config)
    transport.principal = "ledger@example.com"

    readiness = DriveLedgerStore(transport, config).readiness()

    assert readiness.ready is False
    assert "service-account principal" in readiness.blockers[0]


def test_delegated_user_mode_accepts_owned_my_drive_folders() -> None:
    config = _config(OwnershipMode.DELEGATED_USER)

    readiness = DriveLedgerStore(FakeDriveTransport(config), config).readiness()

    assert readiness.ready is True


def test_delegated_user_mode_rejects_service_account_principal() -> None:
    config = _config(OwnershipMode.DELEGATED_USER)
    transport = FakeDriveTransport(config)
    transport.principal = "ledger@project.iam.gserviceaccount.com"

    readiness = DriveLedgerStore(transport, config).readiness()

    assert readiness.ready is False
    assert "delegated-user principal" in readiness.blockers[0]


def test_timeout_after_success_retries_same_id_and_verifies_409(tmp_path, make_signal) -> None:
    config = _config()
    transport = FakeDriveTransport(config)
    transport.fail_after_create_once = True
    store = DriveLedgerStore(transport, config, sleep=lambda _: None, retry_delays=(0, 0))
    outbox = LedgerOutbox(tmp_path / "ledger.sqlite3")
    event = LedgerEvent.for_signal(make_signal(), source="writer")
    outbox.enqueue((event,))

    published = store.publish_pending(outbox)

    assert published == (event.event_id,)
    assert transport.create_calls == 2
    assert not outbox.pending()
    assert len(transport.files) == 1


def test_409_with_different_remote_bytes_fails_closed(tmp_path, make_signal) -> None:
    config = _config()
    transport = FakeDriveTransport(config)
    store = DriveLedgerStore(transport, config, sleep=lambda _: None, retry_delays=(0,))
    outbox = LedgerOutbox(tmp_path / "ledger.sqlite3")
    event = LedgerEvent.for_signal(make_signal(), source="writer")
    outbox.enqueue((event,))
    outbox.reserve_remote_file_id(event.event_id, "generated-1")
    metadata = _metadata_for_event(store, event, file_id="generated-1")
    metadata["size"] = "2"
    transport.files["generated-1"] = (metadata, b"{}")

    with pytest.raises(DriveLedgerError, match="size mismatch"):
        store.publish_pending(outbox)


def test_409_verification_requires_exact_pre_generated_file_id(tmp_path, make_signal) -> None:
    config = _config()
    transport = FakeDriveTransport(config)
    store = DriveLedgerStore(transport, config, sleep=lambda _: None, retry_delays=(0,))
    outbox = LedgerOutbox(tmp_path / "ledger.sqlite3")
    event = LedgerEvent.for_signal(make_signal(), source="writer")
    outbox.enqueue((event,))
    outbox.reserve_remote_file_id(event.event_id, "generated-1")
    metadata = _metadata_for_event(store, event, file_id="different-id")
    transport.files["generated-1"] = (metadata, event.canonical_bytes())

    with pytest.raises(DriveLedgerError, match="file ID mismatch"):
        store.publish_pending(outbox)


def test_duplicate_physical_objects_reconcile_to_one_event(make_signal) -> None:
    config = _config()
    transport = FakeDriveTransport(config)
    store = DriveLedgerStore(transport, config)
    event = LedgerEvent.for_signal(make_signal(), source="writer")
    first = _metadata_for_event(store, event, file_id="physical-1")
    second = _metadata_for_event(store, event, file_id="physical-2")
    transport.files["physical-1"] = (first, event.canonical_bytes())
    transport.files["physical-2"] = (second, event.canonical_bytes())

    events = store.read_events()

    assert events == (event,)


def test_missing_acknowledged_drive_object_is_not_masked_by_local_cache(
    tmp_path, make_signal
) -> None:
    config = _config()
    transport = FakeDriveTransport(config)
    store = DriveLedgerStore(transport, config, sleep=lambda _: None, retry_delays=(0,))
    outbox = LedgerOutbox(tmp_path / "ledger.sqlite3")
    event = LedgerEvent.for_signal(make_signal(), source="writer")
    outbox.enqueue((event,))
    store.publish_pending(outbox)
    transport.files.clear()

    with pytest.raises(DriveHTTPError, match="404"):
        store.verify_acknowledged(outbox)


def test_cross_type_remote_placement_fails_closed(make_signal) -> None:
    config = _config()
    transport = FakeDriveTransport(config)
    store = DriveLedgerStore(transport, config)
    event = LedgerEvent.for_signal(make_signal(), source="writer")
    metadata = _metadata_for_event(store, event, file_id="physical-1")
    metadata["parents"] = [config.folder_for(SignalType.DAY)]
    transport.files["physical-1"] = (metadata, event.canonical_bytes())

    with pytest.raises(DriveLedgerError, match="wrong Type folder"):
        store.read_events()
