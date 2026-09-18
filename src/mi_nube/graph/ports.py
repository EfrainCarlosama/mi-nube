from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from mi_nube.domain.models import (
    DeltaResult,
    DownloadDescriptor,
    DriveItem,
    DriveQuota,
    SharingPermission,
)


class GraphDriveClient(Protocol):
    """Operations supported by the personal OneDrive adapter."""

    def list_children(self, item_id: str | None = None) -> Sequence[DriveItem]: ...

    def search(self, query: str) -> Sequence[DriveItem]: ...

    def get_item(self, item_id: str) -> DriveItem: ...

    def get_quota(self) -> DriveQuota: ...

    def create_folder(self, parent_id: str | None, name: str) -> DriveItem: ...

    def upload_small_file(self, parent_id: str | None, source: Path) -> DriveItem: ...

    def upload_file(
        self,
        parent_id: str | None,
        source: Path,
        progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> DriveItem: ...

    def download_file(self, item_id: str, destination: Path) -> Path: ...

    def upload_file_persistent(
        self,
        parent_id: str | None,
        source: Path,
        *,
        session_url: str | None = None,
        transferred: int = 0,
        checkpoint: Callable[[str | None, int], None] | None = None,
        progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> DriveItem: ...

    def discard_upload_session(self, upload_url: str) -> None: ...

    def get_download_descriptor(self, item_id: str) -> DownloadDescriptor: ...

    def download_to_part(
        self,
        descriptor: DownloadDescriptor,
        part_path: Path,
        *,
        progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> int: ...

    def rename_item(self, item_id: str, new_name: str, etag: str | None = None) -> DriveItem: ...

    def move_item(self, item_id: str, parent_id: str | None) -> DriveItem: ...

    def delete_item(self, item_id: str, etag: str | None = None) -> None: ...

    def invite_user(
        self,
        item_id: str,
        email: str,
        role: str,
        *,
        send_invitation: bool = True,
        message: str = "",
    ) -> SharingPermission: ...

    def list_permissions(self, item_id: str) -> Sequence[SharingPermission]: ...

    def delete_permission(self, item_id: str, permission_id: str) -> None: ...

    def delta(
        self,
        item_id: str | None = None,
        *,
        delta_link: str | None = None,
        latest: bool = False,
    ) -> DeltaResult: ...
