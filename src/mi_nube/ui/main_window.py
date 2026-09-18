from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mi_nube.app.settings import Settings
from mi_nube.auth.controller import AuthController
from mi_nube.documents.controller import DocumentController
from mi_nube.domain.identity import public_display_name
from mi_nube.domain.models import AccountProfile
from mi_nube.graph.controller import DriveController
from mi_nube.projects.controller import ProjectController
from mi_nube.projects.permission_controller import PermissionController
from mi_nube.services.mock_data import MockDataService
from mi_nube.sync.controller import SyncController
from mi_nube.transfers.controller import TransferController
from mi_nube.ui.components.sidebar import Sidebar
from mi_nube.ui.views.activity import ActivityView
from mi_nube.ui.views.common import PlaceholderView
from mi_nube.ui.views.home import HomeView
from mi_nube.ui.views.personal import PersonalView
from mi_nube.ui.views.settings import SettingsView
from mi_nube.ui.views.work import WorkView
from mi_nube.updates.controller import UpdateController
from mi_nube.updates.errors import UpdateError
from mi_nube.updates.models import UpdateCheckResult, UpdateManifest

LOGGER = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(
        self,
        data_service: MockDataService,
        settings: Settings,
        auth_controller: AuthController,
        drive_controller: DriveController,
        project_controller: ProjectController,
        project_drive_controller: DriveController,
        permission_controller: PermissionController,
        transfer_controller: TransferController | None = None,
        sync_controller: SyncController | None = None,
        document_controller: DocumentController | None = None,
        update_controller: UpdateController | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._auth_controller = auth_controller
        self._drive_controller = drive_controller
        self._transfer_controller = transfer_controller
        self._sync_controller = sync_controller
        self._update_controller = update_controller
        self._pending_update: UpdateManifest | None = None
        self.setWindowTitle("Mi Nube")
        self.setMinimumSize(1024, 680)
        self.resize(1280, 790)

        root = QWidget()
        root.setObjectName("AppRoot")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        self._sidebar = Sidebar()
        self._sidebar.navigation_requested.connect(self.navigate_to)
        root_layout.addWidget(self._sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._build_topbar())

        self._settings_view = SettingsView(settings)
        self._settings_view.sign_in_requested.connect(self._auth_controller.sign_in)
        self._settings_view.sign_out_requested.connect(self._auth_controller.sign_out)
        self._settings_view.check_updates_requested.connect(self._request_update)
        self._personal_view = PersonalView(
            drive_controller,
            transfer_controller=transfer_controller,
            sync_controller=sync_controller,
        )
        self._personal_view.connect_requested.connect(self._auth_controller.sign_in)
        self._work_view = WorkView(
            project_controller,
            project_drive_controller,
            permission_controller,
            transfer_controller,
            sync_controller,
            document_controller,
            settings.data_dir / "project-covers",
        )

        self._activity_view = ActivityView(sync_controller or data_service)
        self._stack = QStackedWidget()
        self._home_view = HomeView(data_service)
        self._views = {
            "home": self._home_view,
            "personal": self._personal_view,
            "work": self._work_view,
            "recent": PlaceholderView(
                "Recientes",
                "Tus archivos usados últimamente",
                "Los archivos recientes aparecerán aquí al conectar Microsoft Graph.",
            ),
            "shared": PlaceholderView(
                "Compartidos",
                "Elementos compartidos contigo y por ti",
                "El contenido compartido se habilitará después de integrar "
                "permisos de Microsoft Graph.",
            ),
            "activity": self._activity_view,
            "settings": self._settings_view,
        }
        for view in self._views.values():
            self._stack.addWidget(view)
        content_layout.addWidget(self._stack, 1)
        root_layout.addWidget(content, 1)
        self._auth_controller.profile_changed.connect(self._on_profile_changed)
        self._auth_controller.busy_changed.connect(self._settings_view.set_busy)
        self._auth_controller.error_occurred.connect(self._show_auth_error)
        self._auth_controller.notice_occurred.connect(self.statusBar().showMessage)
        self._settings_view.set_update_configured(update_controller is not None)
        if update_controller:
            update_controller.check_completed.connect(self._update_checked)
            update_controller.installer_ready.connect(self._update_ready)
            update_controller.download_progress.connect(self._settings_view.show_update_progress)
            update_controller.error_occurred.connect(self._update_error)
            update_controller.busy_changed.connect(self._settings_view.set_update_busy)
        self._on_profile_changed(self._auth_controller.current_profile)
        self.navigate_to("home")

    def _build_topbar(self) -> QFrame:
        topbar = QFrame()
        topbar.setObjectName("TopBar")
        topbar.setFixedHeight(70)
        layout = QHBoxLayout(topbar)
        layout.setContentsMargins(30, 12, 30, 12)
        search = QLineEdit()
        search.setObjectName("SearchInput")
        search.setPlaceholderText("Buscar archivos, carpetas o proyectos")
        search.setMaximumWidth(470)
        layout.addWidget(search)
        layout.addStretch()
        self._account_button = QPushButton("Sin sesión")
        self._account_button.setProperty("secondary", True)
        self._account_button.setToolTip("Abrir configuración de cuenta")
        self._account_button.clicked.connect(lambda: self.navigate_to("settings"))
        layout.addWidget(self._account_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        return topbar

    def _on_profile_changed(self, profile: AccountProfile | None) -> None:
        self._settings_view.set_profile(profile)
        if self._transfer_controller:
            self._transfer_controller.set_connected(profile is not None)
        if self._sync_controller:
            self._sync_controller.set_connected(profile is not None)
        if profile:
            display_name = public_display_name(profile.display_name, "Propietario")
            self._account_button.setText(display_name)
            self._sidebar.set_user(display_name)
            self._home_view.set_owner(display_name)
            self._personal_view.set_connected(True)
            self._work_view.set_connected(True)
            self._work_view.set_owner(display_name, profile.email)
        else:
            self._account_button.setText("Sin sesión")
            self._sidebar.set_user(None)
            self._home_view.set_owner(None)
            self._personal_view.set_connected(False)
            self._work_view.set_connected(False)
            self._work_view.set_owner("Propietario", "")

    def _show_auth_error(self, message: str) -> None:
        LOGGER.warning("Error de autenticación mostrado al usuario: %s", message)
        QMessageBox.warning(self, "No se pudo iniciar sesión", message)

    def _request_update(self) -> None:
        if self._update_controller is None:
            return
        if self._pending_update is None:
            self._update_controller.check()
        else:
            self._update_controller.download(self._pending_update)

    def _update_checked(self, value: object) -> None:
        if not isinstance(value, UpdateCheckResult):
            return
        self._pending_update = value.manifest if value.available else None
        self._settings_view.show_update_result(value)

    def _update_error(self, message: str) -> None:
        self._settings_view.show_update_error(message)

    def _update_ready(self, path: str) -> None:
        answer = QMessageBox.question(
            self,
            "Instalar actualización",
            "La actualización se verificó correctamente. ¿Quieres cerrar Mi Nube e instalarla?",
        )
        if answer != QMessageBox.StandardButton.Yes or self._update_controller is None:
            return
        try:
            self._update_controller.launch_installer(path)
        except UpdateError as error:
            self._update_error(str(error))
            return
        application = QApplication.instance()
        if application:
            application.quit()

    def navigate_to(self, key: str) -> None:
        view = self._views.get(key)
        if view is None:
            LOGGER.warning("Se solicitó una vista inexistente: %s", key)
            return
        self._stack.setCurrentWidget(view)
        self._sidebar.select(key)
        if key == "activity":
            self._activity_view.activate()
        LOGGER.debug("Navegación a vista: %s", key)

    @property
    def current_view_key(self) -> str:
        current = self._stack.currentWidget()
        return next(key for key, view in self._views.items() if view is current)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        LOGGER.info("Aplicación cerrada correctamente")
        super().closeEvent(event)
