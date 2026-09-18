from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QVBoxLayout, QWidget


class MetricCard(QFrame):
    def __init__(self, title: str, value: str, detail: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(5)
        title_label = QLabel(title)
        title_label.setObjectName("Muted")
        value_label = QLabel(value)
        value_label.setObjectName("Metric")
        detail_label = QLabel(detail)
        detail_label.setObjectName("Muted")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addWidget(detail_label)


class StorageCard(QFrame):
    def __init__(self, used_gb: int, total_gb: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        title = QLabel("Almacenamiento")
        title.setObjectName("Muted")
        value = QLabel(f"{used_gb} GB / {total_gb / 1024:.0f} TB")
        value.setObjectName("Metric")
        bar = QProgressBar()
        bar.setRange(0, total_gb)
        bar.setValue(used_gb)
        bar.setTextVisible(False)
        detail = QLabel(f"{round((used_gb / total_gb) * 100)} % utilizado")
        detail.setObjectName("Muted")
        layout.addWidget(title)
        layout.addWidget(value)
        layout.addWidget(bar)
        layout.addWidget(detail)
