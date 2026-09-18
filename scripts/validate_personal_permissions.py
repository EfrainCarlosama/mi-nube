from __future__ import annotations

from collections import Counter

from mi_nube.app.settings import Settings
from mi_nube.auth.msal_service import MsalAuthService
from mi_nube.auth.token_cache import create_token_cache_store
from mi_nube.graph.http_client import HttpGraphDriveClient
from mi_nube.services.project_service import WORK_ROOT_NAME


def main() -> None:
    settings = Settings.from_environment()
    auth = MsalAuthService(
        settings.microsoft_client_id,
        settings.microsoft_tenant_id,
        create_token_cache_store(settings.auth_dir),
    )
    if auth.current_profile() is None:
        raise RuntimeError("No hay una sesión de Microsoft restaurada.")
    client = HttpGraphDriveClient(auth)
    try:
        work_root = next(
            item
            for item in client.list_children(None)
            if item.is_folder and item.name.casefold() == WORK_ROOT_NAME.casefold()
        )
        permissions = client.list_permissions(work_root.item_id)
        role_counts = Counter(role for permission in permissions for role in permission.roles)
        inherited = sum(permission.inherited for permission in permissions)
        print(
            f"Validado: {len(permissions)} permisos; roles={dict(role_counts)}; "
            f"heredados={inherited}",
            flush=True,
        )
    finally:
        client.close()


if __name__ == "__main__":
    main()
