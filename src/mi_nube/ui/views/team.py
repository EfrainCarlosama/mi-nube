from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mi_nube.domain.identity import public_display_name
from mi_nube.domain.models import (
    FolderPermissionRule,
    PermissionChange,
    PermissionEditorData,
    Project,
    ProjectFolder,
    ProjectMember,
)
from mi_nube.domain.permissions import (
    DEFAULT_CAPABILITIES,
    Capability,
    GraphAccess,
    PermissionLevel,
    ProjectRole,
    graph_access_for,
)
from mi_nube.projects.permission_controller import PermissionController

_EDITABLE_ROLES = (
    ProjectRole.PROJECT_ADMIN,
    ProjectRole.COLLABORATOR,
    ProjectRole.VIEWER,
)


def _graph_access_label(access: GraphAccess) -> str:
    if access is GraphAccess.WRITE:
        return "Editor (write)"
    if access is GraphAccess.READ:
        return "Lector (read)"
    return "Sin acceso directo"


class _MemberDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Agregar integrante")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.display_name = QLineEdit()
        self.display_name.setPlaceholderText("Nombre para mostrar")
        self.email = QLineEdit()
        self.email.setPlaceholderText("persona@example.com")
        self.role = QComboBox()
        for role in _EDITABLE_ROLES:
            self.role.addItem(role.value, role)
        form.addRow("Nombre:", self.display_name)
        form.addRow("Correo Microsoft:", self.email)
        form.addRow("Rol:", self.role)
        layout.addLayout(form)
        warning = QLabel(
            "Administrador y Visualizador reciben inmediatamente una invitación real al "
            "proyecto completo. Un Colaborador se invita al guardar sus carpetas permitidas. "
            "El correo se usa solo para enviar y administrar el acceso; no se mostrará en la "
            "interfaz después de registrar a la persona."
        )
        warning.setWordWrap(True)
        warning.setProperty("warning", True)
        layout.addWidget(warning)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Agregar integrante")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def selected_role(self) -> ProjectRole:
        return self.role.currentData()


class _CapabilitiesDialog(QDialog):
    def __init__(self, capabilities: Capability, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Permiso personalizado")
        layout = QVBoxLayout(self)
        self._checks: dict[Capability, QCheckBox] = {}
        labels = {
            Capability.VIEW: "Visualizar",
            Capability.DOWNLOAD: "Descargar",
            Capability.UPLOAD: "Subir",
            Capability.CREATE_FOLDER: "Crear carpetas",
            Capability.RENAME: "Renombrar",
            Capability.MODIFY: "Modificar",
            Capability.MOVE: "Mover",
            Capability.DELETE: "Eliminar",
        }
        for capability, label in labels.items():
            check = QCheckBox(label)
            check.setChecked(bool(capabilities & capability))
            self._checks[capability] = check
            layout.addWidget(check)
        note = QLabel(
            "OneDrive Personal convertirá esta combinación a read o write. Los controles "
            "individuales solo pueden imponerse dentro de Mi Nube."
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def capabilities(self) -> Capability:
        result = Capability.NONE
        for capability, check in self._checks.items():
            if check.isChecked():
                result |= capability
        return result


class _PermissionDialog(QDialog):
    def __init__(self, data: PermissionEditorData, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Permisos — {data.member.display_name}")
        self.resize(920, 680)
        self._data = data
        self._rows: dict[str, tuple[ProjectFolder, QComboBox, QCheckBox, QTreeWidgetItem]] = {}
        self._custom: dict[str, Capability] = {}
        self._initial: dict[str, tuple[PermissionLevel, Capability, bool]] = {}

        layout = QVBoxLayout(self)
        notice = QLabel(
            "Compatibilidad OneDrive Personal: Solo ver y Ver/descargar ⇒ read. "
            "Subir, Modificar y Control total ⇒ write. Una excepción en una subcarpeta no "
            "puede quitar un acceso que OneDrive ya heredó desde su carpeta superior."
        )
        notice.setWordWrap(True)
        notice.setProperty("warning", True)
        layout.addWidget(notice)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(
            ("Carpeta", "Política de Mi Nube", "Acceso real OneDrive", "Nuevas subcarpetas")
        )
        header = self._tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._tree, 1)

        self._build_tree(data)
        self._tree.expandToDepth(0)

        self._custom_button = QPushButton("Configurar permiso personalizado seleccionado")
        self._custom_button.setProperty("secondary", True)
        self._custom_button.clicked.connect(self._configure_selected_custom)
        layout.addWidget(self._custom_button)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Aplicar cambios")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _effective_rule(
        self,
        folder: ProjectFolder,
        folders: dict[str, ProjectFolder],
        rules_by_folder: dict[str | None, FolderPermissionRule],
    ) -> FolderPermissionRule | None:
        current: ProjectFolder | None = folder
        while current is not None:
            rule = rules_by_folder.get(current.folder_id)
            if rule is not None:
                return rule
            current = folders.get(current.parent_folder_id) if current.parent_folder_id else None
        return rules_by_folder.get(None)

    def _build_tree(self, data: PermissionEditorData) -> None:
        folders = {folder.folder_id: folder for folder in data.folders}
        rules_by_folder = {rule.folder_id: rule for rule in data.rules}
        items: dict[str, QTreeWidgetItem] = {}
        for folder in data.folders:
            parent_item = items.get(folder.parent_folder_id or "")
            item = QTreeWidgetItem(parent_item or self._tree, (folder.name,))
            item.setData(0, Qt.ItemDataRole.UserRole, folder.folder_id)
            items[folder.folder_id] = item

            effective = self._effective_rule(folder, folders, rules_by_folder)
            level = PermissionLevel(effective.level) if effective else PermissionLevel.NO_ACCESS
            capabilities = (
                Capability(effective.capabilities)
                if effective
                else DEFAULT_CAPABILITIES[PermissionLevel.NO_ACCESS]
            )
            apply_new = effective.apply_to_new_subfolders if effective else True
            direct = rules_by_folder.get(folder.folder_id)
            if effective and direct is None:
                item.setText(0, f"{folder.name}  (heredado)")

            combo = QComboBox()
            for candidate in PermissionLevel:
                combo.addItem(candidate.value, candidate)
            combo.setCurrentIndex(combo.findData(level))
            inherit = QCheckBox("Sí")
            inherit.setChecked(apply_new)
            self._tree.setItemWidget(item, 1, combo)
            self._tree.setItemWidget(item, 3, inherit)
            self._custom[folder.folder_id] = capabilities
            self._initial[folder.folder_id] = (level, capabilities, apply_new)
            self._rows[folder.folder_id] = (folder, combo, inherit, item)
            combo.currentIndexChanged.connect(
                lambda _index, folder_id=folder.folder_id: self._update_access(folder_id)
            )
            self._update_access(folder.folder_id)

    def _update_access(self, folder_id: str) -> None:
        _folder, combo, _inherit, item = self._rows[folder_id]
        level: PermissionLevel = combo.currentData()
        capabilities = self._custom[folder_id]
        if level is not PermissionLevel.CUSTOM:
            capabilities = DEFAULT_CAPABILITIES[level]
        item.setText(2, _graph_access_label(graph_access_for(level, capabilities)))

    def _configure_selected_custom(self) -> None:
        item = self._tree.currentItem()
        if item is None:
            QMessageBox.information(self, "Permisos", "Selecciona primero una carpeta.")
            return
        folder_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(folder_id, str) or folder_id not in self._rows:
            return
        dialog = _CapabilitiesDialog(self._custom[folder_id], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._custom[folder_id] = dialog.capabilities
        combo = self._rows[folder_id][1]
        combo.setCurrentIndex(combo.findData(PermissionLevel.CUSTOM))
        self._update_access(folder_id)

    @property
    def updates(self) -> tuple[tuple[str, PermissionLevel, Capability, bool], ...]:
        changes: list[tuple[str, PermissionLevel, Capability, bool]] = []
        for folder_id, (_folder, combo, inherit, _item) in self._rows.items():
            level: PermissionLevel = combo.currentData()
            capabilities = (
                self._custom[folder_id]
                if level is PermissionLevel.CUSTOM
                else DEFAULT_CAPABILITIES[level]
            )
            current = (level, capabilities, inherit.isChecked())
            if current != self._initial[folder_id]:
                changes.append((folder_id, *current))
        return tuple(changes)


class _HistoryDialog(QDialog):
    def __init__(
        self,
        changes: Sequence[PermissionChange],
        member_names: dict[str, str],
        owner_name: str,
        owner_email: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Historial de permisos")
        self.resize(920, 540)
        layout = QVBoxLayout(self)
        table = QTableWidget(len(changes), 6)
        table.setHorizontalHeaderLabels(
            ("Fecha", "Usuario", "Carpeta", "Anterior", "Nuevo", "Administrador")
        )
        table.horizontalHeader().setStretchLastSection(True)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for row, change in enumerate(changes):
            member_name = member_names.get(change.member_email.casefold(), "Integrante")
            actor_name = (
                owner_name
                if owner_email and change.actor_email.casefold() == owner_email.casefold()
                else member_names.get(change.actor_email.casefold(), "Administrador")
            )
            values = (
                change.occurred_at.astimezone().strftime("%d/%m/%Y %H:%M"),
                member_name,
                change.folder_path,
                change.previous_level,
                change.new_level,
                actor_name,
            )
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class TeamView(QWidget):
    def __init__(self, controller: PermissionController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._project: Project | None = None
        self._members: tuple[ProjectMember, ...] = ()
        self._owner_name = "Propietario"
        self._owner_email = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 22)
        header = QHBoxLayout()
        title = QLabel("Equipo y accesos")
        title.setObjectName("SectionTitle")
        self._status = QLabel("Selecciona un proyecto.")
        self._status.setObjectName("Muted")
        self._add_button = QPushButton("＋ Agregar integrante")
        self._add_button.setProperty("primary", True)
        self._add_button.clicked.connect(self._add_member)
        header.addWidget(title)
        header.addWidget(self._status)
        header.addStretch()
        header.addWidget(self._add_button)
        layout.addLayout(header)

        self._owner = QLabel()
        self._owner.setWordWrap(True)
        self._owner.setStyleSheet("font-weight: 600; padding: 10px;")
        layout.addWidget(self._owner)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(("Nombre", "Rol", "Acceso real"))
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.itemSelectionChanged.connect(self._update_buttons)
        layout.addWidget(self._table, 1)

        actions = QHBoxLayout()
        self._permissions_button = QPushButton("Editar permisos por carpeta")
        self._role_button = QPushButton("Cambiar rol")
        self._remove_button = QPushButton("Quitar acceso")
        self._history_button = QPushButton("Historial")
        for button in (
            self._permissions_button,
            self._role_button,
            self._remove_button,
            self._history_button,
        ):
            button.setProperty("secondary", True)
            actions.addWidget(button)
        self._remove_button.setProperty("danger", True)
        self._permissions_button.clicked.connect(self._edit_permissions)
        self._role_button.clicked.connect(self._change_role)
        self._remove_button.clicked.connect(self._remove_member)
        self._history_button.clicked.connect(self._load_history)
        actions.addStretch()
        layout.addLayout(actions)

        controller.team_loaded.connect(self._show_members)
        controller.member_added.connect(self._operation_completed)
        controller.member_removed.connect(self._operation_completed)
        controller.role_changed.connect(self._operation_completed)
        controller.editor_loaded.connect(self._open_permission_editor)
        controller.permissions_saved.connect(self._permissions_completed)
        controller.history_loaded.connect(self._show_history)
        controller.progress_changed.connect(self._show_progress)
        controller.error_occurred.connect(self._show_error)
        controller.busy_changed.connect(self._set_busy)
        self._update_owner()
        self._update_buttons()

    def set_owner(self, display_name: str, email: str) -> None:
        self._owner_name = public_display_name(display_name, "Propietario")
        self._owner_email = email
        self._update_owner()

    def _update_owner(self) -> None:
        self._owner.setText(
            f"Propietario general: {self._owner_name} · Acceso completo no revocable"
        )

    def set_project(self, project: Project) -> None:
        self._project = project
        self._controller.load_team(project.project_id)

    def _selected_member(self) -> ProjectMember | None:
        row = self._table.currentRow()
        item = self._table.item(row, 0) if row >= 0 else None
        member_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        return next((member for member in self._members if member.member_id == member_id), None)

    def _add_member(self) -> None:
        if self._project is None:
            return
        dialog = _MemberDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._controller.add_member(
            self._project.project_id,
            dialog.email.text(),
            dialog.display_name.text(),
            dialog.selected_role,
            self._owner_email,
        )

    def _change_role(self) -> None:
        member = self._selected_member()
        if member is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Cambiar rol")
        layout = QFormLayout(dialog)
        combo = QComboBox()
        for role in _EDITABLE_ROLES:
            combo.addItem(role.value, role)
        current_role = ProjectRole(member.role)
        combo.setCurrentIndex(combo.findData(current_role))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow("Nuevo rol:", combo)
        layout.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._controller.change_role(member.member_id, combo.currentData(), self._owner_email)

    def _edit_permissions(self) -> None:
        member = self._selected_member()
        if member:
            self._controller.load_editor(member.member_id)

    def _open_permission_editor(self, value: object) -> None:
        if not isinstance(value, PermissionEditorData):
            return
        dialog = _PermissionDialog(value, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        updates = dialog.updates
        if not updates:
            self._status.setText("No se realizaron cambios.")
            return
        self._controller.save_folder_permissions(value.member.member_id, updates, self._owner_email)

    def _remove_member(self) -> None:
        member = self._selected_member()
        if member is None:
            return
        answer = QMessageBox.question(
            self,
            "Quitar acceso",
            "¿Quieres revocar en OneDrive todos los accesos directos de "
            f"{public_display_name(member.display_name, 'Integrante')}?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._controller.remove_member(member.member_id, self._owner_email)

    def _load_history(self) -> None:
        if self._project:
            self._controller.load_history(self._project.project_id)

    def _show_members(self, value: object) -> None:
        if not isinstance(value, (tuple, list)):
            return
        self._members = tuple(member for member in value if isinstance(member, ProjectMember))
        self._table.setRowCount(len(self._members))
        for row, member in enumerate(self._members):
            role = ProjectRole(member.role)
            if role is ProjectRole.PROJECT_ADMIN:
                real_access = "Editor del proyecto"
            elif role is ProjectRole.VIEWER:
                real_access = "Lector del proyecto"
            else:
                real_access = "Por carpetas"
            for column, text in enumerate(
                (public_display_name(member.display_name, "Integrante"), role.value, real_access)
            ):
                item = QTableWidgetItem(text)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, member.member_id)
                self._table.setItem(row, column, item)
        count = len(self._members)
        self._status.setText(f"{count} integrante" if count == 1 else f"{count} integrantes")
        self._table.clearSelection()
        self._update_buttons()

    def _operation_completed(self, _value: object) -> None:
        if self._project:
            self._controller.load_team(self._project.project_id)

    def _permissions_completed(self, _value: object) -> None:
        self._status.setText("Permisos actualizados en Mi Nube y OneDrive.")

    def _show_history(self, value: object) -> None:
        if isinstance(value, (tuple, list)):
            changes = tuple(item for item in value if isinstance(item, PermissionChange))
            member_names = {
                member.email.casefold(): public_display_name(member.display_name, "Integrante")
                for member in self._members
            }
            _HistoryDialog(
                changes,
                member_names,
                self._owner_name,
                self._owner_email,
                self,
            ).exec()

    def _show_progress(self, done: int, total: int, label: str) -> None:
        self._status.setText(f"Aplicando permisos {done}/{total}: {label}")

    def _show_error(self, message: str) -> None:
        self._status.setText(message)
        QMessageBox.warning(self, "Equipo y permisos", message)

    def _set_busy(self, busy: bool) -> None:
        self._table.setEnabled(not busy)
        self._add_button.setEnabled(not busy and self._project is not None)
        self._history_button.setEnabled(not busy and self._project is not None)
        if busy:
            self._status.setText("Comunicándose con OneDrive...")
        self._update_buttons()

    def _update_buttons(self) -> None:
        enabled = self._selected_member() is not None and self._table.isEnabled()
        self._permissions_button.setEnabled(enabled)
        self._role_button.setEnabled(enabled)
        self._remove_button.setEnabled(enabled)
