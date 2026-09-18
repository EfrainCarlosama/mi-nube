import os
from datetime import UTC, datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QPushButton

from mi_nube.app.settings import Settings
from mi_nube.auth.controller import AuthController
from mi_nube.database.sqlite import SqliteDatabase
from mi_nube.domain.models import AccountProfile, ActivityEvent, DriveItem, Project, ProjectMember
from mi_nube.domain.permissions import ProjectRole
from mi_nube.graph.controller import DriveController
from mi_nube.projects.controller import ProjectController
from mi_nube.projects.permission_controller import PermissionController
from mi_nube.repositories.project_repository import SqliteProjectRepository
from mi_nube.services.mock_data import MockDataService
from mi_nube.services.permission_service import PermissionService
from mi_nube.services.project_service import ProjectService
from mi_nube.ui.components.sidebar import Sidebar
from mi_nube.ui.main_window import MainWindow
from mi_nube.ui.project_covers import COVER_HEIGHT, COVER_WIDTH, save_project_cover
from mi_nube.ui.views.activity import ActivityView
from mi_nube.ui.views.home import HomeView
from mi_nube.ui.views.personal import PersonalView
from mi_nube.ui.views.settings import SettingsView
from mi_nube.ui.views.team import TeamView
from mi_nube.ui.views.work import WorkView


class FakeAuthService:
    def current_profile(self) -> AccountProfile | None:
        return None

    def sign_in(self) -> AccountProfile:
        return AccountProfile("1", "Usuario", "usuario@example.com")

    def sign_out(self) -> None:
        return None

    def acquire_access_token(self, scopes) -> str:
        return "test-token"


class FakeDriveClient:
    def list_children(self, item_id=None):
        return ()

    def search(self, query):
        return ()

    def get_quota(self):
        return None


def test_main_window_navigates_all_sections(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    settings = Settings("Mi Nube", "test", "DEBUG", tmp_path)
    drive_client = FakeDriveClient()
    repository = SqliteProjectRepository(SqliteDatabase(settings.database_path))
    window = MainWindow(
        MockDataService(),
        settings,
        AuthController(FakeAuthService()),
        DriveController(drive_client),
        ProjectController(
            ProjectService(
                drive_client,
                repository,
            )
        ),
        DriveController(drive_client),
        PermissionController(PermissionService(drive_client, repository)),
    )

    for key in ("home", "personal", "work", "recent", "shared", "activity", "settings"):
        window.navigate_to(key)
        assert window.current_view_key == key

    window.close()
    app.processEvents()


def test_personal_emails_are_hidden_from_identity_and_team_views(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    email = "propietario@example.com"
    settings = Settings("Mi Nube", "test", "DEBUG", tmp_path)
    repository = SqliteProjectRepository(SqliteDatabase(settings.database_path))
    permission_controller = PermissionController(PermissionService(FakeDriveClient(), repository))

    sidebar = Sidebar()
    sidebar.set_user("Juan Caballero", email)
    assert sidebar._user.text() == "Juan Caballero"
    sidebar.set_user(email, email)
    assert sidebar._user.text() == "Propietario"

    settings_view = SettingsView(settings)
    settings_view.set_profile(AccountProfile("owner", "Juan Caballero", email))
    assert settings_view._account_name.text() == "Juan Caballero"
    assert email not in settings_view._account_email.text()

    home = HomeView(MockDataService())
    home.set_owner("Juan Caballero")
    assert home._title.text() == "Buenos días, Juan Caballero"

    team = TeamView(permission_controller)
    team.set_owner("Juan Caballero", email)
    member = ProjectMember(
        member_id="member-1",
        project_id="project-1",
        email="integrante@example.com",
        display_name="María Pérez",
        role=ProjectRole.COLLABORATOR.value,
        created_at=datetime.now(UTC),
        modified_at=datetime.now(UTC),
    )
    team._show_members((member,))
    visible_team_text = " ".join(
        team._table.item(row, column).text()
        for row in range(team._table.rowCount())
        for column in range(team._table.columnCount())
    )
    assert team._table.columnCount() == 3
    assert visible_team_text == "María Pérez Colaborador Por carpetas"
    assert "@" not in visible_team_text
    assert email not in team._owner.text()

    for widget in (sidebar, settings_view, home, team):
        widget.close()
    app.processEvents()


def test_activity_replaces_legacy_email_actor_with_generic_name() -> None:
    app = QApplication.instance() or QApplication([])
    view = ActivityView(MockDataService())
    view._show_activity(
        (
            ActivityEvent(
                event_id="event-1",
                source="local",
                action="actualizó",
                actor="persona@example.com",
                target="Plano.pdf",
                scope_id="drive:personal",
                project_name=None,
                remote_item_id="item-1",
                occurred_at=datetime.now(UTC),
            ),
        )
    )

    assert view._table.item(0, 1).text() == "Usuario"
    assert "@" not in view._table.item(0, 1).text()
    view.close()
    app.processEvents()


def test_file_browser_uses_colored_folder_icons_and_hides_path_column() -> None:
    app = QApplication.instance() or QApplication([])
    view = PersonalView(DriveController(FakeDriveClient()))
    folder = DriveItem(
        item_id="folder-1",
        name="01 Arquitectura",
        is_folder=True,
        size_bytes=0,
        modified_at=datetime.now(UTC),
        modified_by="Juan Caballero",
        parent_path="/drive/root:/Mi Nube - Trabajo/Proyecto - Casa",
    )

    view._show_items((folder,))

    assert view._table.columnCount() == 6
    assert [view._table.horizontalHeaderItem(index).text() for index in range(6)] == [
        "Nombre",
        "Tipo",
        "Tamaño",
        "Modificado",
        "Modificado por",
        "Estado",
    ]
    assert not view._table.item(0, 0).icon().isNull()
    assert PersonalView._display_item_path(folder).endswith("/Proyecto - Casa/01 Arquitectura")
    view.close()
    app.processEvents()


def test_project_cover_is_normalized_and_project_card_offers_photo(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "source.png"
    image = QImage(400, 800, QImage.Format.Format_RGB32)
    image.fill(QColor("#4F7DF3"))
    assert image.save(str(source))
    cover = save_project_cover(source, tmp_path / "covers", "project-1")
    normalized = QImage(str(cover))
    assert (normalized.width(), normalized.height()) == (COVER_WIDTH, COVER_HEIGHT)

    drive = FakeDriveClient()
    repository = SqliteProjectRepository(SqliteDatabase(tmp_path / "mi-nube.db"))
    work = WorkView(
        ProjectController(ProjectService(drive, repository)),
        DriveController(drive),
        PermissionController(PermissionService(drive, repository)),
        cover_dir=tmp_path / "covers",
    )
    project = Project(
        project_id="project-1",
        name="Casa Rivera",
        client="Familia Rivera",
        remote_item_id="remote-1",
        template_version=1,
        created_at=datetime.now(UTC),
        modified_at=datetime.now(UTC),
    )
    work._show_projects((project,))
    button_texts = {button.text() for button in work.findChildren(QPushButton)}
    assert "Cambiar foto" in button_texts
    assert "Abrir proyecto" in button_texts
    work.close()
    app.processEvents()
