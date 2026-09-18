from __future__ import annotations

import json
from datetime import UTC, datetime

from mi_nube.database.sqlite import SqliteDatabase
from mi_nube.domain.models import (
    FolderPermissionRule,
    PermissionChange,
    Project,
    ProjectFolder,
    ProjectMember,
    ProjectTemplate,
    TemplateFolder,
)


class SqliteProjectRepository:
    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    @staticmethod
    def _folder_to_dict(folder: TemplateFolder) -> dict[str, object]:
        return {
            "name": folder.name,
            "children": [
                SqliteProjectRepository._folder_to_dict(child) for child in folder.children
            ],
        }

    @staticmethod
    def _folder_from_dict(value: object) -> TemplateFolder:
        if not isinstance(value, dict) or not isinstance(value.get("name"), str):
            raise ValueError("La plantilla guardada no es válida.")
        raw_children = value.get("children", [])
        if not isinstance(raw_children, list):
            raise ValueError("La plantilla guardada no es válida.")
        return TemplateFolder(
            value["name"],
            tuple(SqliteProjectRepository._folder_from_dict(child) for child in raw_children),
        )

    def save_default_template(self, template: ProjectTemplate) -> None:
        structure = json.dumps(
            [self._folder_to_dict(folder) for folder in template.folders],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with self._database.connect() as connection:
            connection.execute("UPDATE project_templates SET is_default = 0 WHERE is_default = 1")
            connection.execute(
                """
                INSERT INTO project_templates(
                    template_id, name, version, structure_json, is_default, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(template_id) DO UPDATE SET
                    name = excluded.name,
                    version = excluded.version,
                    structure_json = excluded.structure_json,
                    is_default = 1,
                    updated_at = excluded.updated_at
                """,
                (
                    template.template_id,
                    template.name,
                    template.version,
                    structure,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def get_default_template(self) -> ProjectTemplate | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT template_id, name, version, structure_json
                FROM project_templates WHERE is_default = 1
                """
            ).fetchone()
        if row is None:
            return None
        values = json.loads(row["structure_json"])
        if not isinstance(values, list):
            raise ValueError("La plantilla guardada no es válida.")
        return ProjectTemplate(
            template_id=row["template_id"],
            name=row["name"],
            version=int(row["version"]),
            folders=tuple(self._folder_from_dict(value) for value in values),
        )

    def add_project(self, project: Project, folders: tuple[ProjectFolder, ...]) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO projects(
                    project_id, name, client, remote_item_id, template_version,
                    created_at, modified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project.project_id,
                    project.name,
                    project.client,
                    project.remote_item_id,
                    project.template_version,
                    project.created_at.isoformat(),
                    project.modified_at.isoformat(),
                ),
            )
            connection.executemany(
                """
                INSERT INTO project_folders(
                    folder_id, project_id, remote_item_id, parent_folder_id,
                    name, relative_path, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        folder.folder_id,
                        folder.project_id,
                        folder.remote_item_id,
                        folder.parent_folder_id,
                        folder.name,
                        folder.relative_path,
                        folder.sort_order,
                    )
                    for folder in folders
                ],
            )

    def list_projects(self) -> tuple[Project, ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT project_id, name, client, remote_item_id, template_version,
                       created_at, modified_at
                FROM projects
                ORDER BY modified_at DESC, name COLLATE NOCASE
                """
            ).fetchall()
        return tuple(
            Project(
                project_id=row["project_id"],
                name=row["name"],
                client=row["client"],
                remote_item_id=row["remote_item_id"],
                template_version=int(row["template_version"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                modified_at=datetime.fromisoformat(row["modified_at"]),
            )
            for row in rows
        )

    def list_folders(self, project_id: str) -> tuple[ProjectFolder, ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT folder_id, project_id, remote_item_id, parent_folder_id,
                       name, relative_path, sort_order
                FROM project_folders
                WHERE project_id = ?
                ORDER BY sort_order
                """,
                (project_id,),
            ).fetchall()
        return tuple(
            ProjectFolder(
                folder_id=row["folder_id"],
                project_id=row["project_id"],
                remote_item_id=row["remote_item_id"],
                parent_folder_id=row["parent_folder_id"],
                name=row["name"],
                relative_path=row["relative_path"],
                sort_order=int(row["sort_order"]),
            )
            for row in rows
        )

    @staticmethod
    def _project_from_row(row) -> Project:
        return Project(
            project_id=row["project_id"],
            name=row["name"],
            client=row["client"],
            remote_item_id=row["remote_item_id"],
            template_version=int(row["template_version"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            modified_at=datetime.fromisoformat(row["modified_at"]),
        )

    def get_project(self, project_id: str) -> Project | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT project_id, name, client, remote_item_id, template_version,
                       created_at, modified_at
                FROM projects WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()
        return self._project_from_row(row) if row is not None else None

    @staticmethod
    def _insert_rule(connection, rule: FolderPermissionRule) -> None:
        connection.execute(
            """
            INSERT INTO permission_rules(
                rule_id, member_id, project_id, folder_id, target_item_id, level,
                capabilities, graph_access, graph_permission_id,
                apply_to_new_subfolders, modified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(member_id, target_item_id) DO UPDATE SET
                folder_id = excluded.folder_id,
                level = excluded.level,
                capabilities = excluded.capabilities,
                graph_access = excluded.graph_access,
                graph_permission_id = excluded.graph_permission_id,
                apply_to_new_subfolders = excluded.apply_to_new_subfolders,
                modified_at = excluded.modified_at
            """,
            (
                rule.rule_id,
                rule.member_id,
                rule.project_id,
                rule.folder_id,
                rule.target_item_id,
                rule.level,
                rule.capabilities,
                rule.graph_access,
                rule.graph_permission_id,
                int(rule.apply_to_new_subfolders),
                rule.modified_at.isoformat(),
            ),
        )

    @staticmethod
    def _insert_change(connection, change: PermissionChange) -> None:
        connection.execute(
            """
            INSERT INTO permission_changes(
                change_id, project_id, member_id, member_email, folder_path,
                previous_level, new_level, previous_graph_access, new_graph_access,
                actor_email, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                change.change_id,
                change.project_id,
                change.member_id,
                change.member_email,
                change.folder_path,
                change.previous_level,
                change.new_level,
                change.previous_graph_access,
                change.new_graph_access,
                change.actor_email,
                change.occurred_at.isoformat(),
            ),
        )

    def add_member(
        self,
        member: ProjectMember,
        rule: FolderPermissionRule | None = None,
        change: PermissionChange | None = None,
    ) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO project_members(
                    member_id, project_id, email, display_name, role, created_at, modified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    member.member_id,
                    member.project_id,
                    member.email,
                    member.display_name,
                    member.role,
                    member.created_at.isoformat(),
                    member.modified_at.isoformat(),
                ),
            )
            if rule is not None:
                self._insert_rule(connection, rule)
            if change is not None:
                self._insert_change(connection, change)

    def list_members(self, project_id: str) -> tuple[ProjectMember, ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT member_id, project_id, email, display_name, role, created_at, modified_at
                FROM project_members WHERE project_id = ?
                ORDER BY display_name COLLATE NOCASE, email COLLATE NOCASE
                """,
                (project_id,),
            ).fetchall()
        return tuple(
            ProjectMember(
                member_id=row["member_id"],
                project_id=row["project_id"],
                email=row["email"],
                display_name=row["display_name"],
                role=row["role"],
                created_at=datetime.fromisoformat(row["created_at"]),
                modified_at=datetime.fromisoformat(row["modified_at"]),
            )
            for row in rows
        )

    def get_member(self, member_id: str) -> ProjectMember | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT member_id, project_id, email, display_name, role, created_at, modified_at
                FROM project_members WHERE member_id = ?
                """,
                (member_id,),
            ).fetchone()
        if row is None:
            return None
        return ProjectMember(
            member_id=row["member_id"],
            project_id=row["project_id"],
            email=row["email"],
            display_name=row["display_name"],
            role=row["role"],
            created_at=datetime.fromisoformat(row["created_at"]),
            modified_at=datetime.fromisoformat(row["modified_at"]),
        )

    def update_member_role(self, member_id: str, role: str, modified_at: str) -> None:
        with self._database.connect() as connection:
            connection.execute(
                "UPDATE project_members SET role = ?, modified_at = ? WHERE member_id = ?",
                (role, modified_at, member_id),
            )

    def delete_member(self, member_id: str) -> None:
        with self._database.connect() as connection:
            connection.execute("DELETE FROM project_members WHERE member_id = ?", (member_id,))

    def upsert_rule(self, rule: FolderPermissionRule, change: PermissionChange) -> None:
        with self._database.connect() as connection:
            self._insert_rule(connection, rule)
            self._insert_change(connection, change)

    @staticmethod
    def _rule_from_row(row) -> FolderPermissionRule:
        return FolderPermissionRule(
            rule_id=row["rule_id"],
            member_id=row["member_id"],
            project_id=row["project_id"],
            folder_id=row["folder_id"],
            target_item_id=row["target_item_id"],
            level=row["level"],
            capabilities=int(row["capabilities"]),
            graph_access=row["graph_access"],
            graph_permission_id=row["graph_permission_id"],
            apply_to_new_subfolders=bool(row["apply_to_new_subfolders"]),
            modified_at=datetime.fromisoformat(row["modified_at"]),
        )

    def list_rules(self, member_id: str) -> tuple[FolderPermissionRule, ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM permission_rules WHERE member_id = ? ORDER BY folder_id",
                (member_id,),
            ).fetchall()
        return tuple(self._rule_from_row(row) for row in rows)

    def get_rule(self, member_id: str, target_item_id: str) -> FolderPermissionRule | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM permission_rules
                WHERE member_id = ? AND target_item_id = ?
                """,
                (member_id, target_item_id),
            ).fetchone()
        return self._rule_from_row(row) if row is not None else None

    def list_changes(self, project_id: str) -> tuple[PermissionChange, ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM permission_changes
                WHERE project_id = ? ORDER BY occurred_at DESC
                """,
                (project_id,),
            ).fetchall()
        return tuple(
            PermissionChange(
                change_id=row["change_id"],
                project_id=row["project_id"],
                member_id=row["member_id"],
                member_email=row["member_email"],
                folder_path=row["folder_path"],
                previous_level=row["previous_level"],
                new_level=row["new_level"],
                previous_graph_access=row["previous_graph_access"],
                new_graph_access=row["new_graph_access"],
                actor_email=row["actor_email"],
                occurred_at=datetime.fromisoformat(row["occurred_at"]),
            )
            for row in rows
        )
