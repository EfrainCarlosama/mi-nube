from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from mi_nube.auth.token_cache import DataProtector
from mi_nube.domain.models import TransferDirection, TransferJob, TransferStatus
from mi_nube.graph.errors import GraphError, GraphServiceError, GraphUploadCancelled
from mi_nube.graph.ports import GraphDriveClient
from mi_nube.repositories.transfer_repository import SqliteTransferRepository
from mi_nube.services.integrity import quick_xor_hash, sha1_hash


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TransferService:
    def __init__(
        self,
        client: GraphDriveClient,
        repository: SqliteTransferRepository,
        protector: DataProtector,
    ) -> None:
        self._client = client
        self._repository = repository
        self._protector = protector

    def recover_interrupted(self) -> int:
        return self._repository.recover_interrupted()

    def list_jobs(self) -> tuple[TransferJob, ...]:
        return self._repository.list_recent()

    def next_queued(self) -> TransferJob | None:
        return self._repository.next_queued()

    def queue_upload(self, parent_id: str | None, source: Path) -> TransferJob:
        stat = source.stat()
        now = _utcnow()
        return self._repository.save(
            TransferJob(
                job_id=str(uuid4()),
                direction=TransferDirection.UPLOAD,
                status=TransferStatus.QUEUED,
                local_path=str(source.resolve()),
                remote_name=source.name,
                remote_item_id=None,
                remote_parent_id=parent_id,
                total_bytes=stat.st_size,
                transferred_bytes=0,
                source_size=stat.st_size,
                source_mtime_ns=stat.st_mtime_ns,
                session_secret=None,
                remote_etag=None,
                expected_hash=None,
                error_message=None,
                created_at=now,
                updated_at=now,
            )
        )

    def queue_download(
        self, item_id: str, remote_name: str, size_bytes: int, destination: Path
    ) -> TransferJob:
        now = _utcnow()
        return self._repository.save(
            TransferJob(
                job_id=str(uuid4()),
                direction=TransferDirection.DOWNLOAD,
                status=TransferStatus.QUEUED,
                local_path=str(destination.resolve()),
                remote_name=remote_name,
                remote_item_id=item_id,
                remote_parent_id=None,
                total_bytes=size_bytes,
                transferred_bytes=0,
                source_size=None,
                source_mtime_ns=None,
                session_secret=None,
                remote_etag=None,
                expected_hash=None,
                error_message=None,
                created_at=now,
                updated_at=now,
            )
        )

    def retry(self, job_id: str) -> TransferJob | None:
        job = self._repository.get(job_id)
        if job is None or job.status not in {
            TransferStatus.PAUSED,
            TransferStatus.FAILED,
            TransferStatus.CANCELLED,
        }:
            return job
        return self._repository.update(job, status=TransferStatus.QUEUED, error_message=None)

    def cancel(self, job_id: str) -> TransferJob | None:
        job = self._repository.get(job_id)
        if job is None or job.status == TransferStatus.COMPLETED:
            return job
        if job.direction == TransferDirection.UPLOAD and job.session_secret:
            with suppress(GraphError, OSError, UnicodeError):
                self._client.discard_upload_session(
                    self._protector.unprotect(job.session_secret).decode("utf-8")
                )
        if job.direction == TransferDirection.DOWNLOAD:
            self._part_path(job).unlink(missing_ok=True)
        return self._repository.update(
            job,
            status=TransferStatus.CANCELLED,
            session_secret=None,
            transferred_bytes=0,
            error_message=None,
        )

    @staticmethod
    def _part_path(job: TransferJob) -> Path:
        destination = Path(job.local_path)
        return destination.with_name(f".{destination.name}.{job.job_id}.part")

    def _session_url(self, job: TransferJob) -> str | None:
        if not job.session_secret:
            return None
        try:
            return self._protector.unprotect(job.session_secret).decode("utf-8")
        except (OSError, UnicodeError, ValueError):
            return None

    def process(
        self,
        job: TransferJob,
        progress: Callable[[int, int], None],
        is_cancelled: Callable[[], bool],
    ) -> TransferJob:
        current = self._repository.update(job, status=TransferStatus.RUNNING, error_message=None)
        try:
            if current.direction == TransferDirection.UPLOAD:
                current = self._process_upload(current, progress, is_cancelled)
            else:
                current = self._process_download(current, progress, is_cancelled)
            return self._repository.update(
                current,
                status=TransferStatus.COMPLETED,
                transferred_bytes=current.total_bytes,
                session_secret=None,
                error_message=None,
            )
        except GraphUploadCancelled:
            current = self._repository.get(job.job_id) or current
            self._repository.update(current, status=TransferStatus.PAUSED)
            raise
        except (GraphError, OSError, ValueError) as error:
            current = self._repository.get(job.job_id) or current
            self._repository.update(current, status=TransferStatus.FAILED, error_message=str(error))
            raise

    def _process_upload(
        self,
        job: TransferJob,
        progress: Callable[[int, int], None],
        is_cancelled: Callable[[], bool],
    ) -> TransferJob:
        source = Path(job.local_path)
        stat = source.stat()
        if stat.st_size != job.source_size or stat.st_mtime_ns != job.source_mtime_ns:
            raise GraphServiceError(
                "El archivo local cambió desde que se añadió a la cola. Añádelo nuevamente."
            )
        current = job

        def checkpoint(url: str | None, offset: int) -> None:
            nonlocal current
            secret = self._protector.protect(url.encode("utf-8")) if url else None
            current = self._repository.update(
                current,
                session_secret=secret,
                transferred_bytes=offset,
                total_bytes=stat.st_size,
            )

        self._client.upload_file_persistent(
            job.remote_parent_id,
            source,
            session_url=self._session_url(job),
            transferred=job.transferred_bytes,
            checkpoint=checkpoint,
            progress=progress,
            is_cancelled=is_cancelled,
        )
        return current

    def _process_download(
        self,
        job: TransferJob,
        progress: Callable[[int, int], None],
        is_cancelled: Callable[[], bool],
    ) -> TransferJob:
        if not job.remote_item_id:
            raise GraphServiceError("La descarga no tiene un archivo remoto asociado.")
        descriptor = self._client.get_download_descriptor(job.remote_item_id)
        part_path = self._part_path(job)
        if job.remote_etag and descriptor.etag and job.remote_etag != descriptor.etag:
            part_path.unlink(missing_ok=True)
        expected_hash = None
        if descriptor.quick_xor_hash:
            expected_hash = f"quickxor:{descriptor.quick_xor_hash}"
        elif descriptor.sha1_hash:
            expected_hash = f"sha1:{descriptor.sha1_hash}"
        current = self._repository.update(
            job,
            total_bytes=descriptor.size_bytes,
            remote_etag=descriptor.etag,
            expected_hash=expected_hash,
            transferred_bytes=part_path.stat().st_size if part_path.exists() else 0,
        )
        written = self._client.download_to_part(
            descriptor,
            part_path,
            progress=lambda done, total: self._download_checkpoint(
                current.job_id, done, total, progress
            ),
            is_cancelled=is_cancelled,
        )
        if written != descriptor.size_bytes:
            raise GraphServiceError(
                f"La descarga quedó incompleta ({written} de {descriptor.size_bytes} bytes)."
            )
        if descriptor.quick_xor_hash:
            actual = quick_xor_hash(part_path)
            if actual != descriptor.quick_xor_hash:
                raise GraphServiceError("La verificación QuickXorHash de la descarga falló.")
        elif descriptor.sha1_hash:
            actual = sha1_hash(part_path)
            if actual.casefold() != descriptor.sha1_hash.casefold():
                raise GraphServiceError("La verificación SHA-1 de la descarga falló.")
        destination = Path(job.local_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(part_path, destination)
        return self._repository.get(job.job_id) or current

    def _download_checkpoint(
        self,
        job_id: str,
        done: int,
        total: int,
        notify: Callable[[int, int], None],
    ) -> None:
        job = self._repository.get(job_id)
        if job:
            self._repository.update(job, transferred_bytes=done, total_bytes=total)
        notify(done, total)
