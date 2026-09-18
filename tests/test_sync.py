from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mi_nube.database.sqlite import SqliteDatabase
from mi_nube.domain.models import DeltaChange, DeltaResult
from mi_nube.repositories.sync_repository import SqliteSyncRepository
from mi_nube.services.sync_service import SyncService


class EmptyProjectRepository:
    def list_projects(self):
        return ()


class SequenceDeltaClient:
    def __init__(self, results: list[DeltaResult]) -> None:
        self.results = results
        self.calls: list[tuple[bool, str | None]] = []

    def delta(self, item_id=None, *, delta_link=None, latest=False):
        self.calls.append((latest, delta_link))
        return self.results.pop(0)


def test_sync_creates_baseline_then_reconciles_local_activity(tmp_path: Path) -> None:
    moment = datetime(2026, 9, 17, 20, 0, tzinfo=UTC)
    client = SequenceDeltaClient(
        [
            DeltaResult((), "https://graph.microsoft.com/v1.0/delta?token=one"),
            DeltaResult(
                (
                    DeltaChange(
                        item_id="file-1",
                        name="Plano.dwg",
                        parent_item_id="root",
                        is_folder=False,
                        is_deleted=False,
                        etag='"v1"',
                        created_at=moment,
                        modified_at=moment,
                        modified_by="Efraín",
                    ),
                ),
                "https://graph.microsoft.com/v1.0/delta?token=two",
            ),
        ]
    )
    repository = SqliteSyncRepository(SqliteDatabase(tmp_path / "app.db"))
    service = SyncService(client, repository, EmptyProjectRepository(), lambda: "Efraín")

    baseline = service.sync_all()
    service.record_local("subió", "Plano.dwg")
    changed = service.sync_all()

    events = service.list_activity()
    assert baseline.baselines_created == 1
    assert changed.changes_received == 1
    assert changed.events_created == 0
    assert len(events) == 1
    assert events[0].source == "local+graph"
    assert events[0].remote_item_id == "file-1"
    assert client.calls[0] == (True, None)
    assert client.calls[1][0] is False
    assert client.calls[1][1] and "token=one" in client.calls[1][1]


def test_sync_classifies_rename_from_previous_snapshot(tmp_path: Path) -> None:
    repository = SqliteSyncRepository(SqliteDatabase(tmp_path / "app.db"))
    moment = datetime.now(UTC)
    client = SequenceDeltaClient(
        [
            DeltaResult((), "https://graph.microsoft.com/delta?token=base"),
            DeltaResult(
                (
                    DeltaChange(
                        "file",
                        "Antes.txt",
                        "root",
                        False,
                        False,
                        '"1"',
                        moment,
                        moment,
                        "Efraín",
                    ),
                ),
                "https://graph.microsoft.com/delta?token=first",
            ),
            DeltaResult(
                (
                    DeltaChange(
                        "file",
                        "Después.txt",
                        "root",
                        False,
                        False,
                        '"2"',
                        moment,
                        moment,
                        "Efraín",
                    ),
                ),
                "https://graph.microsoft.com/delta?token=second",
            ),
        ]
    )
    service = SyncService(client, repository, EmptyProjectRepository(), lambda: "Efraín")
    service.sync_all()
    service.sync_all()
    service.sync_all()

    events = service.list_activity()
    renamed = next(event for event in events if event.action == "renombró")
    assert renamed.target == "Después.txt"
