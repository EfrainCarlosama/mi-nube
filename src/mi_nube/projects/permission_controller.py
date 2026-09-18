from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from mi_nube.auth.errors import AuthenticationError
from mi_nube.domain.permissions import Capability, PermissionLevel, ProjectRole
from mi_nube.graph.errors import GraphError
from mi_nube.projects.errors import ProjectError
from mi_nube.services.permission_service import PermissionService

LOGGER = logging.getLogger(__name__)


class _PermissionWorkerSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()


class _PermissionWorker(QRunnable):
    def __init__(self, operation: Callable[[], Any]) -> None:
        super().__init__()
        self._operation = operation
        self.signals = _PermissionWorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.succeeded.emit(self._operation())
        except (ProjectError, GraphError, AuthenticationError) as error:
            self.signals.failed.emit(str(error))
        except Exception:
            LOGGER.exception("Fallo inesperado administrando permisos")
            self.signals.failed.emit("Ocurrió un error inesperado al administrar permisos.")
        finally:
            self.signals.finished.emit()


class PermissionController(QObject):
    team_loaded = Signal(object)
    member_added = Signal(object)
    member_removed = Signal(str)
    role_changed = Signal(object)
    editor_loaded = Signal(object)
    permissions_saved = Signal(object)
    history_loaded = Signal(object)
    progress_changed = Signal(int, int, str)
    error_occurred = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, service: PermissionService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._thread_pool = QThreadPool.globalInstance()
        self._workers: set[_PermissionWorker] = set()
        self._active_operations = 0

    def _run(self, operation: Callable[[], Any], on_success: Callable[[Any], None]) -> None:
        worker = _PermissionWorker(operation)
        self._workers.add(worker)
        worker.signals.succeeded.connect(on_success)
        worker.signals.failed.connect(self.error_occurred.emit)
        worker.signals.finished.connect(lambda: self._finish(worker))
        self._active_operations += 1
        self.busy_changed.emit(True)
        self._thread_pool.start(worker)

    def _finish(self, worker: _PermissionWorker) -> None:
        self._workers.discard(worker)
        self._active_operations = max(0, self._active_operations - 1)
        self.busy_changed.emit(self._active_operations > 0)

    def load_team(self, project_id: str) -> None:
        self._run(lambda: self._service.list_members(project_id), self.team_loaded.emit)

    def add_member(
        self,
        project_id: str,
        email: str,
        display_name: str,
        role: ProjectRole,
        actor_email: str,
    ) -> None:
        self._run(
            lambda: self._service.add_member(project_id, email, display_name, role, actor_email),
            self.member_added.emit,
        )

    def change_role(self, member_id: str, role: ProjectRole, actor_email: str) -> None:
        self._run(
            lambda: self._service.change_role(member_id, role, actor_email),
            self.role_changed.emit,
        )

    def remove_member(self, member_id: str, actor_email: str) -> None:
        self._run(
            lambda: self._remove_member(member_id, actor_email),
            self.member_removed.emit,
        )

    def _remove_member(self, member_id: str, actor_email: str) -> str:
        self._service.remove_member(member_id, actor_email)
        return member_id

    def load_editor(self, member_id: str) -> None:
        self._run(lambda: self._service.editor_data(member_id), self.editor_loaded.emit)

    def save_folder_permissions(
        self,
        member_id: str,
        updates: Sequence[tuple[str, PermissionLevel, Capability, bool]],
        actor_email: str,
    ) -> None:
        self._run(
            lambda: self._service.set_folder_permissions(
                member_id,
                updates,
                actor_email,
                self.progress_changed.emit,
            ),
            self.permissions_saved.emit,
        )

    def load_history(self, project_id: str) -> None:
        self._run(lambda: self._service.list_history(project_id), self.history_loaded.emit)
