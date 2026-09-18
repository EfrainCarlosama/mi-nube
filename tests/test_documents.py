from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mi_nube.database.sqlite import SqliteDatabase
from mi_nube.documents.errors import DocumentValidationError
from mi_nube.domain.models import DocumentStatus, DriveItem, Project
from mi_nube.repositories.document_repository import SqliteDocumentRepository
from mi_nube.repositories.project_repository import SqliteProjectRepository
from mi_nube.services.document_service import DocumentService


class RenameGraphClient:
    def __init__(self) -> None:
        self.renames: list[tuple[str, str, str | None]] = []

    def rename_item(self, item_id: str, new_name: str, etag: str | None = None):
        self.renames.append((item_id, new_name, etag))
        return replace(FILE, name=new_name, etag='"new-etag"')


FILE = DriveItem(
    item_id="file-1",
    name="plano original.pdf",
    is_folder=False,
    size_bytes=100,
    modified_at=datetime(2026, 9, 17, tzinfo=UTC),
    modified_by="Efraín",
    parent_path="/drive/root:/Proyecto",
    etag='"etag"',
)


def service_for(tmp_path: Path):
    database = SqliteDatabase(tmp_path / "app.db")
    project = Project(
        "project-1",
        "Residencia",
        "Cliente",
        "remote-project",
        1,
        datetime.now(UTC),
        datetime.now(UTC),
    )
    SqliteProjectRepository(database).add_project(project, ())
    graph = RenameGraphClient()
    service = DocumentService(graph, SqliteDocumentRepository(database), lambda: "Efraín")
    return service, graph


def test_document_naming_is_optional_and_normalized(tmp_path: Path) -> None:
    service, graph = service_for(tmp_path)

    draft = service.save(
        "project-1",
        FILE,
        status=DocumentStatus.DRAFT,
        revision="r1",
        naming_enabled=False,
    )
    approved = service.save(
        "project-1",
        FILE,
        status=DocumentStatus.APPROVED,
        revision="2",
        naming_enabled=True,
        discipline_code="arq",
        document_number="4",
        title="Planta Baja",
        rename_remote=True,
    )

    assert draft.file_name == "plano original.pdf"
    assert draft.revision == "R01"
    assert approved.file_name == "ARQ-004-R02-Planta-Baja.pdf"
    assert graph.renames == [("file-1", "ARQ-004-R02-Planta-Baja.pdf", '"etag"')]
    history = service.list_history(FILE.item_id)
    assert len(history) == 2
    assert history[0].previous_status == DocumentStatus.DRAFT
    assert history[0].new_status == DocumentStatus.APPROVED


def test_document_report_filters_and_exports_utf8_csv(tmp_path: Path) -> None:
    service, _graph = service_for(tmp_path)
    service.save(
        "project-1",
        FILE,
        status=DocumentStatus.IN_REVIEW,
        revision="R03",
        naming_enabled=False,
    )

    values = service.list_project("project-1", DocumentStatus.IN_REVIEW, "plano")
    report = service.report("project-1")
    destination = service.export_csv("project-1", tmp_path / "reporte.csv")

    assert len(values) == 1
    assert report.counts[DocumentStatus.IN_REVIEW] == 1
    assert "En revisión" in destination.read_text(encoding="utf-8-sig")


@pytest.mark.parametrize("revision", ("", "R", "rev2", "R1000"))
def test_invalid_revision_is_rejected(tmp_path: Path, revision: str) -> None:
    service, _graph = service_for(tmp_path)
    with pytest.raises(DocumentValidationError, match="revisión"):
        service.save(
            "project-1",
            FILE,
            status=DocumentStatus.DRAFT,
            revision=revision,
            naming_enabled=False,
        )


def test_folder_cannot_receive_document_status(tmp_path: Path) -> None:
    service, _graph = service_for(tmp_path)
    with pytest.raises(DocumentValidationError, match="solo a archivos"):
        service.save(
            "project-1",
            replace(FILE, is_folder=True),
            status=DocumentStatus.DRAFT,
            revision="R01",
            naming_enabled=False,
        )
