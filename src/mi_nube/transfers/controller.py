from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from mi_nube.domain.models import TransferJob
from mi_nube.graph.errors import GraphError, GraphUploadCancelled
from mi_nube.services.transfer_service import TransferService

LOGGER = logging.getLogger(__name__)


class _Signals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    paused = Signal(str)
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
        except GraphUploadCancelled as error:
            self.signals.paused.emit(str(error))
        except (GraphError, OSError, ValueError) as error:
            self.signals.failed.emit(str(error))
        except Exception:
            LOGGER.exception("Fallo inesperado en una transferencia")
            self.signals.failed.emit("Ocurrió un error inesperado durante la transferencia.")
        finally:
            self.signals.finished.emit()


class TransferController(QObject):
    jobs_changed = Signal(object)
    job_started = Signal(object)
    job_progress = Signal(str, int, int)
    job_completed = Signal(object)
    operation_succeeded = Signal(str)
    error_occurred = Signal(str)
    active_changed = Signal(bool)

    def __init__(self, service: TransferService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._pool = QThreadPool.globalInstance()
        self._worker: _Worker | None = None
        self._active_job: TransferJob | None = None
        self._cancel_event = threading.Event()
        self._connected = False
        self._service.recover_interrupted()
        self._emit_jobs()

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        if not connected:
            self.pause_active()
        else:
            self._start_next()

    def enqueue_upload(self, parent_id: str | None, source: Path) -> TransferJob | None:
        try:
            job = self._service.queue_upload(parent_id, source)
        except OSError as error:
            self.error_occurred.emit(f"No se pudo añadir el archivo: {error}")
            return None
        self._emit_jobs()
        self._start_next()
        return job

    def enqueue_download(
        self, item_id: str, remote_name: str, size_bytes: int, destination: Path
    ) -> TransferJob:
        job = self._service.queue_download(item_id, remote_name, size_bytes, destination)
        self._emit_jobs()
        self._start_next()
        return job

    def pause_active(self) -> None:
        if self._worker is not None:
            self._cancel_event.set()

    def retry(self, job_id: str) -> None:
        self._service.retry(job_id)
        self._emit_jobs()
        self._start_next()

    def cancel(self, job_id: str) -> None:
        if self._active_job and self._active_job.job_id == job_id:
            self.pause_active()
            return
        self._service.cancel(job_id)
        self._emit_jobs()

    def refresh(self) -> None:
        self._emit_jobs()

    def _emit_jobs(self) -> None:
        self.jobs_changed.emit(self._service.list_jobs())

    def _start_next(self) -> None:
        if not self._connected or self._worker is not None:
            return
        job = self._service.next_queued()
        if job is None:
            self.active_changed.emit(False)
            return
        self._active_job = job
        self._cancel_event = threading.Event()
        worker = _Worker(
            lambda: self._service.process(
                job,
                lambda done, total: self.job_progress.emit(job.job_id, done, total),
                self._cancel_event.is_set,
            )
        )
        self._worker = worker
        worker.signals.succeeded.connect(self._completed)
        worker.signals.failed.connect(self.error_occurred.emit)
        worker.signals.paused.connect(lambda _message: None)
        worker.signals.finished.connect(self._finished)
        self.job_started.emit(job)
        self.active_changed.emit(True)
        self._pool.start(worker)

    def _completed(self, job: object) -> None:
        if isinstance(job, TransferJob):
            action = "Subida" if job.direction.value == "upload" else "Descarga"
            self.operation_succeeded.emit(f"{action} completada: {job.remote_name}")
            self.job_completed.emit(job)

    def _finished(self) -> None:
        self._worker = None
        self._active_job = None
        self._emit_jobs()
        self._start_next()
