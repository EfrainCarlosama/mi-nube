from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from mi_nube.domain.models import (
    DriveItem,
    Project,
    ProjectFolder,
    ProjectTemplate,
    TemplateFolder,
)
from mi_nube.graph.errors import GraphConflictError, GraphError
from mi_nube.graph.ports import GraphDriveClient
from mi_nube.projects.errors import ProjectCreationError, ProjectValidationError
from mi_nube.repositories.ports import ProjectRepository
from mi_nube.services.template_codec import validate_folder_name

LOGGER = logging.getLogger(__name__)
WORK_ROOT_NAME = "Mi Nube - Trabajo"

DEFAULT_PROJECT_FOLDERS: tuple[TemplateFolder, ...] = (
    TemplateFolder(
        "01 Arquitectura",
        tuple(TemplateFolder(name) for name in ("Planos", "Modelos", "Documentos", "Referencias")),
    ),
    TemplateFolder(
        "02 Estructuras",
        tuple(
            TemplateFolder(name)
            for name in ("Planos", "Cálculos", "Memorias", "ETABS", "SAFE", "Revit")
        ),
    ),
    TemplateFolder(
        "03 Renders",
        tuple(TemplateFolder(name) for name in ("Borradores", "Finales", "Referencias")),
    ),
    TemplateFolder(
        "04 Presupuesto",
        tuple(
            TemplateFolder(name)
            for name in ("APU", "Presupuesto", "Cotizaciones", "Análisis", "Proveedores")
        ),
    ),
    TemplateFolder(
        "05 Obra",
        tuple(
            TemplateFolder(name)
            for name in (
                "Planillas",
                "Avance de obra",
                "Fotografías",
                "Fiscalización",
                "Libro de obra",
                "Informes",
                "Cronograma",
            )
        ),
    ),
    TemplateFolder(
        "06 Legalización",
        tuple(
            TemplateFolder(name)
            for name in (
                "Municipio",
                "Permisos",
                "Aprobaciones",
                "Entidades públicas",
                "Documentación legal",
            )
        ),
    ),
    TemplateFolder(
        "07 Contratos",
        tuple(
            TemplateFolder(name)
            for name in ("Contrato principal", "Anexos", "Modificaciones", "Actas")
        ),
    ),
    TemplateFolder(
        "08 Cliente",
        tuple(
            TemplateFolder(name)
            for name in ("Documentos recibidos", "Documentos enviados", "Aprobaciones")
        ),
    ),
    TemplateFolder(
        "09 Entrega Final",
        tuple(
            TemplateFolder(name)
            for name in (
                "Planos finales",
                "Memorias",
                "Presupuesto final",
                "Documentación entregada",
            )
        ),
    ),
)


class ProjectService:
    def __init__(self, drive: GraphDriveClient, repository: ProjectRepository) -> None:
        self._drive = drive
        self._repository = repository
        if self._repository.get_default_template() is None:
            self._repository.save_default_template(
                ProjectTemplate("default", "Ingeniería y arquitectura", 1, DEFAULT_PROJECT_FOLDERS)
            )

    def list_projects(self) -> tuple[Project, ...]:
        return self._repository.list_projects()

    def default_template(self) -> ProjectTemplate:
        template = self._repository.get_default_template()
        if template is None:
            raise ProjectCreationError("No existe una plantilla de proyecto configurada.")
        return template

    def save_default_template(self, folders: tuple[TemplateFolder, ...]) -> ProjectTemplate:
        if not folders:
            raise ProjectValidationError("La plantilla debe contener al menos una carpeta.")
        current = self._repository.get_default_template()
        template = ProjectTemplate(
            template_id=current.template_id if current else "default",
            name=current.name if current else "Ingeniería y arquitectura",
            version=(current.version + 1) if current else 1,
            folders=folders,
        )
        self._repository.save_default_template(template)
        return template

    @staticmethod
    def _count_folders(folders: tuple[TemplateFolder, ...]) -> int:
        return sum(1 + ProjectService._count_folders(folder.children) for folder in folders)

    def _work_root(self) -> DriveItem:
        existing = next(
            (
                item
                for item in self._drive.list_children(None)
                if item.is_folder and item.name.casefold() == WORK_ROOT_NAME.casefold()
            ),
            None,
        )
        if existing:
            return existing
        try:
            return self._drive.create_folder(None, WORK_ROOT_NAME)
        except GraphConflictError:
            existing = next(
                (
                    item
                    for item in self._drive.list_children(None)
                    if item.is_folder and item.name.casefold() == WORK_ROOT_NAME.casefold()
                ),
                None,
            )
            if existing:
                return existing
            raise

    def create_project(
        self,
        name: str,
        client: str,
        use_template: bool = True,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> Project:
        clean_name = validate_folder_name(name)
        clean_client = client.strip()
        if not clean_client:
            raise ProjectValidationError("Escribe el nombre del cliente.")
        template = self.default_template()
        folders = template.folders if use_template else ()
        total = 1 + self._count_folders(folders)
        notify = progress or (lambda _done, _total, _label: None)
        project_id = uuid4().hex
        remote_root: DriveItem | None = None
        records: list[ProjectFolder] = []
        completed = 0
        sort_order = 0

        def create_children(
            nodes: tuple[TemplateFolder, ...],
            remote_parent_id: str,
            local_parent_id: str | None,
            parent_path: str,
        ) -> None:
            nonlocal completed, sort_order
            for node in nodes:
                remote = self._drive.create_folder(remote_parent_id, node.name)
                local_id = uuid4().hex
                relative_path = f"{parent_path}/{node.name}" if parent_path else node.name
                records.append(
                    ProjectFolder(
                        folder_id=local_id,
                        project_id=project_id,
                        remote_item_id=remote.item_id,
                        parent_folder_id=local_parent_id,
                        name=node.name,
                        relative_path=relative_path,
                        sort_order=sort_order,
                    )
                )
                sort_order += 1
                completed += 1
                notify(completed, total, relative_path)
                create_children(node.children, remote.item_id, local_id, relative_path)

        try:
            work_root = self._work_root()
            remote_name = (
                clean_name
                if clean_name.casefold().startswith("proyecto -")
                else f"Proyecto - {clean_name}"
            )
            remote_root = self._drive.create_folder(work_root.item_id, remote_name)
            completed = 1
            notify(completed, total, remote_name)
            create_children(folders, remote_root.item_id, None, "")
            now = datetime.now(UTC)
            project = Project(
                project_id=project_id,
                name=clean_name,
                client=clean_client,
                remote_item_id=remote_root.item_id,
                template_version=template.version,
                created_at=now,
                modified_at=now,
            )
            self._repository.add_project(project, tuple(records))
            return project
        except (GraphError, ProjectValidationError):
            if remote_root is not None:
                self._rollback_remote_project(remote_root.item_id)
            raise
        except Exception as error:
            if remote_root is not None:
                self._rollback_remote_project(remote_root.item_id)
            LOGGER.exception("No se pudo registrar el proyecto")
            raise ProjectCreationError(
                "No se pudo completar el proyecto. La creación incompleta fue revertida."
            ) from error

    def _rollback_remote_project(self, item_id: str) -> None:
        try:
            self._drive.delete_item(item_id)
        except GraphError:
            LOGGER.exception("No se pudo revertir la carpeta incompleta del proyecto")
