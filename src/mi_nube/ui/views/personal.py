from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mi_nube.documents.controller import DocumentController
from mi_nube.domain.identity import public_display_name
from mi_nube.domain.models import DriveItem, DriveQuota, TransferJob, TransferStatus
from mi_nube.graph.controller import DriveController
from mi_nube.sync.controller import SyncController
from mi_nube.transfers.controller import TransferController
from mi_nube.ui.formatters import human_size
from mi_nube.ui.icons import colored_folder_icon
from mi_nube.ui.views.common import page_header
from mi_nube.ui.views.documents import DocumentEditorDialog


class _SortableItem(QTableWidgetItem):
    SORT_ROLE = int(Qt.ItemDataRole.UserRole) + 1

    def __init__(self, text: str, sort_value: object) -> None:
        super().__init__(text)
        self.setData(self.SORT_ROLE, sort_value)

    def __lt__(self, other: QTableWidgetItem) -> bool:
        own_value = self.data(self.SORT_ROLE)
        other_value = other.data(self.SORT_ROLE)
        if own_value is not None and other_value is not None:
            return own_value < other_value
        return super().__lt__(other)


_STATUS_TEXT = {
    TransferStatus.QUEUED: "En cola",
    TransferStatus.RUNNING: "En curso",
    TransferStatus.PAUSED: "Pausada",
    TransferStatus.COMPLETED: "Completada",
    TransferStatus.FAILED: "Falló",
    TransferStatus.CANCELLED: "Cancelada",
}


class _TransferDialog(QDialog):
    def __init__(
        self,
        jobs: tuple[TransferJob, ...],
        controller: TransferController,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._jobs = {job.job_id: job for job in jobs}
        self._controller = controller
        self.setWindowTitle("Transferencias")
        self.resize(760, 430)
        layout = QVBoxLayout(self)
        note = QLabel(
            "La cola continúa una por una. Las transferencias interrumpidas pueden reanudarse."
        )
        note.setObjectName("Muted")
        layout.addWidget(note)
        self.table = QTableWidget(len(jobs), 5)
        self.table.setHorizontalHeaderLabels(("Archivo", "Tipo", "Estado", "Progreso", "Detalle"))
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for row, job in enumerate(jobs):
            percent = round(job.transferred_bytes * 100 / job.total_bytes) if job.total_bytes else 0
            values = (
                job.remote_name,
                "Subida" if job.direction.value == "upload" else "Descarga",
                _STATUS_TEXT[job.status],
                f"{percent} %",
                job.error_message or "",
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, job.job_id)
                self.table.setItem(row, column, cell)
        layout.addWidget(self.table)
        actions = QHBoxLayout()
        retry = QPushButton("Reintentar / reanudar")
        retry.setProperty("primary", True)
        retry.clicked.connect(self._retry)
        cancel = QPushButton("Cancelar y descartar")
        cancel.setProperty("danger", True)
        cancel.clicked.connect(self._cancel)
        actions.addWidget(retry)
        actions.addWidget(cancel)
        actions.addStretch()
        layout.addLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _selected_id(self) -> str | None:
        row = self.table.currentRow()
        cell = self.table.item(row, 0) if row >= 0 else None
        return str(cell.data(Qt.ItemDataRole.UserRole)) if cell else None

    def _retry(self) -> None:
        if job_id := self._selected_id():
            self._controller.retry(job_id)
            self.accept()

    def _cancel(self) -> None:
        if job_id := self._selected_id():
            self._controller.cancel(job_id)
            self.accept()


class PersonalView(QWidget):
    connect_requested = Signal()

    def __init__(
        self,
        controller: DriveController,
        parent: QWidget | None = None,
        *,
        title_text: str = "Personal",
        subtitle_text: str = "Archivos privados de tu cuenta de OneDrive",
        show_connect: bool = True,
        transfer_controller: TransferController | None = None,
        sync_controller: SyncController | None = None,
        document_controller: DocumentController | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._transfer_controller = transfer_controller
        self._sync_controller = sync_controller
        self._document_controller = document_controller
        self._document_project_id: str | None = None
        self._activity_scope_id = "drive:personal"
        self._activity_project_name: str | None = None
        self._pending_activity: tuple[str, str] | None = None
        self._transfer_activity: dict[str, tuple[str, str]] = {}
        self._transfer_jobs: tuple[TransferJob, ...] = ()
        self._active_transfer_id: str | None = None
        self._items: tuple[DriveItem, ...] = ()
        self._items_by_id: dict[str, DriveItem] = {}
        self._folder_stack: list[tuple[str | None, str]] = [(None, "Mi OneDrive")]
        self._pending_move: DriveItem | None = None
        self._search_mode = False
        self._upload_active = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 26, 36, 28)
        layout.setSpacing(14)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        title, subtitle = page_header(title_text, subtitle_text)
        heading.addWidget(title)
        heading.addWidget(subtitle)
        header.addLayout(heading)
        header.addStretch()
        self._quota = QLabel("Almacenamiento: conecta OneDrive para consultar")
        self._quota.setObjectName("Muted")
        header.addWidget(self._quota)
        layout.addLayout(header)

        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setObjectName("SearchInput")
        self._search.setPlaceholderText("Buscar en todo OneDrive...")
        self._search.returnPressed.connect(self._start_search)
        search_button = QPushButton("Buscar")
        search_button.setProperty("secondary", True)
        search_button.clicked.connect(self._start_search)
        self._clear_search_button = QPushButton("Volver a carpeta")
        self._clear_search_button.setProperty("secondary", True)
        self._clear_search_button.clicked.connect(self._clear_search)
        self._clear_search_button.hide()
        self._connect_button = QPushButton("Conectar OneDrive")
        self._connect_button.setProperty("primary", True)
        self._connect_button.clicked.connect(self.connect_requested.emit)
        self._connect_button.setVisible(show_connect)
        search_row.addWidget(self._search, 1)
        search_row.addWidget(search_button)
        search_row.addWidget(self._clear_search_button)
        search_row.addWidget(self._connect_button)
        layout.addLayout(search_row)

        navigation = QHBoxLayout()
        self._back_button = QPushButton("← Atrás")
        self._back_button.setProperty("secondary", True)
        self._back_button.clicked.connect(self._go_back)
        self._path_label = QLabel("Mi OneDrive")
        self._path_label.setStyleSheet("font-weight: 600; color: #344054;")
        self._status_label = QLabel("Pulsa Conectar OneDrive y luego Actualizar.")
        self._status_label.setObjectName("Muted")
        navigation.addWidget(self._back_button)
        navigation.addWidget(self._path_label)
        navigation.addStretch()
        navigation.addWidget(self._status_label)
        layout.addLayout(navigation)

        transfer_row = QHBoxLayout()
        self._transfer_label = QLabel()
        self._transfer_label.setObjectName("Muted")
        self._transfer_progress = QProgressBar()
        self._transfer_progress.setRange(0, 100)
        self._transfer_progress.setTextVisible(True)
        self._transfer_progress.setMinimumWidth(260)
        self._transfer_progress.setMinimumHeight(24)
        self._cancel_upload_button = QPushButton(
            "Pausar transferencia" if transfer_controller else "Cancelar subida"
        )
        self._cancel_upload_button.setProperty("danger", True)
        self._cancel_upload_button.clicked.connect(self._cancel_upload)
        for widget in (
            self._transfer_label,
            self._transfer_progress,
            self._cancel_upload_button,
        ):
            widget.hide()
        transfer_row.addWidget(self._transfer_label)
        transfer_row.addWidget(self._transfer_progress, 1)
        transfer_row.addWidget(self._cancel_upload_button)
        self._queue_button = QPushButton("Transferencias")
        self._queue_button.setProperty("secondary", True)
        self._queue_button.clicked.connect(self._show_transfer_queue)
        self._queue_button.setVisible(transfer_controller is not None)
        transfer_row.addWidget(self._queue_button)
        layout.addLayout(transfer_row)

        actions = QHBoxLayout()
        self._refresh_button = self._action_button("Actualizar", self._refresh)
        self._folder_button = self._action_button("Nueva carpeta", self._new_folder)
        self._upload_button = self._action_button("Subir archivo", self._upload)
        self._download_button = self._action_button("Descargar", self._download)
        self._rename_button = self._action_button("Renombrar", self._rename)
        self._move_button = self._action_button("Mover", self._prepare_move)
        self._move_here_button = self._action_button("Mover aquí", self._move_here)
        self._move_here_button.setProperty("primary", True)
        self._move_here_button.hide()
        self._info_button = self._action_button("Información", self._show_info)
        self._document_button = self._action_button("Estado y revisión", self._edit_document)
        self._document_button.setVisible(document_controller is not None)
        self._delete_button = self._action_button("Eliminar", self._delete)
        self._delete_button.setProperty("danger", True)
        for button in (
            self._refresh_button,
            self._folder_button,
            self._upload_button,
            self._download_button,
            self._rename_button,
            self._move_button,
            self._move_here_button,
            self._info_button,
            self._document_button,
            self._delete_button,
        ):
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ("Nombre", "Tipo", "Tamaño", "Modificado", "Modificado por", "Estado")
        )
        self._table.setIconSize(QSize(30, 30))
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setColumnWidth(0, 270)
        self._table.setColumnWidth(1, 100)
        self._table.setColumnWidth(2, 100)
        self._table.setColumnWidth(3, 145)
        self._table.setColumnWidth(4, 150)
        self._table.setColumnWidth(5, 110)
        self._table.horizontalHeader().setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        self._table.setSortingEnabled(True)
        self._table.itemSelectionChanged.connect(self._update_action_state)
        self._table.cellDoubleClicked.connect(self._open_row)
        layout.addWidget(self._table, 1)

        controller.browser_loaded.connect(self._show_browser)
        controller.items_loaded.connect(self._show_items)
        controller.item_info_loaded.connect(self._show_item_dialog)
        controller.operation_succeeded.connect(self._operation_completed)
        controller.download_succeeded.connect(self._download_completed)
        controller.error_occurred.connect(self._show_error)
        controller.busy_changed.connect(self._set_busy)
        if transfer_controller:
            transfer_controller.jobs_changed.connect(self._transfer_jobs_changed)
            transfer_controller.job_started.connect(self._transfer_started)
            transfer_controller.job_progress.connect(self._transfer_job_progress)
            transfer_controller.operation_succeeded.connect(self._transfer_completed)
            transfer_controller.job_completed.connect(self._transfer_job_completed)
            transfer_controller.error_occurred.connect(self._show_error)
            transfer_controller.refresh()
        else:
            controller.upload_started.connect(self._upload_started)
            controller.upload_progress.connect(self._upload_progress)
            controller.upload_cancelled.connect(self._upload_cancelled)
            controller.upload_finished.connect(self._upload_finished)
        if document_controller:
            document_controller.metadata_saved.connect(self._document_saved)
            document_controller.error_occurred.connect(self._show_error)
        self._update_navigation()
        self._update_action_state()

    @staticmethod
    def _action_button(text: str, callback) -> QPushButton:
        button = QPushButton(text)
        button.setProperty("secondary", True)
        button.clicked.connect(callback)
        return button

    @property
    def current_folder_id(self) -> str | None:
        return self._folder_stack[-1][0]

    def set_root(self, item_id: str | None, label: str) -> None:
        self._folder_stack = [(item_id, label)]
        self._search_mode = False
        self._search.clear()
        self._clear_search_button.hide()
        self._items = ()
        self._items_by_id = {}
        self._table.setRowCount(0)
        self._update_navigation()
        self._update_action_state()

    def set_activity_scope(self, scope_id: str, project_name: str | None = None) -> None:
        self._activity_scope_id = scope_id
        self._activity_project_name = project_name

    def set_document_project(self, project_id: str | None) -> None:
        self._document_project_id = project_id
        self._document_button.setVisible(
            self._document_controller is not None and project_id is not None
        )

    def _record_local(self, action: str, target: str) -> None:
        if self._sync_controller:
            self._sync_controller.record_local(
                action,
                target,
                scope_id=self._activity_scope_id,
                project_name=self._activity_project_name,
            )

    def load_root(self) -> None:
        self._refresh()

    def _selected_item(self) -> DriveItem | None:
        row = self._table.currentRow()
        name_cell = self._table.item(row, 0) if row >= 0 else None
        item_id = name_cell.data(Qt.ItemDataRole.UserRole) if name_cell else None
        return self._items_by_id.get(str(item_id)) if item_id else None

    def _refresh(self) -> None:
        self._search_mode = False
        self._clear_search_button.hide()
        self._controller.refresh(self.current_folder_id)

    def _refresh_current(self) -> None:
        if self._search_mode and self._search.text().strip():
            self._controller.search(self._search.text())
        else:
            self._controller.refresh(self.current_folder_id)

    def _start_search(self) -> None:
        query = self._search.text().strip()
        if not query:
            self._show_error("Escribe un término para buscar.")
            return
        self._search_mode = True
        self._clear_search_button.show()
        self._path_label.setText(f"Resultados para “{query}”")
        self._controller.search(query)

    def _clear_search(self) -> None:
        self._search.clear()
        self._search_mode = False
        self._clear_search_button.hide()
        self._update_navigation()
        self._controller.refresh(self.current_folder_id)

    def _new_folder(self) -> None:
        name, accepted = QInputDialog.getText(self, "Nueva carpeta", "Nombre de la carpeta:")
        if accepted and name.strip():
            self._pending_activity = ("creó", name.strip())
            self._controller.create_folder(self.current_folder_id, name)

    def _upload(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Seleccionar archivo para subir")
        if filename:
            if self._transfer_controller:
                job = self._transfer_controller.enqueue_upload(
                    self.current_folder_id, Path(filename)
                )
                if job:
                    self._transfer_activity[job.job_id] = ("subió", job.remote_name)
            else:
                self._pending_activity = ("subió", Path(filename).name)
                self._controller.upload(self.current_folder_id, Path(filename))

    def _cancel_upload(self) -> None:
        self._cancel_upload_button.setEnabled(False)
        self._status_label.setText("Cancelando la subida...")
        if self._transfer_controller:
            self._transfer_controller.pause_active()
        else:
            self._controller.cancel_upload()

    def _show_transfer_queue(self) -> None:
        if self._transfer_controller:
            _TransferDialog(self._transfer_jobs, self._transfer_controller, self).exec()

    def _transfer_jobs_changed(self, jobs: object) -> None:
        if not isinstance(jobs, (tuple, list)):
            return
        self._transfer_jobs = tuple(job for job in jobs if isinstance(job, TransferJob))
        pending = sum(
            job.status in {TransferStatus.QUEUED, TransferStatus.RUNNING, TransferStatus.PAUSED}
            for job in self._transfer_jobs
        )
        self._queue_button.setText(f"Transferencias ({pending})" if pending else "Transferencias")
        active = next(
            (job for job in self._transfer_jobs if job.status == TransferStatus.RUNNING), None
        )
        if active is None:
            self._active_transfer_id = None
            self._upload_finished()

    def _transfer_started(self, job: object) -> None:
        if not isinstance(job, TransferJob):
            return
        self._active_transfer_id = job.job_id
        self._upload_active = True
        action = "Subiendo" if job.direction.value == "upload" else "Descargando"
        self._transfer_label.setText(f"{action} {job.remote_name}")
        self._transfer_progress.setValue(0)
        self._transfer_progress.setFormat(
            f"{human_size(job.transferred_bytes)} / {human_size(job.total_bytes)}"
        )
        self._cancel_upload_button.setEnabled(True)
        self._transfer_label.show()
        self._transfer_progress.show()
        self._cancel_upload_button.show()

    def _transfer_job_progress(self, job_id: str, transferred: int, total: int) -> None:
        if job_id == self._active_transfer_id:
            self._upload_progress(transferred, total)

    def _transfer_completed(self, message: str) -> None:
        self._status_label.setText(message)
        self._refresh_current()

    def _transfer_job_completed(self, job: object) -> None:
        if not isinstance(job, TransferJob):
            return
        activity = self._transfer_activity.pop(job.job_id, None)
        if activity:
            self._record_local(*activity)

    def _upload_started(self, filename: str, total: int) -> None:
        self._upload_active = True
        self._transfer_label.setText(f"Subiendo {filename}")
        self._transfer_progress.setValue(0)
        self._transfer_progress.setFormat(f"0 B / {human_size(total)} — 0 %")
        self._cancel_upload_button.setEnabled(True)
        self._transfer_label.show()
        self._transfer_progress.show()
        self._cancel_upload_button.show()

    def _upload_progress(self, transferred: int, total: int) -> None:
        percentage = min(100, round((transferred / total) * 100)) if total else 100
        self._transfer_progress.setValue(percentage)
        self._transfer_progress.setFormat(
            f"{human_size(transferred)} / {human_size(total)} — {percentage} %"
        )

    def _upload_cancelled(self, message: str) -> None:
        self._status_label.setText(message)

    def _upload_finished(self) -> None:
        self._upload_active = False
        self._transfer_label.hide()
        self._transfer_progress.hide()
        self._cancel_upload_button.hide()

    def _download(self) -> None:
        item = self._selected_item()
        if item is None or item.is_folder:
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Guardar archivo", item.name)
        if filename:
            if self._transfer_controller:
                job = self._transfer_controller.enqueue_download(
                    item.item_id, item.name, item.size_bytes, Path(filename)
                )
                self._transfer_activity[job.job_id] = ("descargó", item.name)
            else:
                self._pending_activity = ("descargó", item.name)
                self._controller.download(item.item_id, Path(filename))

    def _rename(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        name, accepted = QInputDialog.getText(
            self,
            "Renombrar",
            "Nuevo nombre:",
            text=item.name,
        )
        if accepted and name.strip() and name.strip() != item.name:
            self._pending_activity = ("renombró", name.strip())
            self._controller.rename(item.item_id, name, item.etag)

    def _prepare_move(self) -> None:
        if self._pending_move is not None:
            self._pending_move = None
            self._move_here_button.hide()
            self._move_button.setText("Mover")
            self._status_label.setText("Movimiento cancelado.")
            return
        item = self._selected_item()
        if item is None:
            return
        self._pending_move = item
        self._move_here_button.show()
        self._move_button.setText("Cancelar mover")
        self._status_label.setText(
            f"Moviendo “{item.name}”: abre la carpeta de destino y pulsa Mover aquí."
        )

    def _move_here(self) -> None:
        item = self._pending_move
        if item is None:
            return
        if item.is_folder and item.item_id == self.current_folder_id:
            self._show_error("No puedes mover una carpeta dentro de sí misma.")
            return
        self._pending_activity = ("movió", item.name)
        self._controller.move(item.item_id, self.current_folder_id)

    def _delete(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        answer = QMessageBox.question(
            self,
            "Enviar a la papelera",
            f"¿Quieres enviar “{item.name}” a la papelera de OneDrive?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._pending_activity = ("eliminó", item.name)
            self._controller.delete(item.item_id, item.etag)

    def _show_info(self) -> None:
        item = self._selected_item()
        if item:
            self._controller.load_info(item.item_id)

    def _edit_document(self) -> None:
        item = self._selected_item()
        if (
            item is None
            or item.is_folder
            or self._document_controller is None
            or self._document_project_id is None
        ):
            return
        metadata = self._document_controller.get(item.item_id)
        dialog = DocumentEditorDialog(item, metadata, self._document_controller, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._document_controller.save(
            self._document_project_id,
            item,
            status=dialog.status.currentData(),
            revision=dialog.revision.text(),
            naming_enabled=dialog.naming.isChecked(),
            discipline_code=dialog.discipline.text(),
            document_number=dialog.number.text(),
            title=dialog.title.text(),
            rename_remote=dialog.rename_remote.isChecked(),
        )

    def _document_saved(self, metadata: object) -> None:
        self._status_label.setText("Estado y revisión guardados correctamente.")
        self._refresh_current()

    def _open_row(self, row: int, _column: int) -> None:
        name_cell = self._table.item(row, 0)
        item_id = name_cell.data(Qt.ItemDataRole.UserRole) if name_cell else None
        item = self._items_by_id.get(str(item_id)) if item_id else None
        if item is None:
            return
        if not item.is_folder:
            self._show_item_dialog(item)
            return
        self._folder_stack.append((item.item_id, item.name))
        self._search_mode = False
        self._clear_search_button.hide()
        self._update_navigation()
        self._controller.refresh(item.item_id)

    def _go_back(self) -> None:
        if self._search_mode:
            self._clear_search()
            return
        if len(self._folder_stack) > 1:
            self._folder_stack.pop()
            self._update_navigation()
            self._controller.refresh(self.current_folder_id)

    def _update_navigation(self) -> None:
        self._path_label.setText(" / ".join(name for _, name in self._folder_stack))
        self._back_button.setEnabled(len(self._folder_stack) > 1 or self._search_mode)

    def _show_browser(self, items: object, quota: object) -> None:
        self._show_items(items)
        if isinstance(quota, DriveQuota):
            self._quota.setText(
                f"Almacenamiento: {human_size(quota.used_bytes)} / {human_size(quota.total_bytes)}"
            )

    def _show_items(self, items: object) -> None:
        if not isinstance(items, (tuple, list)):
            return
        self._items = tuple(item for item in items if isinstance(item, DriveItem))
        self._items_by_id = {item.item_id: item for item in self._items}
        metadata_by_id = {}
        if self._document_controller and self._document_project_id:
            metadata_by_id = {
                value.item_id: value
                for value in self._document_controller.list_project(self._document_project_id)
            }
        sorting_enabled = self._table.isSortingEnabled()
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(self._items))
        for row, item in enumerate(self._items):
            kind = self._display_type(item)
            size = "—" if item.is_folder else human_size(item.size_bytes)
            modified_text = self._format_datetime(item.modified_at)
            metadata = metadata_by_id.get(item.item_id)
            state = metadata.status.label if metadata else "—"
            modified_by = public_display_name(item.modified_by, "Usuario")
            values = (
                (item.name, item.name.casefold()),
                (kind, kind.casefold()),
                (size, item.size_bytes if not item.is_folder else -1),
                (modified_text, item.modified_at.timestamp() if item.modified_at else 0),
                (modified_by, modified_by.casefold()),
                (state, state.casefold()),
            )
            for column, (text, sort_value) in enumerate(values):
                cell = _SortableItem(text, sort_value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, item.item_id)
                    if item.is_folder:
                        cell.setIcon(colored_folder_icon(item.name))
                self._table.setItem(row, column, cell)
            self._table.setRowHeight(row, 50)
        self._table.setSortingEnabled(sorting_enabled)
        self._table.clearSelection()
        count = len(self._items)
        self._status_label.setText(f"{count} elemento" if count == 1 else f"{count} elementos")
        self._update_action_state()

    @staticmethod
    def _format_datetime(value: datetime | None) -> str:
        if value is None:
            return "—"
        try:
            return value.astimezone().strftime("%d/%m/%Y %H:%M")
        except ValueError:
            return value.strftime("%d/%m/%Y %H:%M")

    @staticmethod
    def _display_type(item: DriveItem) -> str:
        if item.is_folder:
            return "Carpeta"
        extension = Path(item.name).suffix.removeprefix(".").upper()
        return extension or item.mime_type or "Archivo"

    @staticmethod
    def _display_path(parent_path: str) -> str:
        relative = parent_path.removeprefix("/drive/root:").strip("/")
        return f"Mi OneDrive/{relative}" if relative else "Mi OneDrive"

    @classmethod
    def _display_item_path(cls, item: DriveItem) -> str:
        return f"{cls._display_path(item.parent_path)}/{item.name}"

    def _show_item_dialog(self, item: object) -> None:
        if not isinstance(item, DriveItem):
            return
        details = (
            f"Nombre: {item.name}\n"
            f"Tipo: {self._display_type(item)}\n"
            f"Tamaño: {'—' if item.is_folder else human_size(item.size_bytes)}\n"
            f"Modificado: {self._format_datetime(item.modified_at)}\n"
            f"Modificado por: {public_display_name(item.modified_by, 'Usuario')}\n"
            f"Ruta completa: {self._display_item_path(item)}"
        )
        QMessageBox.information(self, "Información del elemento", details)

    def _operation_completed(self, message: str) -> None:
        if self._pending_activity:
            self._record_local(*self._pending_activity)
            self._pending_activity = None
        self._pending_move = None
        self._move_here_button.hide()
        self._move_button.setText("Mover")
        self._status_label.setText(message)
        self._refresh_current()

    def _download_completed(self, path: str) -> None:
        if self._pending_activity:
            self._record_local(*self._pending_activity)
            self._pending_activity = None
        self._status_label.setText(f"Descarga completada: {path}")

    def _show_error(self, message: str) -> None:
        self._pending_activity = None
        self._status_label.setText(message)
        QMessageBox.warning(self, "OneDrive", message)

    def _set_busy(self, busy: bool) -> None:
        self._table.setEnabled(not busy)
        self._refresh_button.setEnabled(not busy)
        self._folder_button.setEnabled(not busy and not self._search_mode)
        self._upload_button.setEnabled(not busy and not self._search_mode)
        self._connect_button.setEnabled(not busy)
        self._move_here_button.setEnabled(not busy)
        self._cancel_upload_button.setEnabled(self._upload_active)
        if busy:
            if self._upload_active:
                self._status_label.setText("Subiendo archivo a OneDrive...")
            else:
                self._status_label.setText("Comunicándose con OneDrive...")
        self._update_action_state()

    def _update_action_state(self) -> None:
        selected = self._selected_item()
        enabled = selected is not None and self._table.isEnabled()
        self._download_button.setEnabled(enabled and not selected.is_folder if selected else False)
        self._rename_button.setEnabled(enabled)
        self._move_button.setEnabled(enabled)
        self._info_button.setEnabled(enabled)
        self._document_button.setEnabled(enabled and not selected.is_folder if selected else False)
        self._delete_button.setEnabled(enabled)

    def set_connected(self, connected: bool) -> None:
        self._connect_button.setText("Renovar acceso" if connected else "Conectar OneDrive")
        if connected and not self._items:
            self._status_label.setText(
                "Sesión conectada. Pulsa Actualizar para cargar tus archivos."
            )
