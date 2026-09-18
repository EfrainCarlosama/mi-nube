from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

_MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS project_templates (
            template_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            version INTEGER NOT NULL,
            structure_json TEXT NOT NULL,
            is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
            updated_at TEXT NOT NULL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS ux_project_templates_default
            ON project_templates(is_default) WHERE is_default = 1;

        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            client TEXT NOT NULL,
            remote_item_id TEXT NOT NULL UNIQUE,
            template_version INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            modified_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS project_folders (
            folder_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            remote_item_id TEXT NOT NULL UNIQUE,
            parent_folder_id TEXT REFERENCES project_folders(folder_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            sort_order INTEGER NOT NULL,
            UNIQUE(project_id, relative_path)
        );

        CREATE INDEX IF NOT EXISTS ix_project_folders_project
            ON project_folders(project_id, sort_order);
        """,
    ),
    (
        2,
        """
        CREATE TABLE IF NOT EXISTS project_members (
            member_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            email TEXT NOT NULL COLLATE NOCASE,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL,
            modified_at TEXT NOT NULL,
            UNIQUE(project_id, email)
        );

        CREATE TABLE IF NOT EXISTS permission_rules (
            rule_id TEXT PRIMARY KEY,
            member_id TEXT NOT NULL REFERENCES project_members(member_id) ON DELETE CASCADE,
            project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            folder_id TEXT REFERENCES project_folders(folder_id) ON DELETE CASCADE,
            target_item_id TEXT NOT NULL,
            level TEXT NOT NULL,
            capabilities INTEGER NOT NULL,
            graph_access TEXT NOT NULL,
            graph_permission_id TEXT,
            apply_to_new_subfolders INTEGER NOT NULL DEFAULT 1
                CHECK (apply_to_new_subfolders IN (0, 1)),
            modified_at TEXT NOT NULL,
            UNIQUE(member_id, target_item_id)
        );

        CREATE INDEX IF NOT EXISTS ix_permission_rules_member
            ON permission_rules(member_id);

        CREATE TABLE IF NOT EXISTS permission_changes (
            change_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            member_id TEXT NOT NULL,
            member_email TEXT NOT NULL,
            folder_path TEXT NOT NULL,
            previous_level TEXT NOT NULL,
            new_level TEXT NOT NULL,
            previous_graph_access TEXT NOT NULL,
            new_graph_access TEXT NOT NULL,
            actor_email TEXT NOT NULL,
            occurred_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS ix_permission_changes_project
            ON permission_changes(project_id, occurred_at DESC);
        """,
    ),
    (
        3,
        """
        CREATE TABLE IF NOT EXISTS transfer_jobs (
            job_id TEXT PRIMARY KEY,
            direction TEXT NOT NULL CHECK (direction IN ('upload', 'download')),
            status TEXT NOT NULL CHECK (
                status IN ('queued', 'running', 'paused', 'completed', 'failed', 'cancelled')
            ),
            local_path TEXT NOT NULL,
            remote_name TEXT NOT NULL,
            remote_item_id TEXT,
            remote_parent_id TEXT,
            total_bytes INTEGER NOT NULL DEFAULT 0,
            transferred_bytes INTEGER NOT NULL DEFAULT 0,
            source_size INTEGER,
            source_mtime_ns INTEGER,
            session_secret BLOB,
            remote_etag TEXT,
            expected_hash TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS ix_transfer_jobs_queue
            ON transfer_jobs(status, created_at);
        """,
    ),
    (
        4,
        """
        CREATE TABLE IF NOT EXISTS sync_scopes (
            scope_id TEXT PRIMARY KEY,
            scope_type TEXT NOT NULL CHECK (scope_type IN ('drive', 'project')),
            remote_item_id TEXT,
            label TEXT NOT NULL,
            delta_link TEXT,
            initialized INTEGER NOT NULL DEFAULT 0 CHECK (initialized IN (0, 1)),
            last_synced_at TEXT
        );

        CREATE TABLE IF NOT EXISTS synced_items (
            scope_id TEXT NOT NULL REFERENCES sync_scopes(scope_id) ON DELETE CASCADE,
            item_id TEXT NOT NULL,
            name TEXT NOT NULL,
            parent_item_id TEXT,
            is_folder INTEGER NOT NULL CHECK (is_folder IN (0, 1)),
            etag TEXT,
            modified_at TEXT,
            modified_by TEXT NOT NULL,
            PRIMARY KEY(scope_id, item_id)
        );

        CREATE TABLE IF NOT EXISTS activity_events (
            event_id TEXT PRIMARY KEY,
            dedupe_key TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL CHECK (source IN ('local', 'graph', 'local+graph')),
            action TEXT NOT NULL,
            actor TEXT NOT NULL,
            target TEXT NOT NULL,
            scope_id TEXT NOT NULL,
            project_name TEXT,
            remote_item_id TEXT,
            occurred_at TEXT NOT NULL,
            details TEXT
        );

        CREATE INDEX IF NOT EXISTS ix_activity_events_time
            ON activity_events(occurred_at DESC);
        CREATE INDEX IF NOT EXISTS ix_activity_events_scope
            ON activity_events(scope_id, occurred_at DESC);
        """,
    ),
    (
        5,
        """
        CREATE TABLE IF NOT EXISTS document_metadata (
            item_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            file_name TEXT NOT NULL,
            status TEXT NOT NULL CHECK (
                status IN ('draft', 'in_review', 'approved', 'obsolete')
            ),
            revision TEXT NOT NULL,
            discipline_code TEXT,
            document_number TEXT,
            title TEXT,
            naming_enabled INTEGER NOT NULL DEFAULT 0 CHECK (naming_enabled IN (0, 1)),
            remote_etag TEXT,
            updated_at TEXT NOT NULL,
            updated_by TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS ix_document_metadata_project
            ON document_metadata(project_id, status, file_name COLLATE NOCASE);

        CREATE TABLE IF NOT EXISTS document_history (
            history_id TEXT PRIMARY KEY,
            item_id TEXT NOT NULL,
            project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
            previous_status TEXT,
            new_status TEXT NOT NULL,
            previous_revision TEXT,
            new_revision TEXT NOT NULL,
            previous_name TEXT,
            new_name TEXT NOT NULL,
            actor TEXT NOT NULL,
            occurred_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS ix_document_history_item
            ON document_history(item_id, occurred_at DESC);
        """,
    ),
)


class SqliteDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        return connection

    def _initialize(self) -> None:
        backup: Path | None = None
        try:
            with self._connect() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                applied = {
                    int(row["version"])
                    for row in connection.execute("SELECT version FROM schema_migrations")
                }
                pending = tuple(item for item in _MIGRATIONS if item[0] not in applied)
                if pending and applied:
                    backup = self._create_migration_backup(connection, max(applied))
                for version, script in pending:
                    connection.executescript(script)
                    connection.execute(
                        "INSERT INTO schema_migrations(version) VALUES (?)", (version,)
                    )
        except Exception:
            if backup:
                self._restore_migration_backup(backup)
            raise
        if backup:
            self._prune_migration_backups()

    @property
    def backup_dir(self) -> Path:
        return self.path.parent / "backups"

    def _create_migration_backup(
        self, connection: sqlite3.Connection, current_version: int
    ) -> Path:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        backup = self.backup_dir / f"{self.path.stem}-schema-v{current_version}-{stamp}.db"
        with sqlite3.connect(backup) as destination:
            connection.backup(destination)
        return backup

    def _restore_migration_backup(self, backup: Path) -> None:
        with sqlite3.connect(backup) as source, sqlite3.connect(self.path) as destination:
            source.backup(destination)
            destination.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def _prune_migration_backups(self, keep: int = 3) -> None:
        backups = sorted(
            self.backup_dir.glob(f"{self.path.stem}-schema-v*.db"),
            key=lambda candidate: candidate.stat().st_mtime_ns,
            reverse=True,
        )
        for obsolete in backups[keep:]:
            obsolete.unlink(missing_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
