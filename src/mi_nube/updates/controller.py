from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from mi_nube.updates.errors import UpdateError
from mi_nube.updates.models import UpdateManifest
from mi_nube.updates.service import UpdateService

LOGGER = logging.getLogger(__name__)


class _UpdateWorkerSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()


class _UpdateWorker(QRunnable):
    def __init__(self, operation: Callable[[], Any]) -> None:
        super().__init__()
        self._operation = operation
        self.signals = _UpdateWorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.succeeded.emit(self._operation())
        except UpdateError as error:
            self.signals.failed.emit(str(error))
        except Exception:
            LOGGER.exception("Fallo inesperado en el sistema de actualizaciones")
            self.signals.failed.emit("Ocurrió un error inesperado al comprobar actualizaciones.")
        finally:
            self.signals.finished.emit()


class UpdateController(QObject):
    check_completed = Signal(object)
    installer_ready = Signal(str)
    download_progress = Signal(int, int)
    error_occurred = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, service: UpdateService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._pool = QThreadPool.globalInstance()
        self._workers: set[_UpdateWorker] = set()

    def _run(self, operation: Callable[[], Any], success: Callable[[Any], None]) -> None:
        worker = _UpdateWorker(operation)
        self._workers.add(worker)
        worker.signals.succeeded.connect(success)
        worker.signals.failed.connect(self.error_occurred.emit)
        worker.signals.finished.connect(lambda: self._finish(worker))
        self.busy_changed.emit(True)
        self._pool.start(worker)

    def _finish(self, worker: _UpdateWorker) -> None:
        self._workers.discard(worker)
        self.busy_changed.emit(bool(self._workers))

    def check(self) -> None:
        self._run(self._service.check, self.check_completed.emit)

    def download(self, manifest: UpdateManifest) -> None:
        self._run(
            lambda: self._service.download(manifest, self.download_progress.emit),
            lambda path: self.installer_ready.emit(str(path)),
        )

    def launch_installer(self, path: str) -> None:
        self._service.launch_installer(Path(path))

    def close(self) -> None:
        self._service.close()
