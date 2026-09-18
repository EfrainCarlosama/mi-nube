from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mi_nube.documents.controller import DocumentController
from mi_nube.documents.errors import DocumentError
from mi_nube.domain.identity import public_display_name
from mi_nube.domain.models import (
    DocumentHistory,
    DocumentMetadata,
    DocumentStatus,
    DriveItem,
    Project,
)
from mi_nube.ui.formatters import relative_time


class DocumentEditorDialog(QDialog):
    def __init__(
        self,
        item: DriveItem,
        metadata: DocumentMetadata | None,
        controller: DocumentController,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._item = item
        self._controller = controller
        self.setWindowTitle("Estado y revisión del documento")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        name = QLabel(f"<b>{item.name}</b>")
        layout.addWidget(name)
        form = QFormLayout()
        self.status = QComboBox()
        for status in DocumentStatus:
            self.status.addItem(status.label, status)
        self.revision = QLineEdit(metadata.revision if metadata else "R01")
        self.revision.setPlaceholderText("R01")
        self.naming = QCheckBox("Usar nomenclatura de Mi Nube")
        self.naming.setChecked(metadata.naming_enabled if metadata else False)
        self.discipline = QLineEdit(metadata.discipline_code or "" if metadata else "")
        self.discipline.setPlaceholderText("ARQ, EST, PRE...")
        self.number = QLineEdit(metadata.document_number or "" if metadata else "")
        self.number.setPlaceholderText("001")
        self.title = QLineEdit(metadata.title or "" if metadata else "")
        self.title.setPlaceholderText("Planta-Baja (opcional)")
        self.rename_remote = QCheckBox("Renombrar también el archivo real en OneDrive")
        if metadata:
            self.status.setCurrentIndex(self.status.findData(metadata.status))
        form.addRow("Estado:", self.status)
        form.addRow("Revisión:", self.revision)
        form.addRow("", self.naming)
        form.addRow("Disciplina:", self.discipline)
        form.addRow("Número:", self.number)
        form.addRow("Título:", self.title)
        form.addRow("", self.rename_remote)
        layout.addLayout(form)
        self.preview = QLabel()
        self.preview.setObjectName("Muted")
        self.preview.setWordWrap(True)
        layout.addWidget(self.preview)
        notice = QLabel(
            "El estado y la revisión son metadatos internos. Solo la opción de renombrado "
            "modifica OneDrive."
        )
        notice.setObjectName("Muted")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar documento")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.naming.toggled.connect(self._update_enabled)
        for field in (self.revision, self.discipline, self.number, self.title):
            field.textChanged.connect(self._update_preview)
        self._update_enabled()

    def _update_enabled(self) -> None:
        enabled = self.naming.isChecked()
        for widget in (self.discipline, self.number, self.title, self.rename_remote):
            widget.setEnabled(enabled)
        if not enabled:
            self.rename_remote.setChecked(False)
        self._update_preview()

    def _update_preview(self) -> None:
        if not self.naming.isChecked():
            self.preview.setText("Nomenclatura desactivada; se conservará el nombre actual.")
            return
        try:
            value = self._controller.preview_name(
                self._item.name,
                self.discipline.text(),
                self.number.text(),
                self.revision.text(),
                self.title.text(),
            )
            self.preview.setText(f"Vista previa: {value}")
        except DocumentError as error:
            self.preview.setText(str(error))

    def _validate_and_accept(self) -> None:
        try:
            self._controller.normalize_revision(self.revision.text())
            if self.naming.isChecked():
                self._controller.preview_name(
                    self._item.name,
                    self.discipline.text(),
                    self.number.text(),
                    self.revision.text(),
                    self.title.text(),
                )
        except DocumentError as error:
            QMessageBox.warning(self, "Documento", str(error))
            return
        self.accept()


class DocumentRegistryView(QWidget):
    def __init__(self, controller: DocumentController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._project: Project | None = None
        self._documents: tuple[DocumentMetadata, ...] = ()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName("SearchInput")
        self.search.setPlaceholderText("Buscar documento, disciplina o revisión...")
        self.search.textChanged.connect(self.refresh)
        self.status = QComboBox()
        self.status.addItem("Todos los estados", None)
        for status in DocumentStatus:
            self.status.addItem(status.label, status)
        self.status.currentIndexChanged.connect(self.refresh)
        history = QPushButton("Ver historial")
        history.setProperty("secondary", True)
        history.clicked.connect(self._show_history)
        export = QPushButton("Exportar reporte CSV")
        export.setProperty("primary", True)
        export.clicked.connect(self._export)
        controls.addWidget(self.search, 1)
        controls.addWidget(self.status)
        controls.addWidget(history)
        controls.addWidget(export)
        layout.addLayout(controls)
        self.summary = QLabel("Sin proyecto seleccionado")
        self.summary.setObjectName("Muted")
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ("Archivo", "Estado", "Revisión", "Disciplina", "Número", "Actualizado por", "Fecha")
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setColumnWidth(0, 280)
        layout.addWidget(self.table, 1)
        controller.project_loaded.connect(self._show_documents)
        controller.metadata_saved.connect(lambda _metadata: self.refresh())
        controller.history_loaded.connect(self._history_loaded)
        controller.report_exported.connect(
            lambda path: self.summary.setText(f"Reporte guardado: {path}")
        )
        controller.error_occurred.connect(self.summary.setText)

    def set_project(self, project: Project) -> None:
        self._project = project
        self.refresh()

    def refresh(self) -> None:
        if self._project:
            self._controller.load_project(
                self._project.project_id,
                self.status.currentData(),
                self.search.text().strip(),
            )

    def _show_documents(self, values: object) -> None:
        if not isinstance(values, (tuple, list)):
            return
        self._documents = tuple(value for value in values if isinstance(value, DocumentMetadata))
        self.table.setRowCount(len(self._documents))
        counts = {status: 0 for status in DocumentStatus}
        for row, document in enumerate(self._documents):
            counts[document.status] += 1
            data = (
                document.file_name,
                document.status.label,
                document.revision,
                document.discipline_code or "—",
                document.document_number or "—",
                public_display_name(document.updated_by, "Usuario"),
                relative_time(document.updated_at),
            )
            for column, text in enumerate(data):
                cell = QTableWidgetItem(text)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, document.item_id)
                self.table.setItem(row, column, cell)
            self.table.setRowHeight(row, 42)
        total = len(self._documents)
        breakdown = " · ".join(f"{status.label}: {counts[status]}" for status in DocumentStatus)
        self.summary.setText(f"{total} documentos · {breakdown}")

    def _selected(self) -> DocumentMetadata | None:
        row = self.table.currentRow()
        return self._documents[row] if 0 <= row < len(self._documents) else None

    def _show_history(self) -> None:
        if document := self._selected():
            self._controller.load_history(document.item_id)

    def _history_loaded(self, values: object) -> None:
        if not isinstance(values, (tuple, list)):
            return
        history = tuple(value for value in values if isinstance(value, DocumentHistory))
        if not history:
            return
        lines = []
        for entry in history:
            previous = entry.previous_status.label if entry.previous_status else "Sin registro"
            lines.append(
                f"{entry.occurred_at.astimezone():%d/%m/%Y %H:%M} — "
                f"{public_display_name(entry.actor, 'Usuario')}\n"
                f"{previous} → {entry.new_status.label}; "
                f"{entry.previous_revision or '—'} → {entry.new_revision}"
            )
        QMessageBox.information(self, "Historial documental", "\n\n".join(lines))

    def _export(self) -> None:
        if not self._project:
            return
        default = f"Reporte documental - {self._project.name}.csv"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Guardar reporte documental", default, "CSV (*.csv)"
        )
        if filename:
            self._controller.export_csv(self._project.project_id, Path(filename))
