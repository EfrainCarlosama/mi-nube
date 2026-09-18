from __future__ import annotations

from pathlib import Path

import pytest

from mi_nube.database.sqlite import SqliteDatabase
from mi_nube.domain.models import TransferStatus
from mi_nube.graph.errors import GraphUploadCancelled
from mi_nube.repositories.transfer_repository import SqliteTransferRepository
from mi_nube.services.transfer_service import TransferService


class ReverseProtector:
    def protect(self, data: bytes) -> bytes:
        return data[::-1]

    def unprotect(self, data: bytes) -> bytes:
        return data[::-1]


class PausingUploadClient:
    def __init__(self) -> None:
        self.received_session: str | None = None

    def upload_file_persistent(
        self,
        parent_id,
        source,
        *,
        session_url=None,
        transferred=0,
        checkpoint=None,
        progress=None,
        is_cancelled=None,
    ):
        self.received_session = session_url
        checkpoint("https://my.microsoftpersonalcontent.com/upload/secret", 5)
        progress(5, source.stat().st_size)
        raise GraphUploadCancelled("La transferencia fue pausada.")


def test_upload_checkpoint_is_encrypted_and_can_be_requeued(tmp_path: Path) -> None:
    source = tmp_path / "modelo.rvt"
    source.write_bytes(b"1234567890")
    repository = SqliteTransferRepository(SqliteDatabase(tmp_path / "app.db"))
    client = PausingUploadClient()
    service = TransferService(client, repository, ReverseProtector())
    job = service.queue_upload("folder", source)

    with pytest.raises(GraphUploadCancelled):
        service.process(job, lambda _done, _total: None, lambda: False)

    paused = repository.get(job.job_id)
    assert paused is not None
    assert paused.status == TransferStatus.PAUSED
    assert paused.transferred_bytes == 5
    assert paused.session_secret is not None
    assert b"https://" not in paused.session_secret

    service.retry(job.job_id)
    queued = repository.next_queued()
    assert queued is not None
    with pytest.raises(GraphUploadCancelled):
        service.process(queued, lambda _done, _total: None, lambda: False)
    assert client.received_session == "https://my.microsoftpersonalcontent.com/upload/secret"


def test_database_recovers_running_transfer_after_restart(tmp_path: Path) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    database = SqliteDatabase(tmp_path / "app.db")
    repository = SqliteTransferRepository(database)
    service = TransferService(PausingUploadClient(), repository, ReverseProtector())
    job = service.queue_upload(None, source)
    repository.update(job, status=TransferStatus.RUNNING)

    assert service.recover_interrupted() == 1
    recovered = repository.get(job.job_id)
    assert recovered is not None
    assert recovered.status == TransferStatus.QUEUED
