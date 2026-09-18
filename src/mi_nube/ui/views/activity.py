from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mi_nube.domain.identity import public_display_name
from mi_nube.domain.models import ActivityEvent, SyncScope, SyncSummary
from mi_nube.services.mock_data import MockDataService
from mi_nube.sync.controller import SyncController
from mi_nube.ui.formatters import relative_time
from mi_nube.ui.views.common import page_header


class ActivityView(QWidget):
    def __init__(
        self,
        source: SyncController | MockDataService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = source if isinstance(source, SyncController) else None
        self._scopes: tuple[SyncScope, ...] = ()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 30, 36, 30)
        layout.setSpacing(16)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        title, subtitle = page_header(
            "Actividad", "Cambios incrementales detectados en OneDrive y acciones de Mi Nube"
        )
        heading.addWidget(title)
        heading.addWidget(subtitle)
        header.addLayout(heading)
        header.addStretch()
        self._sync_button = QPushButton("Sincronizar ahora")
        self._sync_button.setProperty("primary", True)
        self._sync_button.clicked.connect(self._sync)
        header.addWidget(self._sync_button)
        layout.addLayout(header)

        filters = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setObjectName("SearchInput")
        self._search.setPlaceholderText("Buscar archivo, acción o persona...")
        self._search.textChanged.connect(self._reload)
        self._scope = QComboBox()
        self._scope.addItem("Todos los espacios", None)
        self._scope.currentIndexChanged.connect(self._reload)
        self._status = QLabel("Sincronización automática cada 5 minutos")
        self._status.setObjectName("Muted")
        filters.addWidget(self._search, 1)
        filters.addWidget(self._scope)
        filters.addStretch()
        filters.addWidget(self._status)
        layout.addLayout(filters)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ("Cuándo", "Quién", "Acción", "Elemento", "Espacio", "Origen")
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setColumnWidth(0, 150)
        self._table.setColumnWidth(1, 170)
        self._table.setColumnWidth(2, 110)
        self._table.setColumnWidth(3, 260)
        self._table.setColumnWidth(4, 170)
        layout.addWidget(self._table, 1)

        if self._controller:
            self._controller.activity_loaded.connect(self._show_activity)
            self._controller.scopes_loaded.connect(self._show_scopes)
            self._controller.sync_completed.connect(self._sync_completed)
            self._controller.error_occurred.connect(self._show_error)
            self._controller.busy_changed.connect(self._set_busy)
        else:
            events = tuple(
                ActivityEvent(
                    event_id=f"mock-{index}",
                    source="local",
                    action=item.action,
                    actor=item.actor,
                    target=item.target,
                    scope_id="drive:personal",
                    project_name=item.project,
                    remote_item_id=None,
                    occurred_at=item.occurred_at,
                )
                for index, item in enumerate(source.recent_activity())
            )
            self._show_activity(events)
            self._sync_button.setEnabled(False)

    def activate(self) -> None:
        self._reload()

    def _sync(self) -> None:
        if self._controller:
            self._controller.sync_now()

    def _reload(self) -> None:
        if self._controller:
            self._controller.load_activity(self._scope.currentData(), self._search.text().strip())

    def _show_scopes(self, scopes: object) -> None:
        if not isinstance(scopes, (tuple, list)):
            return
        values = tuple(scope for scope in scopes if isinstance(scope, SyncScope))
        if values == self._scopes:
            return
        selected = self._scope.currentData()
        self._scopes = values
        self._scope.blockSignals(True)
        self._scope.clear()
        self._scope.addItem("Todos los espacios", None)
        for scope in values:
            self._scope.addItem(scope.label, scope.scope_id)
        index = self._scope.findData(selected)
        self._scope.setCurrentIndex(max(index, 0))
        self._scope.blockSignals(False)

    def _show_activity(self, events: object) -> None:
        if not isinstance(events, (tuple, list)):
            return
        items = tuple(event for event in events if isinstance(event, ActivityEvent))
        self._table.setRowCount(len(items))
        for row, event in enumerate(items):
            origin = {
                "graph": "OneDrive",
                "local": "Mi Nube",
                "local+graph": "Confirmado",
            }.get(event.source, event.source)
            values = (
                relative_time(event.occurred_at),
                public_display_name(event.actor, "Usuario"),
                event.action.capitalize(),
                event.target,
                event.project_name or "Personal",
                origin,
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column in {0, 2, 5}:
                    cell.setTextAlignment(
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                    )
                self._table.setItem(row, column, cell)
            self._table.setRowHeight(row, 42)
        if not items:
            self._status.setText("Todavía no hay cambios registrados")

    def _sync_completed(self, summary: object) -> None:
        if not isinstance(summary, SyncSummary):
            return
        if summary.baselines_created:
            self._status.setText(
                f"Línea base creada en {summary.baselines_created} espacio(s); "
                "los próximos cambios aparecerán aquí."
            )
        else:
            self._status.setText(
                f"Sincronizado: {summary.changes_received} cambios, "
                f"{summary.events_created} eventos nuevos."
            )

    def _show_error(self, message: str) -> None:
        self._status.setText(message)

    def _set_busy(self, busy: bool) -> None:
        self._sync_button.setEnabled(not busy)
        self._sync_button.setText("Sincronizando..." if busy else "Sincronizar ahora")
