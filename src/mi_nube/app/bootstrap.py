from __future__ import annotations

import logging

from PySide6.QtWidgets import QApplication

from mi_nube import __version__
from mi_nube.app.logging_config import configure_logging
from mi_nube.app.resources import update_public_key_bytes
from mi_nube.app.settings import Settings
from mi_nube.auth.controller import AuthController
from mi_nube.auth.msal_service import MsalAuthService
from mi_nube.auth.token_cache import create_token_cache_store, create_transfer_protector
from mi_nube.database.sqlite import SqliteDatabase
from mi_nube.documents.controller import DocumentController
from mi_nube.domain.identity import public_display_name
from mi_nube.graph.controller import DriveController
from mi_nube.graph.http_client import HttpGraphDriveClient
from mi_nube.projects.controller import ProjectController
from mi_nube.projects.permission_controller import PermissionController
from mi_nube.repositories.document_repository import SqliteDocumentRepository
from mi_nube.repositories.project_repository import SqliteProjectRepository
from mi_nube.repositories.sync_repository import SqliteSyncRepository
from mi_nube.repositories.transfer_repository import SqliteTransferRepository
from mi_nube.services.document_service import DocumentService
from mi_nube.services.mock_data import MockDataService
from mi_nube.services.permission_service import PermissionService
from mi_nube.services.project_service import ProjectService
from mi_nube.services.sync_service import SyncService
from mi_nube.services.transfer_service import TransferService
from mi_nube.sync.controller import SyncController
from mi_nube.transfers.controller import TransferController
from mi_nube.ui.main_window import MainWindow
from mi_nube.ui.theme import APPLICATION_STYLE
from mi_nube.updates.controller import UpdateController
from mi_nube.updates.errors import UpdateError
from mi_nube.updates.service import UpdateService


def create_application(argv: list[str] | None = None) -> tuple[QApplication, MainWindow]:
    settings = Settings.from_environment()
    log_file = configure_logging(settings.log_dir, settings.log_level)

    application = QApplication.instance() or QApplication(argv or [])
    application.setApplicationName(settings.app_name)
    application.setOrganizationName("Mi Nube")
    application.setStyle("Fusion")
    application.setStyleSheet(APPLICATION_STYLE)

    data_service = MockDataService()
    cache_store = create_token_cache_store(settings.auth_dir)
    auth_service = MsalAuthService(
        settings.microsoft_client_id,
        settings.microsoft_tenant_id,
        cache_store,
    )
    auth_controller = AuthController(auth_service)
    graph_client = HttpGraphDriveClient(auth_service)
    drive_controller = DriveController(graph_client)
    project_drive_controller = DriveController(graph_client)
    database = SqliteDatabase(settings.database_path)
    project_repository = SqliteProjectRepository(database)
    transfer_repository = SqliteTransferRepository(database)
    transfer_controller = TransferController(
        TransferService(graph_client, transfer_repository, create_transfer_protector())
    )
    sync_controller = SyncController(
        SyncService(
            graph_client,
            SqliteSyncRepository(database),
            project_repository,
            lambda: (
                public_display_name(auth_service.current_profile().display_name, "Propietario")
                if auth_service.current_profile()
                else "Propietario"
            ),
        )
    )
    document_controller = DocumentController(
        DocumentService(
            graph_client,
            SqliteDocumentRepository(database),
            lambda: (
                public_display_name(auth_service.current_profile().display_name, "Propietario")
                if auth_service.current_profile()
                else "Propietario"
            ),
        )
    )
    project_controller = ProjectController(ProjectService(graph_client, project_repository))
    permission_controller = PermissionController(
        PermissionService(graph_client, project_repository)
    )
    update_controller: UpdateController | None = None
    if settings.update_manifest_url:
        try:
            update_controller = UpdateController(
                UpdateService(
                    __version__,
                    settings.update_manifest_url,
                    update_public_key_bytes(),
                    settings.data_dir / "updates",
                )
            )
        except (OSError, UpdateError):
            logging.getLogger(__name__).exception(
                "El canal de actualizaciones no pudo inicializarse"
            )
    application.aboutToQuit.connect(graph_client.close)
    if update_controller:
        application.aboutToQuit.connect(update_controller.close)
    window = MainWindow(
        data_service=data_service,
        settings=settings,
        auth_controller=auth_controller,
        drive_controller=drive_controller,
        project_controller=project_controller,
        project_drive_controller=project_drive_controller,
        permission_controller=permission_controller,
        transfer_controller=transfer_controller,
        sync_controller=sync_controller,
        document_controller=document_controller,
        update_controller=update_controller,
    )
    logging.getLogger(__name__).info(
        "Aplicación iniciada en entorno %s. Log: %s", settings.environment, log_file
    )
    return application, window
