from __future__ import annotations

from datetime import datetime, timedelta

from mi_nube.domain.models import ActivityItem, FileItem, ProjectSummary, StorageSummary


class MockDataService:
    """Provides deterministic local data while Graph is intentionally disconnected."""

    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime.now()

    def storage(self) -> StorageSummary:
        gib = 1024**3
        return StorageSummary(used_bytes=318 * gib, total_bytes=1024 * gib)

    def projects(self) -> tuple[ProjectSummary, ...]:
        return (
            ProjectSummary(
                "p-carlos",
                "Residencia Carlos",
                "Sr. Carlos",
                self._now - timedelta(hours=2),
                184,
                "#4F7DF3",
            ),
            ProjectSummary(
                "p-orion",
                "Edificio Orión",
                "Constructora Norte",
                self._now - timedelta(days=1),
                327,
                "#8B6CE7",
            ),
            ProjectSummary(
                "p-lago",
                "Casa del Lago",
                "Familia Andrade",
                self._now - timedelta(days=3),
                96,
                "#2FA88F",
            ),
        )

    def recent_activity(self) -> tuple[ActivityItem, ...]:
        return (
            ActivityItem(
                "Juan",
                "subió",
                "EST-004-R03.dwg",
                self._now - timedelta(minutes=18),
                "Residencia Carlos",
            ),
            ActivityItem(
                "Efraín",
                "modificó",
                "PRESUPUESTO.xlsx",
                self._now - timedelta(minutes=35),
                "Edificio Orión",
            ),
            ActivityItem(
                "Ana",
                "creó",
                "Arquitectura/Detalles",
                self._now - timedelta(hours=1, minutes=10),
                "Casa del Lago",
            ),
            ActivityItem(
                "Efraín",
                "aprobó",
                "ARQ-001-R04.pdf",
                self._now - timedelta(hours=3),
                "Residencia Carlos",
            ),
        )

    def personal_items(self) -> tuple[FileItem, ...]:
        return (
            FileItem(
                "Documentos",
                "Carpeta",
                None,
                self._now - timedelta(hours=4),
                "/Personal/Documentos",
            ),
            FileItem(
                "Fotografías",
                "Carpeta",
                None,
                self._now - timedelta(days=1),
                "/Personal/Fotografías",
            ),
            FileItem(
                "Certificado-profesional.pdf",
                "PDF",
                2_430_000,
                self._now - timedelta(days=2),
                "/Personal/Certificado-profesional.pdf",
                "Aprobado",
            ),
            FileItem(
                "Notas-proyecto.docx",
                "DOCX",
                845_000,
                self._now - timedelta(days=5),
                "/Personal/Notas-proyecto.docx",
                "Borrador",
            ),
        )
