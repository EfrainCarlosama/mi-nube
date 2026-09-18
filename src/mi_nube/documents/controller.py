from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from mi_nube.documents.errors import DocumentError
from mi_nube.domain.models import DocumentStatus, DriveItem
from mi_nube.graph.errors import GraphError
from mi_nube.services.document_service import DocumentService

LOGGER = logging.getLogger(__name__)


class _Signals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()


class _Worker(QRunnable):
    def __init__(self, operation: Callable[[], Any]) -> None:
        super().__init__()
        self.operation = operation
        self.signals = _Signals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.succeeded.emit(self.operation())
        except (DocumentError, GraphError, OSError) as error:
            self.signals.failed.emit(str(error))
        except Exception:
            LOGGER.exception("Fallo inesperado administrando un documento")
            self.signals.failed.emit("Ocurrió un error inesperado al guardar el documento.")
        finally:
            self.signals.finished.emit()


class DocumentController(QObject):
    metadata_saved = Signal(object)
    project_loaded = Signal(object)
    history_loaded = Signal(object)
    report_exported = Signal(str)
    error_occurred = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, service: DocumentService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._pool = QThreadPool.globalInstance()
        self._workers: set[_Worker] = set()

    def get(self, item_id: str):
        return self._service.get(item_id)

    def list_project(self, project_id: str, status=None, search: str = ""):
        return self._service.list_project(project_id, status, search)

    def preview_name(
        self, original: str, discipline: str, number: str, revision: str, title: str
    ) -> str:
        return self._service.build_name(original, discipline, number, revision, title)

    def normalize_revision(self, revision: str) -> str:
        return self._service.normalize_revision(revision)

    def _run(self, operation: Callable[[], Any], signal: Signal) -> None:
        worker = _Worker(operation)
        self._workers.add(worker)
        worker.signals.succeeded.connect(signal.emit)
        worker.signals.failed.connect(self.error_occurred.emit)
        worker.signals.finished.connect(lambda: self._finish(worker))
        self.busy_changed.emit(True)
        self._pool.start(worker)

    def _finish(self, worker: _Worker) -> None:
        self._workers.discard(worker)
        self.busy_changed.emit(bool(self._workers))

    def save(
        self,
        project_id: str,
        item: DriveItem,
        *,
        status: DocumentStatus,
        revision: str,
        naming_enabled: bool,
        discipline_code: str,
        document_number: str,
        title: str,
        rename_remote: bool,
    ) -> None:
        self._run(
            lambda: self._service.save(
                project_id,
                item,
                status=status,
                revision=revision,
                naming_enabled=naming_enabled,
                discipline_code=discipline_code,
                document_number=document_number,
                title=title,
                rename_remote=rename_remote,
            ),
            self.metadata_saved,
        )

    def load_project(
        self, project_id: str, status: DocumentStatus | None = None, search: str = ""
    ) -> None:
        self.project_loaded.emit(self._service.list_project(project_id, status, search))

    def load_history(self, item_id: str) -> None:
        self.history_loaded.emit(self._service.list_history(item_id))

    def export_csv(self, project_id: str, destination: Path) -> None:
        self._run(
            lambda: self._service.export_csv(project_id, destination),
            self.report_exported,
        )
