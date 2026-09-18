from __future__ import annotations

import logging
import re
from collections.abc import Callable, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from uuid import uuid4

from mi_nube.domain.models import (
    FolderPermissionRule,
    PermissionChange,
    PermissionEditorData,
    Project,
    ProjectMember,
)
from mi_nube.domain.permissions import (
    DEFAULT_CAPABILITIES,
    Capability,
    GraphAccess,
    PermissionLevel,
    ProjectRole,
    graph_access_for,
)
from mi_nube.graph.errors import GraphError, GraphNotFoundError
from mi_nube.graph.ports import GraphDriveClient
from mi_nube.projects.errors import ProjectCreationError, ProjectValidationError
from mi_nube.repositories.ports import ProjectRepository

LOGGER = logging.getLogger(__name__)
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _role_root_policy(role: ProjectRole) -> tuple[PermissionLevel, GraphAccess]:
    if role is ProjectRole.PROJECT_ADMIN:
        return PermissionLevel.FULL_CONTROL, GraphAccess.WRITE
    if role is ProjectRole.VIEWER:
        return PermissionLevel.VIEW_AND_DOWNLOAD, GraphAccess.READ
    return PermissionLevel.NO_ACCESS, GraphAccess.NONE


class PermissionService:
    def __init__(self, drive: GraphDriveClient, repository: ProjectRepository) -> None:
        self._drive = drive
        self._repository = repository

    def list_members(self, project_id: str) -> tuple[ProjectMember, ...]:
        return self._repository.list_members(project_id)

    def list_history(self, project_id: str) -> tuple[PermissionChange, ...]:
        return self._repository.list_changes(project_id)

    def editor_data(self, member_id: str) -> PermissionEditorData:
        member = self._require_member(member_id)
        return PermissionEditorData(
            member=member,
            folders=self._repository.list_folders(member.project_id),
            rules=self._repository.list_rules(member_id),
        )

    @staticmethod
    def _validate_email(email: str) -> str:
        cleaned = email.strip().casefold()
        if not _EMAIL_PATTERN.fullmatch(cleaned):
            raise ProjectValidationError("Escribe un correo electrónico válido.")
        return cleaned

    def _require_project(self, project_id: str) -> Project:
        project = self._repository.get_project(project_id)
        if project is None:
            raise ProjectValidationError("El proyecto ya no existe en la base local.")
        return project

    def _require_member(self, member_id: str) -> ProjectMember:
        member = self._repository.get_member(member_id)
        if member is None:
            raise ProjectValidationError("El integrante ya no existe en el proyecto.")
        return member

    @staticmethod
    def _new_change(
        member: ProjectMember,
        folder_path: str,
        previous_level: PermissionLevel,
        new_level: PermissionLevel,
        previous_access: GraphAccess,
        new_access: GraphAccess,
        actor_email: str,
        occurred_at: datetime,
    ) -> PermissionChange:
        return PermissionChange(
            change_id=uuid4().hex,
            project_id=member.project_id,
            member_id=member.member_id,
            member_email=member.email,
            folder_path=folder_path,
            previous_level=previous_level.value,
            new_level=new_level.value,
            previous_graph_access=previous_access.value,
            new_graph_access=new_access.value,
            actor_email=actor_email,
            occurred_at=occurred_at,
        )

    def add_member(
        self,
        project_id: str,
        email: str,
        display_name: str,
        role: ProjectRole,
        actor_email: str,
    ) -> ProjectMember:
        if role is ProjectRole.OWNER:
            raise ProjectValidationError("El propietario general no se agrega como invitado.")
        project = self._require_project(project_id)
        cleaned_email = self._validate_email(email)
        if any(
            existing.email.casefold() == cleaned_email
            for existing in self._repository.list_members(project_id)
        ):
            raise ProjectValidationError("Ese correo ya pertenece al equipo del proyecto.")
        clean_name = display_name.strip()
        if not clean_name or "@" in clean_name:
            raise ProjectValidationError(
                "Escribe el nombre visible de la persona, por ejemplo Juan Caballero."
            )
        now = datetime.now(UTC)
        member = ProjectMember(
            member_id=uuid4().hex,
            project_id=project_id,
            email=cleaned_email,
            display_name=clean_name,
            role=role.value,
            created_at=now,
            modified_at=now,
        )
        level, graph_access = _role_root_policy(role)
        permission_id: str | None = None
        if graph_access is not GraphAccess.NONE:
            permission = self._drive.invite_user(
                project.remote_item_id,
                cleaned_email,
                graph_access.value,
                message=f"Acceso al proyecto {project.name} desde Mi Nube.",
            )
            permission_id = permission.permission_id
        rule = FolderPermissionRule(
            rule_id=uuid4().hex,
            member_id=member.member_id,
            project_id=project_id,
            folder_id=None,
            target_item_id=project.remote_item_id,
            level=level.value,
            capabilities=int(DEFAULT_CAPABILITIES[level].value),
            graph_access=graph_access.value,
            graph_permission_id=permission_id,
            apply_to_new_subfolders=True,
            modified_at=now,
        )
        change = self._new_change(
            member,
            "Proyecto completo",
            PermissionLevel.NO_ACCESS,
            level,
            GraphAccess.NONE,
            graph_access,
            actor_email,
            now,
        )
        try:
            self._repository.add_member(member, rule, change)
        except Exception as error:
            if permission_id:
                try:
                    self._drive.delete_permission(project.remote_item_id, permission_id)
                except GraphError:
                    LOGGER.exception("No se pudo revertir la invitación tras un fallo local")
            raise ProjectCreationError(
                "No se pudo registrar al integrante. La invitación fue revertida."
            ) from error
        return member

    def change_role(
        self,
        member_id: str,
        role: ProjectRole,
        actor_email: str,
    ) -> ProjectMember:
        if role is ProjectRole.OWNER:
            raise ProjectValidationError("No se puede asignar otro propietario general.")
        member = self._require_member(member_id)
        project = self._require_project(member.project_id)
        level, access = _role_root_policy(role)
        self._set_target_rule(
            member,
            project.remote_item_id,
            None,
            "Proyecto completo",
            level,
            DEFAULT_CAPABILITIES[level],
            True,
            actor_email,
        )
        now = datetime.now(UTC)
        self._repository.update_member_role(member_id, role.value, now.isoformat())
        return ProjectMember(
            member_id=member.member_id,
            project_id=member.project_id,
            email=member.email,
            display_name=member.display_name,
            role=role.value,
            created_at=member.created_at,
            modified_at=now,
        )

    def set_folder_permissions(
        self,
        member_id: str,
        updates: Sequence[tuple[str, PermissionLevel, Capability, bool]],
        actor_email: str,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> PermissionEditorData:
        member = self._require_member(member_id)
        folders = {
            folder.folder_id: folder for folder in self._repository.list_folders(member.project_id)
        }
        notify = progress or (lambda _done, _total, _label: None)
        for index, (folder_id, level, capabilities, apply_new) in enumerate(updates, start=1):
            folder = folders.get(folder_id)
            if folder is None:
                raise ProjectValidationError("Una carpeta seleccionada ya no existe.")
            self._set_target_rule(
                member,
                folder.remote_item_id,
                folder.folder_id,
                folder.relative_path,
                level,
                capabilities,
                apply_new,
                actor_email,
            )
            notify(index, len(updates), folder.relative_path)
        return self.editor_data(member_id)

    def _set_target_rule(
        self,
        member: ProjectMember,
        target_item_id: str,
        folder_id: str | None,
        folder_path: str,
        level: PermissionLevel,
        capabilities: Capability,
        apply_new: bool,
        actor_email: str,
    ) -> FolderPermissionRule:
        old = self._repository.get_rule(member.member_id, target_item_id)
        old_level = PermissionLevel(old.level) if old else PermissionLevel.NO_ACCESS
        old_access = GraphAccess(old.graph_access) if old else GraphAccess.NONE
        new_access = graph_access_for(level, capabilities)
        permission_id = old.graph_permission_id if old else None

        if old_access is not new_access or (
            new_access is not GraphAccess.NONE and not permission_id
        ):
            if permission_id:
                with suppress(GraphNotFoundError):
                    self._drive.delete_permission(target_item_id, permission_id)
                permission_id = None
            if new_access is not GraphAccess.NONE:
                permission = self._drive.invite_user(
                    target_item_id,
                    member.email,
                    new_access.value,
                    message="Actualización de acceso desde Mi Nube.",
                )
                permission_id = permission.permission_id

        now = datetime.now(UTC)
        rule = FolderPermissionRule(
            rule_id=old.rule_id if old else uuid4().hex,
            member_id=member.member_id,
            project_id=member.project_id,
            folder_id=folder_id,
            target_item_id=target_item_id,
            level=level.value,
            capabilities=int(capabilities.value),
            graph_access=new_access.value,
            graph_permission_id=permission_id,
            apply_to_new_subfolders=apply_new,
            modified_at=now,
        )
        change = self._new_change(
            member,
            folder_path,
            old_level,
            level,
            old_access,
            new_access,
            actor_email,
            now,
        )
        self._repository.upsert_rule(rule, change)
        return rule

    def remove_member(self, member_id: str, actor_email: str) -> None:
        member = self._require_member(member_id)
        folder_paths = {
            folder.folder_id: folder.relative_path
            for folder in self._repository.list_folders(member.project_id)
        }
        for rule in self._repository.list_rules(member_id):
            if not rule.graph_permission_id:
                continue
            with suppress(GraphNotFoundError):
                self._drive.delete_permission(rule.target_item_id, rule.graph_permission_id)
            now = datetime.now(UTC)
            revoked_rule = FolderPermissionRule(
                rule_id=rule.rule_id,
                member_id=rule.member_id,
                project_id=rule.project_id,
                folder_id=rule.folder_id,
                target_item_id=rule.target_item_id,
                level=PermissionLevel.NO_ACCESS.value,
                capabilities=int(Capability.NONE.value),
                graph_access=GraphAccess.NONE.value,
                graph_permission_id=None,
                apply_to_new_subfolders=rule.apply_to_new_subfolders,
                modified_at=now,
            )
            change = self._new_change(
                member,
                (
                    "Proyecto completo"
                    if rule.folder_id is None
                    else folder_paths.get(rule.folder_id, "Carpeta eliminada")
                ),
                PermissionLevel(rule.level),
                PermissionLevel.NO_ACCESS,
                GraphAccess(rule.graph_access),
                GraphAccess.NONE,
                actor_email,
                now,
            )
            self._repository.upsert_rule(revoked_rule, change)
        self._repository.delete_member(member.member_id)
