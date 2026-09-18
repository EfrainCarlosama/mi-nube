from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QImageReader

COVER_WIDTH = 1200
COVER_HEIGHT = 675


def save_project_cover(source: Path, cover_dir: Path, project_id: str) -> Path:
    """Copy and normalize a selected project image into the app's local data directory."""
    reader = QImageReader(str(source))
    reader.setAutoTransform(True)
    image = reader.read()
    if image.isNull():
        raise ValueError("La imagen seleccionada no se pudo abrir.")

    scaled = image.scaled(
        COVER_WIDTH,
        COVER_HEIGHT,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    left = max(0, (scaled.width() - COVER_WIDTH) // 2)
    top = max(0, (scaled.height() - COVER_HEIGHT) // 2)
    normalized: QImage = scaled.copy(left, top, COVER_WIDTH, COVER_HEIGHT)
    cover_dir.mkdir(parents=True, exist_ok=True)
    destination = cover_dir / f"{project_id}.jpg"
    if not normalized.save(str(destination), "JPG", 90):
        raise ValueError("No se pudo guardar la portada del proyecto.")
    return destination


def project_cover_path(cover_dir: Path, project_id: str) -> Path:
    return cover_dir / f"{project_id}.jpg"
