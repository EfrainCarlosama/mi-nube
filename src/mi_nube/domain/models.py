from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class StorageSummary:
    used_bytes: int
    total_bytes: int

    @property
    def ratio(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return min(max(self.used_bytes / self.total_bytes, 0.0), 1.0)


@dataclass(frozen=True, slots=True)
class ProjectSummary:
    project_id: str
    name: str
    client: str
    modified_at: datetime
    item_count: int
    accent: str


@dataclass(frozen=True, slots=True)
class ActivityItem:
    actor: str
    action: str
    target: str
    occurred_at: datetime
    project: str | None = None


@dataclass(frozen=True, slots=True)
class FileItem:
    name: str
    kind: str
    size_bytes: int | None
    modified_at: datetime
    path: str
    status: str | None = None


@dataclass(frozen=True, slots=True)
class AccountProfile:
    user_id: str
    display_name: str
    email: str
    tenant_id: str | None = None


@dataclass(frozen=True, slots=True)
class DriveItem:
    item_id: str
    name: str
    is_folder: bool
    size_bytes: int
    modified_at: datetime | None
    modified_by: str
    parent_path: str
    web_url: str | None = None
    mime_type: str | None = None
    etag: str | None = None
    child_count: int | None = None


@dataclass(frozen=True, slots=True)
class DriveQuota:
    used_bytes: int
    total_bytes: int
    remaining_bytes: int
    state: str

    @property
    def ratio(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return min(max(self.used_bytes / self.total_bytes, 0.0), 1.0)


@dataclass(frozen=True, slots=True)
class Project:
    project_id: str
    name: str
    client: str
    remote_item_id: str
    template_version: int
    created_at: datetime
    modified_at: datetime


@dataclass(frozen=True, slots=True)
class ProjectFolder:
    folder_id: str
    project_id: str
    remote_item_id: str
    parent_folder_id: str | None
    name: str
    relative_path: str
    sort_order: int


@dataclass(frozen=True, slots=True)
class TemplateFolder:
    name: str
    children: tuple[TemplateFolder, ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectTemplate:
    template_id: str
    name: str
    version: int
    folders: tuple[TemplateFolder, ...]


@dataclass(frozen=True, slots=True)
class SharingPermission:
    permission_id: str
    roles: tuple[str, ...]
    grantee_name: str | None = None
    grantee_email: str | None = None
    inherited: bool = False


@dataclass(frozen=True, slots=True)
class ProjectMember:
    member_id: str
    project_id: str
    email: str
    display_name: str
    role: str
    created_at: datetime
    modified_at: datetime


@dataclass(frozen=True, slots=True)
class FolderPermissionRule:
    rule_id: str
    member_id: str
    project_id: str
    folder_id: str | None
    target_item_id: str
    level: str
    capabilities: int
    graph_access: str
    graph_permission_id: str | None
    apply_to_new_subfolders: bool
    modified_at: datetime


@dataclass(frozen=True, slots=True)
class PermissionChange:
    change_id: str
    project_id: str
    member_id: str
    member_email: str
    folder_path: str
    previous_level: str
    new_level: str
    previous_graph_access: str
    new_graph_access: str
    actor_email: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class PermissionEditorData:
    member: ProjectMember
    folders: tuple[ProjectFolder, ...]
    rules: tuple[FolderPermissionRule, ...]


class TransferDirection(StrEnum):
    UPLOAD = "upload"
    DOWNLOAD = "download"


class TransferStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class TransferJob:
    job_id: str
    direction: TransferDirection
    status: TransferStatus
    local_path: str
    remote_name: str
    remote_item_id: str | None
    remote_parent_id: str | None
    total_bytes: int
    transferred_bytes: int
    source_size: int | None
    source_mtime_ns: int | None
    session_secret: bytes | None
    remote_etag: str | None
    expected_hash: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DownloadDescriptor:
    item_id: str
    name: str
    size_bytes: int
    etag: str | None
    download_url: str
    quick_xor_hash: str | None
    sha1_hash: str | None


@dataclass(frozen=True, slots=True)
class DeltaChange:
    item_id: str
    name: str
    parent_item_id: str | None
    is_folder: bool
    is_deleted: bool
    etag: str | None
    created_at: datetime | None
    modified_at: datetime | None
    modified_by: str


@dataclass(frozen=True, slots=True)
class DeltaResult:
    changes: tuple[DeltaChange, ...]
    delta_link: str


@dataclass(frozen=True, slots=True)
class SyncScope:
    scope_id: str
    scope_type: str
    remote_item_id: str | None
    label: str
    delta_link: str | None
    initialized: bool
    last_synced_at: datetime | None


@dataclass(frozen=True, slots=True)
class SyncedItem:
    scope_id: str
    item_id: str
    name: str
    parent_item_id: str | None
    is_folder: bool
    etag: str | None
    modified_at: datetime | None
    modified_by: str


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    event_id: str
    source: str
    action: str
    actor: str
    target: str
    scope_id: str
    project_name: str | None
    remote_item_id: str | None
    occurred_at: datetime
    details: str | None = None


@dataclass(frozen=True, slots=True)
class SyncSummary:
    scopes_synced: int
    changes_received: int
    events_created: int
    baselines_created: int
    synced_at: datetime


class DocumentStatus(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    OBSOLETE = "obsolete"

    @property
    def label(self) -> str:
        return {
            self.DRAFT: "Borrador",
            self.IN_REVIEW: "En revisión",
            self.APPROVED: "Aprobado",
            self.OBSOLETE: "Obsoleto",
        }[self]


@dataclass(frozen=True, slots=True)
class DocumentMetadata:
    item_id: str
    project_id: str
    file_name: str
    status: DocumentStatus
    revision: str
    discipline_code: str | None
    document_number: str | None
    title: str | None
    naming_enabled: bool
    remote_etag: str | None
    updated_at: datetime
    updated_by: str


@dataclass(frozen=True, slots=True)
class DocumentHistory:
    history_id: str
    item_id: str
    project_id: str
    previous_status: DocumentStatus | None
    new_status: DocumentStatus
    previous_revision: str | None
    new_revision: str
    previous_name: str | None
    new_name: str
    actor: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class DocumentReport:
    project_id: str
    documents: tuple[DocumentMetadata, ...]
    counts: dict[DocumentStatus, int]
