from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from mi_nube.domain.models import (
    ActivityEvent,
    DeltaChange,
    SyncedItem,
    SyncScope,
    SyncSummary,
)
from mi_nube.graph.errors import GraphDeltaResetRequired
from mi_nube.graph.ports import GraphDriveClient
from mi_nube.repositories.ports import ProjectRepository
from mi_nube.repositories.sync_repository import SqliteSyncRepository


class SyncService:
    PERSONAL_SCOPE_ID = "drive:personal"

    def __init__(
        self,
        client: GraphDriveClient,
        repository: SqliteSyncRepository,
        project_repository: ProjectRepository,
        actor_provider: Callable[[], str],
    ) -> None:
        self._client = client
        self._repository = repository
        self._project_repository = project_repository
        self._actor_provider = actor_provider

    def ensure_scopes(self) -> tuple[SyncScope, ...]:
        scopes: list[SyncScope] = []
        for project in self._project_repository.list_projects():
            scopes.append(
                self._repository.ensure_scope(
                    SyncScope(
                        scope_id=f"project:{project.project_id}",
                        scope_type="project",
                        remote_item_id=project.remote_item_id,
                        label=project.name,
                        delta_link=None,
                        initialized=False,
                        last_synced_at=None,
                    )
                )
            )
        scopes.append(
            self._repository.ensure_scope(
                SyncScope(
                    scope_id=self.PERSONAL_SCOPE_ID,
                    scope_type="drive",
                    remote_item_id=None,
                    label="Personal",
                    delta_link=None,
                    initialized=False,
                    last_synced_at=None,
                )
            )
        )
        return tuple(scopes)

    def list_scopes(self) -> tuple[SyncScope, ...]:
        self.ensure_scopes()
        return self._repository.list_scopes()

    def list_activity(
        self, scope_id: str | None = None, search: str = ""
    ) -> tuple[ActivityEvent, ...]:
        return self._repository.list_events(scope_id=scope_id, search=search)

    def record_local(
        self,
        action: str,
        target: str,
        *,
        scope_id: str = PERSONAL_SCOPE_ID,
        project_name: str | None = None,
        details: str | None = None,
    ) -> ActivityEvent:
        now = datetime.now(UTC)
        event = ActivityEvent(
            event_id=str(uuid4()),
            source="local",
            action=action,
            actor=self._actor_provider() or "Propietario",
            target=target,
            scope_id=scope_id,
            project_name=project_name,
            remote_item_id=None,
            occurred_at=now,
            details=details,
        )
        self._repository.save_event(event, f"local:{event.event_id}")
        return event

    def sync_all(self) -> SyncSummary:
        now = datetime.now(UTC)
        scopes = self.ensure_scopes()
        changes = events = baselines = 0
        for scope in scopes:
            received, created, baseline = self._sync_scope(scope, now)
            changes += received
            events += created
            baselines += int(baseline)
        return SyncSummary(len(scopes), changes, events, baselines, now)

    def _sync_scope(self, scope: SyncScope, now: datetime) -> tuple[int, int, bool]:
        if not scope.initialized or not scope.delta_link:
            result = self._client.delta(scope.remote_item_id, latest=True)
            self._repository.save_cursor(scope.scope_id, result.delta_link, now)
            return 0, 0, True
        try:
            result = self._client.delta(scope.remote_item_id, delta_link=scope.delta_link)
        except GraphDeltaResetRequired:
            self._repository.reset_scope(scope.scope_id)
            result = self._client.delta(scope.remote_item_id, latest=True)
            self._repository.save_cursor(scope.scope_id, result.delta_link, now)
            return 0, 0, True

        created = 0
        for change in result.changes:
            created += int(self._apply_change(scope, change, now))
        self._repository.save_cursor(scope.scope_id, result.delta_link, now)
        return len(result.changes), created, False

    def _apply_change(self, scope: SyncScope, change: DeltaChange, now: datetime) -> bool:
        previous = self._repository.get_item(scope.scope_id, change.item_id)
        name = change.name or (previous.name if previous else "Elemento eliminado")
        action = self._classify(change, previous)

        if change.is_deleted:
            self._repository.delete_item(scope.scope_id, change.item_id)
        else:
            self._repository.save_item(
                SyncedItem(
                    scope_id=scope.scope_id,
                    item_id=change.item_id,
                    name=name,
                    parent_item_id=change.parent_item_id,
                    is_folder=change.is_folder,
                    etag=change.etag,
                    modified_at=change.modified_at,
                    modified_by=change.modified_by,
                )
            )
        if action is None or change.item_id == scope.remote_item_id:
            return False
        if scope.scope_type == "drive" and (
            self._repository.is_project_item(change.item_id)
            or self._repository.is_project_item(change.parent_item_id)
        ):
            return False

        occurred_at = change.modified_at or now
        if self._repository.reconcile_local_event(
            scope_id=scope.scope_id,
            action=action,
            target=name,
            remote_item_id=change.item_id,
            since=now - timedelta(minutes=15),
        ):
            return False
        marker = "deleted" if change.is_deleted else change.etag or occurred_at.isoformat()
        event = ActivityEvent(
            event_id=str(uuid4()),
            source="graph",
            action=action,
            actor=change.modified_by,
            target=name,
            scope_id=scope.scope_id,
            project_name=scope.label if scope.scope_type == "project" else None,
            remote_item_id=change.item_id,
            occurred_at=occurred_at,
            details="Cambio detectado por sincronización incremental de OneDrive.",
        )
        key = f"graph:{scope.scope_id}:{change.item_id}:{action}:{marker}"
        return self._repository.save_event(event, key)

    @staticmethod
    def _classify(change: DeltaChange, previous: SyncedItem | None) -> str | None:
        if change.is_deleted:
            return "eliminó"
        if previous is None:
            if (
                change.created_at
                and change.modified_at
                and abs((change.modified_at - change.created_at).total_seconds()) <= 2
            ):
                return "creó" if change.is_folder else "subió"
            return "modificó"
        if change.name and change.name != previous.name:
            return "renombró"
        if change.parent_item_id != previous.parent_item_id:
            return "movió"
        if change.etag != previous.etag or change.modified_at != previous.modified_at:
            return "modificó"
        return None
