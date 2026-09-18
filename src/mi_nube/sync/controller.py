from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot

from mi_nube.auth.errors import AuthenticationError
from mi_nube.domain.models import SyncSummary
from mi_nube.graph.errors import GraphError
from mi_nube.services.sync_service import SyncService

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
        except (GraphError, AuthenticationError) as error:
            self.signals.failed.emit(str(error))
        except Exception:
            LOGGER.exception("Fallo inesperado durante la sincronización")
            self.signals.failed.emit("Ocurrió un error inesperado al sincronizar OneDrive.")
        finally:
            self.signals.finished.emit()


class SyncController(QObject):
    activity_loaded = Signal(object)
    scopes_loaded = Signal(object)
    sync_completed = Signal(object)
    error_occurred = Signal(str)
    busy_changed = Signal(bool)

    def __init__(
        self,
        service: SyncService,
        parent: QObject | None = None,
        interval_ms: int = 5 * 60 * 1000,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._pool = QThreadPool.globalInstance()
        self._worker: _Worker | None = None
        self._connected = False
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.sync_now)

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        if connected:
            self._timer.start()
        else:
            self._timer.stop()

    def load_activity(self, scope_id: str | None = None, search: str = "") -> None:
        self.activity_loaded.emit(self._service.list_activity(scope_id, search))
        self.scopes_loaded.emit(self._service.list_scopes())

    def record_local(self, action: str, target: str, **kwargs) -> None:
        self._service.record_local(action, target, **kwargs)

    def sync_now(self) -> None:
        if not self._connected or self._worker is not None:
            return
        worker = _Worker(self._service.sync_all)
        self._worker = worker
        worker.signals.succeeded.connect(self._synced)
        worker.signals.failed.connect(self.error_occurred.emit)
        worker.signals.finished.connect(self._finished)
        self.busy_changed.emit(True)
        self._pool.start(worker)

    def _synced(self, summary: object) -> None:
        if isinstance(summary, SyncSummary):
            self.sync_completed.emit(summary)
        self.load_activity()

    def _finished(self) -> None:
        self._worker = None
        self.busy_changed.emit(False)
