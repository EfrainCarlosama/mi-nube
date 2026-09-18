from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap

_FOLDER_COLORS = (
    "#4F7DF3",
    "#8B6CE7",
    "#E4678A",
    "#2FA88F",
    "#E68A3F",
    "#28A7A1",
    "#6366C7",
    "#2D9CDB",
    "#D97745",
)


def folder_color(name: str) -> str:
    """Return a stable color for a folder name, honoring numbered project folders."""
    prefix = name.strip().split(" ", 1)[0]
    if prefix.isdigit():
        number = int(prefix)
        if number > 0:
            return _FOLDER_COLORS[(number - 1) % len(_FOLDER_COLORS)]
    checksum = sum((index + 1) * ord(character) for index, character in enumerate(name.casefold()))
    return _FOLDER_COLORS[checksum % len(_FOLDER_COLORS)]


def colored_folder_icon(name: str, size: int = 30) -> QIcon:
    """Draw a crisp, colored folder icon without depending on platform theme icons."""
    color = QColor(folder_color(name))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)

    width = float(size)
    tab = QPainterPath()
    tab.addRoundedRect(QRectF(width * 0.10, width * 0.18, width * 0.43, width * 0.27), 3, 3)
    painter.fillPath(tab, color.darker(108))

    body = QPainterPath()
    body.addRoundedRect(QRectF(width * 0.07, width * 0.31, width * 0.86, width * 0.57), 4, 4)
    painter.fillPath(body, color)
    painter.end()
    return QIcon(pixmap)
