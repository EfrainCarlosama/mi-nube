from __future__ import annotations

import sqlite3

import pytest

import mi_nube.database.sqlite as sqlite_module
from mi_nube.database.sqlite import SqliteDatabase


def test_failed_migration_restores_previous_database(monkeypatch, tmp_path) -> None:
    path = tmp_path / "mi-nube.db"
    database = SqliteDatabase(path)
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO projects(
                project_id, name, client, remote_item_id, template_version,
                created_at, modified_at
            ) VALUES ('p1', 'Casa', 'Cliente', 'remote', 1, 'now', 'now')
            """
        )

    broken = (*sqlite_module._MIGRATIONS, (999, "CREATE TABLE invalid SQL"))
    monkeypatch.setattr(sqlite_module, "_MIGRATIONS", broken)
    with pytest.raises(sqlite3.OperationalError):
        SqliteDatabase(path)

    with sqlite3.connect(path) as connection:
        assert (
            connection.execute("SELECT name FROM projects WHERE project_id = 'p1'").fetchone()[0]
            == "Casa"
        )
        versions = [row[0] for row in connection.execute("SELECT version FROM schema_migrations")]
    assert versions == [1, 2, 3, 4, 5]
    assert len(tuple((tmp_path / "backups").glob("*.db"))) == 1
