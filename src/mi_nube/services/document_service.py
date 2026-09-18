from __future__ import annotations

import csv
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from mi_nube.documents.errors import DocumentValidationError
from mi_nube.domain.models import (
    DocumentHistory,
    DocumentMetadata,
    DocumentReport,
    DocumentStatus,
    DriveItem,
)
from mi_nube.graph.ports import GraphDriveClient
from mi_nube.repositories.document_repository import SqliteDocumentRepository

_DISCIPLINE_PATTERN = re.compile(r"^[A-Z0-9]{2,8}$")
_REVISION_PATTERN = re.compile(r"^R?(\d{1,3})$", re.IGNORECASE)
_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class DocumentService:
    def __init__(
        self,
        client: GraphDriveClient,
        repository: SqliteDocumentRepository,
        actor_provider: Callable[[], str],
    ) -> None:
        self._client = client
        self._repository = repository
        self._actor_provider = actor_provider

    @staticmethod
    def normalize_revision(value: str) -> str:
        match = _REVISION_PATTERN.fullmatch(value.strip())
        if not match:
            raise DocumentValidationError("La revisión debe tener formato R01, R02, R10, etc.")
        number = int(match.group(1))
        return f"R{number:02d}"

    @staticmethod
    def normalize_discipline(value: str) -> str:
        code = value.strip().upper()
        if not _DISCIPLINE_PATTERN.fullmatch(code):
            raise DocumentValidationError(
                "La disciplina debe contener entre 2 y 8 letras o números, por ejemplo ARQ."
            )
        return code

    @staticmethod
    def normalize_number(value: str) -> str:
        cleaned = value.strip()
        if not cleaned.isdigit() or not 1 <= int(cleaned) <= 999999:
            raise DocumentValidationError("El número documental debe estar entre 1 y 999999.")
        return cleaned.zfill(3)

    @staticmethod
    def normalize_title(value: str) -> str | None:
        cleaned = _INVALID_FILENAME.sub("", value.strip())
        cleaned = re.sub(r"\s+", "-", cleaned).strip(" .-")
        return cleaned[:80] or None

    @classmethod
    def build_name(
        cls,
        original_name: str,
        discipline_code: str,
        document_number: str,
        revision: str,
        title: str = "",
    ) -> str:
        discipline = cls.normalize_discipline(discipline_code)
        number = cls.normalize_number(document_number)
        normalized_revision = cls.normalize_revision(revision)
        normalized_title = cls.normalize_title(title)
        extension = Path(original_name).suffix
        stem = f"{discipline}-{number}-{normalized_revision}"
        if normalized_title:
            stem = f"{stem}-{normalized_title}"
        return f"{stem}{extension}"

    def get(self, item_id: str) -> DocumentMetadata | None:
        return self._repository.get(item_id)

    def list_project(
        self,
        project_id: str,
        status: DocumentStatus | None = None,
        search: str = "",
    ) -> tuple[DocumentMetadata, ...]:
        return self._repository.list_project(project_id, status=status, search=search)

    def list_history(self, item_id: str) -> tuple[DocumentHistory, ...]:
        return self._repository.list_history(item_id)

    def save(
        self,
        project_id: str,
        item: DriveItem,
        *,
        status: DocumentStatus,
        revision: str,
        naming_enabled: bool,
        discipline_code: str = "",
        document_number: str = "",
        title: str = "",
        rename_remote: bool = False,
    ) -> DocumentMetadata:
        if item.is_folder:
            raise DocumentValidationError("Los estados documentales se aplican solo a archivos.")
        normalized_revision = self.normalize_revision(revision)
        discipline = number = normalized_title = None
        desired_name = item.name
        if naming_enabled:
            discipline = self.normalize_discipline(discipline_code)
            number = self.normalize_number(document_number)
            normalized_title = self.normalize_title(title)
            desired_name = self.build_name(
                item.name, discipline, number, normalized_revision, normalized_title or ""
            )

        remote_item = item
        if rename_remote and desired_name != item.name:
            remote_item = self._client.rename_item(item.item_id, desired_name, item.etag)

        previous = self._repository.get(item.item_id)
        now = datetime.now(UTC)
        actor = self._actor_provider() or "Propietario"
        metadata = DocumentMetadata(
            item_id=item.item_id,
            project_id=project_id,
            file_name=remote_item.name,
            status=status,
            revision=normalized_revision,
            discipline_code=discipline,
            document_number=number,
            title=normalized_title,
            naming_enabled=naming_enabled,
            remote_etag=remote_item.etag,
            updated_at=now,
            updated_by=actor,
        )
        history = DocumentHistory(
            history_id=str(uuid4()),
            item_id=item.item_id,
            project_id=project_id,
            previous_status=previous.status if previous else None,
            new_status=status,
            previous_revision=previous.revision if previous else None,
            new_revision=normalized_revision,
            previous_name=previous.file_name if previous else item.name,
            new_name=remote_item.name,
            actor=actor,
            occurred_at=now,
        )
        self._repository.save(metadata, history)
        return metadata

    def report(self, project_id: str) -> DocumentReport:
        documents = self._repository.list_project(project_id)
        counts = {status: 0 for status in DocumentStatus}
        for document in documents:
            counts[document.status] += 1
        return DocumentReport(project_id, documents, counts)

    def export_csv(self, project_id: str, destination: Path) -> Path:
        report = self.report(project_id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(
                (
                    "Archivo",
                    "Estado",
                    "Revisión",
                    "Disciplina",
                    "Número",
                    "Título",
                    "Actualizado por",
                    "Fecha",
                )
            )
            for document in report.documents:
                writer.writerow(
                    (
                        document.file_name,
                        document.status.label,
                        document.revision,
                        document.discipline_code or "",
                        document.document_number or "",
                        document.title or "",
                        document.updated_by,
                        document.updated_at.astimezone().strftime("%d/%m/%Y %H:%M"),
                    )
                )
        return destination
