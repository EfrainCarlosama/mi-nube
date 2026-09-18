from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from mi_nube.auth.errors import AuthenticationError
from mi_nube.domain.models import ProjectTemplate, TemplateFolder
from mi_nube.graph.errors import GraphError
from mi_nube.projects.errors import ProjectError
from mi_nube.services.project_service import ProjectService

LOGGER = logging.getLogger(__name__)


class _ProjectWorkerSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()


class _ProjectWorker(QRunnable):
    def __init__(self, operation: Callable[[], Any]) -> None:
        super().__init__()
        self._operation = operation
        self.signals = _ProjectWorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.succeeded.emit(self._operation())
        except (ProjectError, GraphError, AuthenticationError) as error:
            self.signals.failed.emit(str(error))
        except Exception:
            LOGGER.exception("Fallo inesperado en una operación de proyecto")
            self.signals.failed.emit("Ocurrió un error inesperado al procesar el proyecto.")
        finally:
            self.signals.finished.emit()


class ProjectController(QObject):
    projects_loaded = Signal(object)
    project_created = Signal(object)
    template_saved = Signal(object)
    progress_changed = Signal(int, int, str)
    error_occurred = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, service: ProjectService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._thread_pool = QThreadPool.globalInstance()
        self._workers: set[_ProjectWorker] = set()
        self._active_operations = 0

    def _run(self, operation: Callable[[], Any], on_success: Callable[[Any], None]) -> None:
        worker = _ProjectWorker(operation)
        self._workers.add(worker)
        worker.signals.succeeded.connect(on_success)
        worker.signals.failed.connect(self.error_occurred.emit)
        worker.signals.finished.connect(lambda: self._finish(worker))
        self._active_operations += 1
        self.busy_changed.emit(True)
        self._thread_pool.start(worker)

    def _finish(self, worker: _ProjectWorker) -> None:
        self._workers.discard(worker)
        self._active_operations = max(0, self._active_operations - 1)
        self.busy_changed.emit(self._active_operations > 0)

    def load_projects(self) -> None:
        self._run(self._service.list_projects, self.projects_loaded.emit)

    def create_project(self, name: str, client: str, use_template: bool = True) -> None:
        self._run(
            lambda: self._service.create_project(
                name,
                client,
                use_template,
                self.progress_changed.emit,
            ),
            self.project_created.emit,
        )

    def default_template(self) -> ProjectTemplate:
        return self._service.default_template()

    def save_default_template(self, folders: tuple[TemplateFolder, ...]) -> ProjectTemplate:
        template = self._service.save_default_template(folders)
        self.template_saved.emit(template)
        return template
