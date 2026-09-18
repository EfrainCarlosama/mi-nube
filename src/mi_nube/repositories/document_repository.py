from __future__ import annotations

from datetime import datetime

from mi_nube.database.sqlite import SqliteDatabase
from mi_nube.domain.models import (
    DocumentHistory,
    DocumentMetadata,
    DocumentStatus,
)


class SqliteDocumentRepository:
    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    @staticmethod
    def _metadata(row) -> DocumentMetadata:
        return DocumentMetadata(
            item_id=row["item_id"],
            project_id=row["project_id"],
            file_name=row["file_name"],
            status=DocumentStatus(row["status"]),
            revision=row["revision"],
            discipline_code=row["discipline_code"],
            document_number=row["document_number"],
            title=row["title"],
            naming_enabled=bool(row["naming_enabled"]),
            remote_etag=row["remote_etag"],
            updated_at=datetime.fromisoformat(row["updated_at"]),
            updated_by=row["updated_by"],
        )

    def get(self, item_id: str) -> DocumentMetadata | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM document_metadata WHERE item_id = ?", (item_id,)
            ).fetchone()
        return self._metadata(row) if row else None

    def save(self, metadata: DocumentMetadata, history: DocumentHistory) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO document_metadata(
                    item_id, project_id, file_name, status, revision,
                    discipline_code, document_number, title, naming_enabled,
                    remote_etag, updated_at, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    project_id=excluded.project_id,
                    file_name=excluded.file_name,
                    status=excluded.status,
                    revision=excluded.revision,
                    discipline_code=excluded.discipline_code,
                    document_number=excluded.document_number,
                    title=excluded.title,
                    naming_enabled=excluded.naming_enabled,
                    remote_etag=excluded.remote_etag,
                    updated_at=excluded.updated_at,
                    updated_by=excluded.updated_by
                """,
                (
                    metadata.item_id,
                    metadata.project_id,
                    metadata.file_name,
                    metadata.status.value,
                    metadata.revision,
                    metadata.discipline_code,
                    metadata.document_number,
                    metadata.title,
                    int(metadata.naming_enabled),
                    metadata.remote_etag,
                    metadata.updated_at.isoformat(),
                    metadata.updated_by,
                ),
            )
            connection.execute(
                """
                INSERT INTO document_history(
                    history_id, item_id, project_id, previous_status, new_status,
                    previous_revision, new_revision, previous_name, new_name,
                    actor, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    history.history_id,
                    history.item_id,
                    history.project_id,
                    history.previous_status.value if history.previous_status else None,
                    history.new_status.value,
                    history.previous_revision,
                    history.new_revision,
                    history.previous_name,
                    history.new_name,
                    history.actor,
                    history.occurred_at.isoformat(),
                ),
            )

    def list_project(
        self,
        project_id: str,
        *,
        status: DocumentStatus | None = None,
        search: str = "",
    ) -> tuple[DocumentMetadata, ...]:
        clauses = ["project_id = ?"]
        values: list[object] = [project_id]
        if status:
            clauses.append("status = ?")
            values.append(status.value)
        if search.strip():
            clauses.append(
                "(file_name LIKE ? OR revision LIKE ? OR discipline_code LIKE ? OR title LIKE ?)"
            )
            pattern = f"%{search.strip()}%"
            values.extend((pattern, pattern, pattern, pattern))
        with self._database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM document_metadata
                WHERE {" AND ".join(clauses)}
                ORDER BY updated_at DESC, file_name COLLATE NOCASE
                """,  # noqa: S608 - fixed clauses with parameterized values
                values,
            ).fetchall()
        return tuple(self._metadata(row) for row in rows)

    def list_history(self, item_id: str) -> tuple[DocumentHistory, ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM document_history
                WHERE item_id = ? ORDER BY occurred_at DESC
                """,
                (item_id,),
            ).fetchall()
        return tuple(
            DocumentHistory(
                history_id=row["history_id"],
                item_id=row["item_id"],
                project_id=row["project_id"],
                previous_status=(
                    DocumentStatus(row["previous_status"]) if row["previous_status"] else None
                ),
                new_status=DocumentStatus(row["new_status"]),
                previous_revision=row["previous_revision"],
                new_revision=row["new_revision"],
                previous_name=row["previous_name"],
                new_name=row["new_name"],
                actor=row["actor"],
                occurred_at=datetime.fromisoformat(row["occurred_at"]),
            )
            for row in rows
        )
