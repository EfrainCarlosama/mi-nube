from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from mi_nube.app.runtime_config import load_bundled_config


def _default_data_dir() -> Path:
    base = os.getenv("LOCALAPPDATA")
    if base:
        return Path(base) / "MiNube"
    return Path.home() / ".mi_nube"


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    environment: str
    log_level: str
    data_dir: Path
    microsoft_client_id: str | None = None
    microsoft_tenant_id: str = "common"
    update_manifest_url: str | None = None

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def auth_dir(self) -> Path:
        return self.data_dir / "auth"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "mi_nube.db"

    @property
    def is_microsoft_configured(self) -> bool:
        return bool(self.microsoft_client_id)

    @classmethod
    def from_environment(cls, env_file: Path | None = None) -> Settings:
        load_dotenv(dotenv_path=env_file, override=False)
        bundled = load_bundled_config()
        data_dir_value = os.getenv("MI_NUBE_DATA_DIR")
        return cls(
            app_name="Mi Nube",
            environment=os.getenv("MI_NUBE_ENV", "development"),
            log_level=os.getenv("MI_NUBE_LOG_LEVEL", "INFO").upper(),
            data_dir=Path(data_dir_value).expanduser() if data_dir_value else _default_data_dir(),
            microsoft_client_id=(
                os.getenv("MICROSOFT_CLIENT_ID") or bundled.get("microsoft_client_id")
            ),
            microsoft_tenant_id=(
                os.getenv("MICROSOFT_TENANT_ID") or bundled.get("microsoft_tenant_id") or "common"
            ),
            update_manifest_url=(
                os.getenv("MI_NUBE_UPDATE_URL") or bundled.get("update_manifest_url")
            ),
        )
