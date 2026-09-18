from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from mi_nube.auth.errors import AuthenticationCancelled, AuthenticationError
from mi_nube.auth.ports import AuthService
from mi_nube.domain.models import AccountProfile

LOGGER = logging.getLogger(__name__)


class _WorkerSignals(QObject):
    succeeded = Signal(object)
    cancelled = Signal(str)
    failed = Signal(str)
    finished = Signal()


class _AuthWorker(QRunnable):
    def __init__(self, operation: Callable[[], AccountProfile]) -> None:
        super().__init__()
        self._operation = operation
        self.signals = _WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.succeeded.emit(self._operation())
        except AuthenticationCancelled as error:
            self.signals.cancelled.emit(str(error))
        except AuthenticationError as error:
            self.signals.failed.emit(str(error))
        except Exception:
            LOGGER.exception("Fallo inesperado durante la autenticación Microsoft")
            self.signals.failed.emit(
                "No se pudo completar el inicio de sesión. Revisa el registro de la aplicación."
            )
        finally:
            self.signals.finished.emit()


class AuthController(QObject):
    profile_changed = Signal(object)
    busy_changed = Signal(bool)
    error_occurred = Signal(str)
    notice_occurred = Signal(str)

    def __init__(self, service: AuthService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._thread_pool = QThreadPool.globalInstance()
        self._workers: set[_AuthWorker] = set()

    @property
    def current_profile(self) -> AccountProfile | None:
        return self._service.current_profile()

    def sign_in(self) -> None:
        worker = _AuthWorker(self._service.sign_in)
        self._workers.add(worker)
        worker.signals.succeeded.connect(self.profile_changed.emit)
        worker.signals.cancelled.connect(self.notice_occurred.emit)
        worker.signals.failed.connect(self.error_occurred.emit)
        worker.signals.finished.connect(lambda: self._finish_worker(worker))
        self.busy_changed.emit(True)
        self._thread_pool.start(worker)

    def _finish_worker(self, worker: _AuthWorker) -> None:
        self._workers.discard(worker)
        self.busy_changed.emit(False)

    def sign_out(self) -> None:
        try:
            self._service.sign_out()
        except AuthenticationError as error:
            self.error_occurred.emit(str(error))
            return
        self.profile_changed.emit(None)
        self.notice_occurred.emit("La sesión se cerró en este equipo.")
