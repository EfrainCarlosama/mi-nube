from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mi_nube.documents.controller import DocumentController
from mi_nube.domain.models import Project
from mi_nube.graph.controller import DriveController
from mi_nube.projects.controller import ProjectController
from mi_nube.projects.errors import ProjectError
from mi_nube.projects.permission_controller import PermissionController
from mi_nube.services.template_codec import format_template, parse_template
from mi_nube.sync.controller import SyncController
from mi_nube.transfers.controller import TransferController
from mi_nube.ui.formatters import relative_time
from mi_nube.ui.icons import colored_folder_icon, folder_color
from mi_nube.ui.project_covers import project_cover_path, save_project_cover
from mi_nube.ui.views.common import page_header
from mi_nube.ui.views.documents import DocumentRegistryView
from mi_nube.ui.views.personal import PersonalView
from mi_nube.ui.views.team import TeamView


class _ProjectCoverLabel(QLabel):
    def __init__(self, project_name: str, cover: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project_name = project_name
        self._source = QPixmap(str(cover)) if cover.is_file() else QPixmap()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(142)
        self.setMinimumWidth(180)
        if self._source.isNull():
            accent = folder_color(project_name)
            self.setStyleSheet(
                f"background: #F2F5FC; border: 1px solid {accent}; border-radius: 11px;"
            )
            self.setPixmap(colored_folder_icon(project_name, 72).pixmap(72, 72))
        else:
            self.setStyleSheet("background: #E9EEF5; border-radius: 11px;")

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        if self._source.isNull() or self.width() <= 0 or self.height() <= 0:
            return
        scaled = self._source.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        left = max(0, (scaled.width() - self.width()) // 2)
        top = max(0, (scaled.height() - self.height()) // 2)
        self.setPixmap(scaled.copy(left, top, self.width(), self.height()))


class _NewProjectDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nuevo proyecto")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("Ej. Residencia Carlos")
        self.client = QLineEdit()
        self.client.setPlaceholderText("Ej. Sr. Carlos")
        self.use_template = QCheckBox("Crear automáticamente la estructura base")
        self.use_template.setChecked(True)
        form.addRow("Nombre del proyecto:", self.name)
        form.addRow("Cliente:", self.client)
        form.addRow("", self.use_template)
        layout.addLayout(form)
        notice = QLabel("La carpeta se creará dentro de “Mi Nube - Trabajo” en tu OneDrive.")
        notice.setObjectName("Muted")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Crear proyecto")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class _TemplateDialog(QDialog):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Plantilla de proyectos")
        self.resize(620, 650)
        layout = QVBoxLayout(self)
        help_text = QLabel(
            "Escribe una carpeta por línea. Usa dos espacios por cada nivel de subcarpeta. "
            "Los cambios se aplicarán únicamente a proyectos nuevos."
        )
        help_text.setWordWrap(True)
        help_text.setObjectName("Muted")
        layout.addWidget(help_text)
        self.editor = QPlainTextEdit(text)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.editor, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar plantilla")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class WorkView(QWidget):
    def __init__(
        self,
        controller: ProjectController,
        project_drive_controller: DriveController,
        permission_controller: PermissionController,
        transfer_controller: TransferController | None = None,
        sync_controller: SyncController | None = None,
        document_controller: DocumentController | None = None,
        cover_dir: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._projects: tuple[Project, ...] = ()
        self._connected = False
        self._loaded_once = False
        self._cover_dir = cover_dir or Path.cwd() / ".mi-nube-project-covers"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._stack = QStackedWidget()
        self._projects_page = self._build_projects_page()
        self._detail_page = self._build_detail_page(
            project_drive_controller,
            permission_controller,
            transfer_controller,
            sync_controller,
            document_controller,
        )
        self._stack.addWidget(self._projects_page)
        self._stack.addWidget(self._detail_page)
        layout.addWidget(self._stack)

        controller.projects_loaded.connect(self._show_projects)
        controller.project_created.connect(self._project_created)
        controller.template_saved.connect(
            lambda template: self._status.setText(
                f"Plantilla guardada. Versión {template.version}."
            )
        )
        controller.progress_changed.connect(self._show_progress)
        controller.error_occurred.connect(self._show_error)
        controller.busy_changed.connect(self._set_busy)

    def _build_projects_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(36, 30, 36, 30)
        layout.setSpacing(16)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        title, subtitle = page_header("Trabajo", "Proyectos de ingeniería y arquitectura")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        header.addLayout(heading)
        header.addStretch()
        self._template_button = QPushButton("Configurar plantilla")
        self._template_button.setProperty("secondary", True)
        self._template_button.clicked.connect(self._edit_template)
        self._new_project_button = QPushButton("＋  Nuevo proyecto")
        self._new_project_button.setProperty("primary", True)
        self._new_project_button.clicked.connect(self._new_project)
        header.addWidget(self._template_button)
        header.addWidget(self._new_project_button)
        layout.addLayout(header)

        tools = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setObjectName("SearchInput")
        self._search.setPlaceholderText("Buscar proyectos o clientes...")
        self._search.setMaximumWidth(430)
        self._search.textChanged.connect(self._apply_filter)
        self._status = QLabel("Conecta OneDrive para crear proyectos.")
        self._status.setObjectName("Muted")
        tools.addWidget(self._search)
        tools.addStretch()
        tools.addWidget(self._status)
        layout.addLayout(tools)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setMinimumHeight(24)
        self._progress.hide()
        layout.addWidget(self._progress)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._cards_container = QWidget()
        self._grid = QGridLayout(self._cards_container)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(14)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        for column in range(3):
            self._grid.setColumnStretch(column, 1)
        scroll.setWidget(self._cards_container)
        layout.addWidget(scroll, 1)
        return page

    def _build_detail_page(
        self,
        drive_controller: DriveController,
        permission_controller: PermissionController,
        transfer_controller: TransferController | None,
        sync_controller: SyncController | None,
        document_controller: DocumentController | None,
    ) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.setContentsMargins(36, 18, 36, 0)
        back = QPushButton("← Volver a proyectos")
        back.setProperty("secondary", True)
        back.clicked.connect(self._back_to_projects)
        self._project_context = QLabel()
        self._project_context.setObjectName("Muted")
        top.addWidget(back)
        top.addWidget(self._project_context)
        top.addStretch()
        layout.addLayout(top)
        tabs = QTabWidget()
        self._files_view = PersonalView(
            drive_controller,
            title_text="Archivos del proyecto",
            subtitle_text="Contenido almacenado directamente en OneDrive",
            show_connect=False,
            transfer_controller=transfer_controller,
            sync_controller=sync_controller,
            document_controller=document_controller,
        )
        self._team_view = TeamView(permission_controller)
        tabs.addTab(self._files_view, "Archivos")
        self._documents_view = (
            DocumentRegistryView(document_controller) if document_controller else None
        )
        if self._documents_view:
            tabs.addTab(self._documents_view, "Documentos")
        tabs.addTab(self._team_view, "Equipo")
        layout.addWidget(tabs, 1)
        return page

    def _new_project(self) -> None:
        if not self._connected:
            self._show_error("Conecta tu cuenta de OneDrive antes de crear un proyecto.")
            return
        dialog = _NewProjectDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._controller.create_project(
            dialog.name.text(),
            dialog.client.text(),
            dialog.use_template.isChecked(),
        )

    def _edit_template(self) -> None:
        try:
            template = self._controller.default_template()
            dialog = _TemplateDialog(format_template(template.folders), self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            folders = parse_template(dialog.editor.toPlainText())
            self._controller.save_default_template(folders)
        except ProjectError as error:
            self._show_error(str(error))

    def _project_created(self, project: object) -> None:
        if isinstance(project, Project):
            self._status.setText(f"Proyecto “{project.name}” creado correctamente.")
        self._progress.hide()
        self._controller.load_projects()

    def _show_progress(self, completed: int, total: int, label: str) -> None:
        percentage = round((completed / total) * 100) if total else 100
        self._progress.setValue(percentage)
        self._progress.setFormat(f"{percentage} % — {label}")
        self._progress.show()
        self._status.setText(f"Creando estructura: {completed}/{total}")

    def _show_projects(self, projects: object) -> None:
        if not isinstance(projects, (tuple, list)):
            return
        self._projects = tuple(project for project in projects if isinstance(project, Project))
        self._render_projects(self._projects)
        if not self._projects:
            self._status.setText("Aún no hay proyectos. Crea el primero cuando estés listo.")
        else:
            count = len(self._projects)
            self._status.setText(f"{count} proyecto" if count == 1 else f"{count} proyectos")

    def _apply_filter(self, query: str) -> None:
        normalized = query.strip().casefold()
        if not normalized:
            self._render_projects(self._projects)
            return
        self._render_projects(
            tuple(
                project
                for project in self._projects
                if normalized in project.name.casefold() or normalized in project.client.casefold()
            )
        )

    def _clear_grid(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _render_projects(self, projects: tuple[Project, ...]) -> None:
        self._clear_grid()
        if not projects:
            empty = QLabel("No hay proyectos que mostrar.")
            empty.setObjectName("Muted")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._grid.addWidget(empty, 0, 0, 1, 3)
            return
        for index, project in enumerate(projects):
            card = QFrame()
            card.setProperty("card", True)
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            card.setMinimumHeight(330)
            card.setMaximumHeight(350)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 16, 16, 16)
            card_layout.setSpacing(10)
            cover = project_cover_path(self._cover_dir, project.project_id)
            cover_label = _ProjectCoverLabel(project.name, cover)
            name = QLabel(project.name)
            name.setObjectName("SectionTitle")
            name.setWordWrap(True)
            client = QLabel(project.client)
            client.setObjectName("Muted")
            stats = QLabel(
                f"Plantilla v{project.template_version}  ·  {relative_time(project.modified_at)}"
            )
            stats.setObjectName("Muted")
            photo_button = QPushButton("Cambiar foto" if cover.is_file() else "＋ Añadir foto")
            photo_button.setProperty("secondary", True)
            photo_button.clicked.connect(
                lambda _checked=False, value=project: self._choose_project_cover(value)
            )
            open_button = QPushButton("Abrir proyecto")
            open_button.setProperty("primary", True)
            open_button.clicked.connect(
                lambda _checked=False, value=project: self._open_project(value)
            )
            actions = QHBoxLayout()
            actions.addWidget(photo_button)
            actions.addWidget(open_button, 1)
            card_layout.addWidget(cover_label)
            card_layout.addWidget(name)
            card_layout.addWidget(client)
            card_layout.addWidget(stats)
            card_layout.addLayout(actions)
            self._grid.addWidget(card, index // 3, index % 3)

    def _choose_project_cover(self, project: Project) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar foto del proyecto",
            str(Path.home()),
            "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not filename:
            return
        try:
            save_project_cover(Path(filename), self._cover_dir, project.project_id)
        except ValueError as error:
            QMessageBox.warning(self, "Foto del proyecto", str(error))
            return
        self._status.setText(f"Foto de “{project.name}” actualizada.")
        self._apply_filter(self._search.text())

    def _open_project(self, project: Project) -> None:
        if not self._connected:
            self._show_error("Conecta OneDrive para abrir los archivos del proyecto.")
            return
        self._project_context.setText(f"{project.name} · {project.client}")
        self._files_view.set_root(project.remote_item_id, project.name)
        self._files_view.set_activity_scope(f"project:{project.project_id}", project.name)
        self._files_view.set_document_project(project.project_id)
        if self._documents_view:
            self._documents_view.set_project(project)
        self._team_view.set_project(project)
        self._stack.setCurrentWidget(self._detail_page)
        self._files_view.load_root()

    def _back_to_projects(self) -> None:
        self._stack.setCurrentWidget(self._projects_page)
        self._controller.load_projects()

    def _show_error(self, message: str) -> None:
        self._progress.hide()
        self._status.setText(message)
        QMessageBox.warning(self, "Proyectos", message)

    def _set_busy(self, busy: bool) -> None:
        self._new_project_button.setEnabled(not busy and self._connected)
        self._template_button.setEnabled(not busy)
        self._search.setEnabled(not busy)
        if busy and not self._progress.isVisible():
            self._status.setText("Cargando proyectos...")

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        self._new_project_button.setEnabled(connected)
        if connected:
            if not self._loaded_once:
                self._loaded_once = True
                self._controller.load_projects()
        else:
            self._status.setText("Conecta OneDrive para crear o abrir proyectos.")

    def set_owner(self, display_name: str, email: str) -> None:
        self._team_view.set_owner(display_name, email)
