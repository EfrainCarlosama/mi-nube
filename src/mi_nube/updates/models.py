from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UpdateManifest:
    schema: int
    version: str
    installer_url: str
    sha256: str
    size_bytes: int
    published_at: str
    release_notes: str
    signature: str


@dataclass(frozen=True, slots=True)
class UpdateCheckResult:
    available: bool
    current_version: str
    manifest: UpdateManifest
