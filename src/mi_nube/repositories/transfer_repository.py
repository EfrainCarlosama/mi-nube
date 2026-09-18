from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from mi_nube.database.sqlite import SqliteDatabase
from mi_nube.domain.models import TransferDirection, TransferJob, TransferStatus


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SqliteTransferRepository:
    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    @staticmethod
    def _map(row) -> TransferJob:
        return TransferJob(
            job_id=str(row["job_id"]),
            direction=TransferDirection(row["direction"]),
            status=TransferStatus(row["status"]),
            local_path=str(row["local_path"]),
            remote_name=str(row["remote_name"]),
            remote_item_id=row["remote_item_id"],
            remote_parent_id=row["remote_parent_id"],
            total_bytes=int(row["total_bytes"]),
            transferred_bytes=int(row["transferred_bytes"]),
            source_size=row["source_size"],
            source_mtime_ns=row["source_mtime_ns"],
            session_secret=bytes(row["session_secret"]) if row["session_secret"] else None,
            remote_etag=row["remote_etag"],
            expected_hash=row["expected_hash"],
            error_message=row["error_message"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def save(self, job: TransferJob) -> TransferJob:
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO transfer_jobs (
                    job_id, direction, status, local_path, remote_name, remote_item_id,
                    remote_parent_id, total_bytes, transferred_bytes, source_size,
                    source_mtime_ns, session_secret, remote_etag, expected_hash,
                    error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status=excluded.status,
                    transferred_bytes=excluded.transferred_bytes,
                    total_bytes=excluded.total_bytes,
                    session_secret=excluded.session_secret,
                    remote_etag=excluded.remote_etag,
                    expected_hash=excluded.expected_hash,
                    error_message=excluded.error_message,
                    updated_at=excluded.updated_at
                """,
                (
                    job.job_id,
                    job.direction.value,
                    job.status.value,
                    job.local_path,
                    job.remote_name,
                    job.remote_item_id,
                    job.remote_parent_id,
                    job.total_bytes,
                    job.transferred_bytes,
                    job.source_size,
                    job.source_mtime_ns,
                    job.session_secret,
                    job.remote_etag,
                    job.expected_hash,
                    job.error_message,
                    job.created_at.isoformat(),
                    job.updated_at.isoformat(),
                ),
            )
        return job

    def update(self, job: TransferJob, **changes) -> TransferJob:
        updated = replace(job, updated_at=_utcnow(), **changes)
        return self.save(updated)

    def get(self, job_id: str) -> TransferJob | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM transfer_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return self._map(row) if row else None

    def list_recent(self, limit: int = 100) -> tuple[TransferJob, ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM transfer_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return tuple(self._map(row) for row in rows)

    def next_queued(self) -> TransferJob | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM transfer_jobs
                WHERE status = 'queued'
                ORDER BY created_at ASC LIMIT 1
                """
            ).fetchone()
        return self._map(row) if row else None

    def recover_interrupted(self) -> int:
        now = _utcnow().isoformat()
        with self._database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE transfer_jobs
                SET status = 'queued', error_message = NULL, updated_at = ?
                WHERE status = 'running'
                """,
                (now,),
            )
        return cursor.rowcount
