from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPainterPath


def main() -> int:
    application = QGuiApplication.instance() or QGuiApplication([])
    output = Path("assets/mi_nube.ico")
    output.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(12, 12, 232, 232), 54, 54)
    painter.fillPath(path, QColor("#4F7DF3"))
    painter.setPen(QColor("#FFFFFF"))
    font = QFont("Segoe UI", 72)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, "MN")
    painter.end()
    if not image.save(str(output), "ICO"):
        raise SystemExit("No se pudo generar el icono de Windows.")
    application.processEvents()
    print(f"Icono generado: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
