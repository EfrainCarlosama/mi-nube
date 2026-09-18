from __future__ import annotations

from datetime import datetime

from mi_nube.database.sqlite import SqliteDatabase
from mi_nube.domain.models import ActivityEvent, SyncedItem, SyncScope


class SqliteSyncRepository:
    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    @staticmethod
    def _scope(row) -> SyncScope:
        return SyncScope(
            scope_id=row["scope_id"],
            scope_type=row["scope_type"],
            remote_item_id=row["remote_item_id"],
            label=row["label"],
            delta_link=row["delta_link"],
            initialized=bool(row["initialized"]),
            last_synced_at=(
                datetime.fromisoformat(row["last_synced_at"]) if row["last_synced_at"] else None
            ),
        )

    def ensure_scope(self, scope: SyncScope) -> SyncScope:
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO sync_scopes(
                    scope_id, scope_type, remote_item_id, label, delta_link,
                    initialized, last_synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope_id) DO UPDATE SET
                    remote_item_id=excluded.remote_item_id,
                    label=excluded.label
                """,
                (
                    scope.scope_id,
                    scope.scope_type,
                    scope.remote_item_id,
                    scope.label,
                    scope.delta_link,
                    int(scope.initialized),
                    scope.last_synced_at.isoformat() if scope.last_synced_at else None,
                ),
            )
        return self.get_scope(scope.scope_id) or scope

    def get_scope(self, scope_id: str) -> SyncScope | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM sync_scopes WHERE scope_id = ?", (scope_id,)
            ).fetchone()
        return self._scope(row) if row else None

    def list_scopes(self) -> tuple[SyncScope, ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM sync_scopes ORDER BY scope_type, label COLLATE NOCASE"
            ).fetchall()
        return tuple(self._scope(row) for row in rows)

    def save_cursor(self, scope_id: str, delta_link: str, synced_at: datetime) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """
                UPDATE sync_scopes
                SET delta_link = ?, initialized = 1, last_synced_at = ?
                WHERE scope_id = ?
                """,
                (delta_link, synced_at.isoformat(), scope_id),
            )

    def reset_scope(self, scope_id: str) -> None:
        with self._database.connect() as connection:
            connection.execute("DELETE FROM synced_items WHERE scope_id = ?", (scope_id,))
            connection.execute(
                """
                UPDATE sync_scopes
                SET delta_link = NULL, initialized = 0, last_synced_at = NULL
                WHERE scope_id = ?
                """,
                (scope_id,),
            )

    def get_item(self, scope_id: str, item_id: str) -> SyncedItem | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM synced_items WHERE scope_id = ? AND item_id = ?",
                (scope_id, item_id),
            ).fetchone()
        if row is None:
            return None
        return SyncedItem(
            scope_id=row["scope_id"],
            item_id=row["item_id"],
            name=row["name"],
            parent_item_id=row["parent_item_id"],
            is_folder=bool(row["is_folder"]),
            etag=row["etag"],
            modified_at=(
                datetime.fromisoformat(row["modified_at"]) if row["modified_at"] else None
            ),
            modified_by=row["modified_by"],
        )

    def save_item(self, item: SyncedItem) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO synced_items(
                    scope_id, item_id, name, parent_item_id, is_folder,
                    etag, modified_at, modified_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope_id, item_id) DO UPDATE SET
                    name=excluded.name,
                    parent_item_id=excluded.parent_item_id,
                    is_folder=excluded.is_folder,
                    etag=excluded.etag,
                    modified_at=excluded.modified_at,
                    modified_by=excluded.modified_by
                """,
                (
                    item.scope_id,
                    item.item_id,
                    item.name,
                    item.parent_item_id,
                    int(item.is_folder),
                    item.etag,
                    item.modified_at.isoformat() if item.modified_at else None,
                    item.modified_by,
                ),
            )

    def delete_item(self, scope_id: str, item_id: str) -> None:
        with self._database.connect() as connection:
            connection.execute(
                "DELETE FROM synced_items WHERE scope_id = ? AND item_id = ?",
                (scope_id, item_id),
            )

    def is_project_item(self, item_id: str | None) -> bool:
        if not item_id:
            return False
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM synced_items
                WHERE scope_id LIKE 'project:%' AND item_id = ? LIMIT 1
                """,
                (item_id,),
            ).fetchone()
        return row is not None

    def save_event(self, event: ActivityEvent, dedupe_key: str) -> bool:
        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO activity_events(
                    event_id, dedupe_key, source, action, actor, target, scope_id,
                    project_name, remote_item_id, occurred_at, details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    dedupe_key,
                    event.source,
                    event.action,
                    event.actor,
                    event.target,
                    event.scope_id,
                    event.project_name,
                    event.remote_item_id,
                    event.occurred_at.isoformat(),
                    event.details,
                ),
            )
        return cursor.rowcount > 0

    def reconcile_local_event(
        self,
        *,
        scope_id: str,
        action: str,
        target: str,
        remote_item_id: str,
        since: datetime,
    ) -> bool:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT event_id FROM activity_events
                WHERE scope_id = ? AND action = ? AND target = ?
                  AND source = 'local' AND occurred_at >= ?
                ORDER BY occurred_at DESC LIMIT 1
                """,
                (scope_id, action, target, since.isoformat()),
            ).fetchone()
            if row is None:
                return False
            connection.execute(
                """
                UPDATE activity_events
                SET source = 'local+graph', remote_item_id = ?
                WHERE event_id = ?
                """,
                (remote_item_id, row["event_id"]),
            )
        return True

    def list_events(
        self, *, scope_id: str | None = None, search: str = "", limit: int = 300
    ) -> tuple[ActivityEvent, ...]:
        clauses: list[str] = []
        values: list[object] = []
        if scope_id:
            clauses.append("scope_id = ?")
            values.append(scope_id)
        if search.strip():
            clauses.append("(target LIKE ? OR actor LIKE ? OR action LIKE ?)")
            pattern = f"%{search.strip()}%"
            values.extend((pattern, pattern, pattern))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(limit)
        with self._database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM activity_events {where}
                ORDER BY occurred_at DESC LIMIT ?
                """,  # noqa: S608 - clauses are fixed strings, values remain parameterized
                values,
            ).fetchall()
        return tuple(
            ActivityEvent(
                event_id=row["event_id"],
                source=row["source"],
                action=row["action"],
                actor=row["actor"],
                target=row["target"],
                scope_id=row["scope_id"],
                project_name=row["project_name"],
                remote_item_id=row["remote_item_id"],
                occurred_at=datetime.fromisoformat(row["occurred_at"]),
                details=row["details"],
            )
            for row in rows
        )
