from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


def page_header(title: str, subtitle: str) -> tuple[QLabel, QLabel]:
    title_label = QLabel(title)
    title_label.setObjectName("PageTitle")
    subtitle_label = QLabel(subtitle)
    subtitle_label.setObjectName("PageSubtitle")
    return title_label, subtitle_label


class PlaceholderView(QWidget):
    def __init__(
        self, title: str, subtitle: str, message: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 30, 36, 30)
        title_label, subtitle_label = page_header(title, subtitle)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addStretch(1)
        symbol = QLabel("◇")
        symbol.setAlignment(Qt.AlignmentFlag.AlignCenter)
        symbol.setStyleSheet("color: #4F7DF3; font-size: 42px;")
        text = QLabel(message)
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setStyleSheet("color: #667085; font-size: 15px;")
        text.setWordWrap(True)
        layout.addWidget(symbol)
        layout.addWidget(text)
        layout.addStretch(2)
