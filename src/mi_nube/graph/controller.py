from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from mi_nube.auth.errors import AuthenticationError
from mi_nube.graph.errors import GraphError, GraphUploadCancelled
from mi_nube.graph.ports import GraphDriveClient

LOGGER = logging.getLogger(__name__)


class _DriveWorkerSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal(str)
    finished = Signal()


class _DriveWorker(QRunnable):
    def __init__(self, operation: Callable[[], Any]) -> None:
        super().__init__()
        self._operation = operation
        self.signals = _DriveWorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.succeeded.emit(self._operation())
        except GraphUploadCancelled as error:
            self.signals.cancelled.emit(str(error))
        except (GraphError, AuthenticationError) as error:
            self.signals.failed.emit(str(error))
        except Exception:
            LOGGER.exception("Fallo inesperado en una operación de OneDrive")
            self.signals.failed.emit("Ocurrió un error inesperado al comunicarse con OneDrive.")
        finally:
            self.signals.finished.emit()


class DriveController(QObject):
    browser_loaded = Signal(object, object)
    items_loaded = Signal(object)
    item_info_loaded = Signal(object)
    operation_succeeded = Signal(str)
    download_succeeded = Signal(str)
    error_occurred = Signal(str)
    busy_changed = Signal(bool)
    upload_started = Signal(str, int)
    upload_progress = Signal(int, int)
    upload_cancelled = Signal(str)
    upload_finished = Signal()

    def __init__(self, client: GraphDriveClient, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._client = client
        self._thread_pool = QThreadPool.globalInstance()
        self._workers: set[_DriveWorker] = set()
        self._active_operations = 0
        self._upload_cancel_event: threading.Event | None = None

    def _run(
        self,
        operation: Callable[[], Any],
        on_success: Callable[[Any], None],
        *,
        on_cancelled: Callable[[str], None] | None = None,
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        worker = _DriveWorker(operation)
        self._workers.add(worker)
        worker.signals.succeeded.connect(on_success)
        worker.signals.failed.connect(self.error_occurred.emit)
        worker.signals.cancelled.connect(on_cancelled or self.error_occurred.emit)
        if on_finished:
            worker.signals.finished.connect(on_finished)
        worker.signals.finished.connect(lambda: self._finish(worker))
        self._active_operations += 1
        self.busy_changed.emit(True)
        self._thread_pool.start(worker)

    def _finish(self, worker: _DriveWorker) -> None:
        self._workers.discard(worker)
        self._active_operations = max(0, self._active_operations - 1)
        self.busy_changed.emit(self._active_operations > 0)

    def refresh(self, parent_id: str | None) -> None:
        self._run(
            lambda: (tuple(self._client.list_children(parent_id)), self._client.get_quota()),
            lambda result: self.browser_loaded.emit(result[0], result[1]),
        )

    def search(self, query: str) -> None:
        self._run(lambda: tuple(self._client.search(query)), self.items_loaded.emit)

    def create_folder(self, parent_id: str | None, name: str) -> None:
        self._run(
            lambda: self._client.create_folder(parent_id, name),
            lambda _: self.operation_succeeded.emit("Carpeta creada correctamente."),
        )

    def upload(self, parent_id: str | None, source: Path) -> None:
        cancel_event = threading.Event()
        self._upload_cancel_event = cancel_event
        try:
            size = source.stat().st_size
        except OSError:
            size = 0
        self.upload_started.emit(source.name, size)
        self._run(
            lambda: self._client.upload_file(
                parent_id,
                source,
                self.upload_progress.emit,
                cancel_event.is_set,
            ),
            lambda _: self.operation_succeeded.emit("Archivo subido correctamente."),
            on_cancelled=self.upload_cancelled.emit,
            on_finished=self._finish_upload,
        )

    def cancel_upload(self) -> None:
        if self._upload_cancel_event is not None:
            self._upload_cancel_event.set()

    def _finish_upload(self) -> None:
        self._upload_cancel_event = None
        self.upload_finished.emit()

    def download(self, item_id: str, destination: Path) -> None:
        self._run(
            lambda: self._client.download_file(item_id, destination),
            lambda path: self.download_succeeded.emit(str(path)),
        )

    def rename(self, item_id: str, new_name: str, etag: str | None) -> None:
        self._run(
            lambda: self._client.rename_item(item_id, new_name, etag),
            lambda _: self.operation_succeeded.emit("Elemento renombrado correctamente."),
        )

    def move(self, item_id: str, parent_id: str | None) -> None:
        self._run(
            lambda: self._client.move_item(item_id, parent_id),
            lambda _: self.operation_succeeded.emit("Elemento movido correctamente."),
        )

    def delete(self, item_id: str, etag: str | None) -> None:
        self._run(
            lambda: self._client.delete_item(item_id, etag),
            lambda _: self.operation_succeeded.emit("Elemento enviado a la papelera."),
        )

    def load_info(self, item_id: str) -> None:
        self._run(lambda: self._client.get_item(item_id), self.item_info_loaded.emit)
