from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mi_nube.database.sqlite import SqliteDatabase
from mi_nube.domain.models import DriveItem, SharingPermission
from mi_nube.domain.permissions import (
    DEFAULT_CAPABILITIES,
    GraphAccess,
    PermissionLevel,
    ProjectRole,
)
from mi_nube.graph.errors import GraphServiceError
from mi_nube.projects.errors import ProjectValidationError
from mi_nube.repositories.project_repository import SqliteProjectRepository
from mi_nube.services.permission_service import PermissionService
from mi_nube.services.project_service import WORK_ROOT_NAME, ProjectService
from mi_nube.services.template_codec import format_template, parse_template


def drive_item(item_id: str, name: str) -> DriveItem:
    return DriveItem(
        item_id=item_id,
        name=name,
        is_folder=True,
        size_bytes=0,
        modified_at=datetime.now(UTC),
        modified_by="Prueba",
        parent_path="/drive/root:",
    )


class FakeProjectDrive:
    def __init__(self, fail_at: int | None = None) -> None:
        self.children: dict[str | None, list[DriveItem]] = {None: []}
        self.deleted: list[str] = []
        self.create_count = 0
        self.fail_at = fail_at
        self.invited: list[tuple[str, str, str]] = []
        self.revoked: list[tuple[str, str]] = []

    def list_children(self, item_id=None):
        return tuple(self.children.get(item_id, []))

    def create_folder(self, parent_id, name):
        self.create_count += 1
        if self.fail_at == self.create_count:
            raise GraphServiceError("fallo simulado")
        item = drive_item(f"remote-{self.create_count}", name)
        self.children.setdefault(parent_id, []).append(item)
        self.children.setdefault(item.item_id, [])
        return item

    def delete_item(self, item_id, etag=None):
        self.deleted.append(item_id)

    def invite_user(
        self,
        item_id,
        email,
        role,
        *,
        send_invitation=True,
        message="",
    ):
        self.invited.append((item_id, email, role))
        return SharingPermission(f"permission-{len(self.invited)}", (role,), grantee_email=email)

    def delete_permission(self, item_id, permission_id):
        self.revoked.append((item_id, permission_id))


def project_service(tmp_path: Path, drive: FakeProjectDrive):
    repository = SqliteProjectRepository(SqliteDatabase(tmp_path / "mi_nube.db"))
    return ProjectService(drive, repository), repository


def test_default_template_roundtrips_through_text_and_sqlite(tmp_path: Path) -> None:
    service, repository = project_service(tmp_path, FakeProjectDrive())
    template = service.default_template()

    parsed = parse_template(format_template(template.folders))
    saved = service.save_default_template(parsed)
    reloaded = repository.get_default_template()

    assert len(saved.folders) == 9
    assert saved.version == 2
    assert reloaded == saved
    assert saved.folders[1].children[-1].name == "Revit"


def test_project_creation_builds_remote_tree_and_persists_folder_ids(tmp_path: Path) -> None:
    drive = FakeProjectDrive()
    service, repository = project_service(tmp_path, drive)
    progress: list[tuple[int, int, str]] = []

    project = service.create_project(
        "Residencia Carlos",
        "Sr. Carlos",
        progress=lambda done, total, label: progress.append((done, total, label)),
    )

    assert drive.children[None][0].name == WORK_ROOT_NAME
    work_root_id = drive.children[None][0].item_id
    assert drive.children[work_root_id][0].name == "Proyecto - Residencia Carlos"
    assert repository.list_projects() == (project,)
    records = repository.list_folders(project.project_id)
    assert len(records) == progress[-1][1] - 1
    assert progress[-1][0] == progress[-1][1]
    assert any(folder.relative_path == "02 Estructuras/Revit" for folder in records)


def test_project_creation_rolls_back_remote_root_after_partial_failure(tmp_path: Path) -> None:
    drive = FakeProjectDrive(fail_at=5)
    service, repository = project_service(tmp_path, drive)

    with pytest.raises(GraphServiceError, match="fallo simulado"):
        service.create_project("Proyecto fallido", "Cliente")

    assert drive.deleted == ["remote-2"]
    assert repository.list_projects() == ()


def test_template_parser_rejects_invalid_indentation() -> None:
    with pytest.raises(ProjectValidationError, match="sangría"):
        parse_template("01 Arquitectura\n   Planos")


def test_personal_account_member_roles_map_to_real_graph_access(tmp_path: Path) -> None:
    drive = FakeProjectDrive()
    project_service_instance, repository = project_service(tmp_path, drive)
    project = project_service_instance.create_project("Casa", "Cliente")
    permissions = PermissionService(drive, repository)

    member = permissions.add_member(
        project.project_id,
        "Admin@Example.com",
        "Administrador",
        ProjectRole.PROJECT_ADMIN,
        "owner@example.com",
    )

    assert drive.invited[-1] == (project.remote_item_id, "admin@example.com", "write")
    root_rule = repository.get_rule(member.member_id, project.remote_item_id)
    assert root_rule is not None
    assert root_rule.graph_access == GraphAccess.WRITE.value
    assert repository.list_changes(project.project_id)[0].new_level == "Control total"


def test_member_requires_a_visible_name_instead_of_an_email(tmp_path: Path) -> None:
    drive = FakeProjectDrive()
    project_service_instance, repository = project_service(tmp_path, drive)
    project = project_service_instance.create_project("Casa", "Cliente")
    permissions = PermissionService(drive, repository)

    with pytest.raises(ProjectValidationError, match="nombre visible"):
        permissions.add_member(
            project.project_id,
            "persona@example.com",
            "persona@example.com",
            ProjectRole.COLLABORATOR,
            "owner@example.com",
        )

    assert repository.list_members(project.project_id) == ()
    assert drive.invited == []


def test_folder_policies_keep_internal_level_and_graph_read_write_mapping(tmp_path: Path) -> None:
    drive = FakeProjectDrive()
    project_service_instance, repository = project_service(tmp_path, drive)
    project = project_service_instance.create_project("Edificio", "Cliente")
    permissions = PermissionService(drive, repository)
    member = permissions.add_member(
        project.project_id,
        "colaborador@example.com",
        "Colaborador",
        ProjectRole.COLLABORATOR,
        "owner@example.com",
    )
    folders = repository.list_folders(project.project_id)
    architecture = next(folder for folder in folders if folder.relative_path == "01 Arquitectura")
    structures = next(folder for folder in folders if folder.relative_path == "02 Estructuras")

    permissions.set_folder_permissions(
        member.member_id,
        (
            (
                architecture.folder_id,
                PermissionLevel.VIEW_ONLY,
                DEFAULT_CAPABILITIES[PermissionLevel.VIEW_ONLY],
                True,
            ),
            (
                structures.folder_id,
                PermissionLevel.MODIFY,
                DEFAULT_CAPABILITIES[PermissionLevel.MODIFY],
                True,
            ),
        ),
        "owner@example.com",
    )

    rules = {rule.folder_id: rule for rule in repository.list_rules(member.member_id)}
    assert rules[architecture.folder_id].level == PermissionLevel.VIEW_ONLY.value
    assert rules[architecture.folder_id].graph_access == GraphAccess.READ.value
    assert rules[structures.folder_id].graph_access == GraphAccess.WRITE.value
    assert drive.invited[-2:] == [
        (architecture.remote_item_id, member.email, "read"),
        (structures.remote_item_id, member.email, "write"),
    ]

    permissions.remove_member(member.member_id, "owner@example.com")
    assert repository.list_members(project.project_id) == ()
    assert len(drive.revoked) == 2
