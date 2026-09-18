from __future__ import annotations

from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from mi_nube.domain.identity import public_display_name
from mi_nube.services.mock_data import MockDataService
from mi_nube.ui.components.cards import MetricCard, StorageCard
from mi_nube.ui.formatters import relative_time
from mi_nube.ui.views.common import page_header


class HomeView(QWidget):
    def __init__(self, data_service: MockDataService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        projects = data_service.projects()
        activity = data_service.recent_activity()
        storage = data_service.storage()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 30, 36, 30)
        layout.setSpacing(22)
        self._title, subtitle = page_header("Buenos días", "Un resumen de tu espacio de trabajo")
        layout.addWidget(self._title)
        layout.addWidget(subtitle)

        metrics = QHBoxLayout()
        metrics.setSpacing(14)
        metrics.addWidget(
            MetricCard("Proyectos activos", str(len(projects)), "2 actualizados esta semana")
        )
        metrics.addWidget(MetricCard("Archivos", "607", "En todos tus proyectos"))
        metrics.addWidget(
            StorageCard(storage.used_bytes // 1024**3, storage.total_bytes // 1024**3)
        )
        layout.addLayout(metrics)

        content = QGridLayout()
        content.setHorizontalSpacing(14)
        content.setVerticalSpacing(14)
        projects_card = self._card("Proyectos recientes")
        projects_layout = projects_card.layout()
        for project in projects:
            row = QHBoxLayout()
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {project.accent}; font-size: 16px;")
            name = QLabel(f"{project.name}\n{project.client}")
            name.setStyleSheet("font-weight: 600; line-height: 1.3;")
            when = QLabel(relative_time(project.modified_at))
            when.setObjectName("Muted")
            row.addWidget(dot)
            row.addWidget(name, 1)
            row.addWidget(when)
            projects_layout.addLayout(row)

        activity_card = self._card("Actividad reciente")
        activity_layout = activity_card.layout()
        for item in activity[:3]:
            actor = public_display_name(item.actor, "Usuario")
            text = QLabel(f"<b>{actor}</b> {item.action} {item.target}")
            text.setTextFormat(text.textFormat().RichText)
            text.setWordWrap(True)
            when = QLabel(f"{item.project} · {relative_time(item.occurred_at)}")
            when.setObjectName("Muted")
            activity_layout.addWidget(text)
            activity_layout.addWidget(when)

        content.addWidget(projects_card, 0, 0)
        content.addWidget(activity_card, 0, 1)
        content.setColumnStretch(0, 1)
        content.setColumnStretch(1, 1)
        layout.addLayout(content)
        layout.addStretch()

    def set_owner(self, display_name: str | None) -> None:
        """Personalize the greeting without ever rendering an email address."""
        if display_name:
            self._title.setText(f"Buenos días, {public_display_name(display_name, 'Propietario')}")
        else:
            self._title.setText("Buenos días")

    @staticmethod
    def _card(title: str) -> QFrame:
        card = QFrame()
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(13)
        heading = QLabel(title)
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)
        return card
