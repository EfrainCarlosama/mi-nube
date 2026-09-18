from __future__ import annotations

import argparse
from pathlib import Path
from uuid import uuid4

from mi_nube.app.settings import Settings
from mi_nube.auth.msal_service import MsalAuthService
from mi_nube.auth.token_cache import create_token_cache_store
from mi_nube.graph.http_client import HttpGraphDriveClient


def validate(source: Path) -> None:
    settings = Settings.from_environment()
    auth = MsalAuthService(
        settings.microsoft_client_id,
        settings.microsoft_tenant_id,
        create_token_cache_store(settings.auth_dir),
    )
    if auth.current_profile() is None:
        raise RuntimeError("No hay una sesión de Microsoft restaurada.")

    client = HttpGraphDriveClient(auth)
    folder = None
    last_percent = -1

    def show_progress(done: int, total: int) -> None:
        nonlocal last_percent
        percent = round(done * 100 / total) if total else 100
        if percent != last_percent:
            print(f"Progreso: {percent}% ({done}/{total} bytes)", flush=True)
            last_percent = percent

    try:
        folder = client.create_folder(None, f"MiNube-Validacion-{uuid4().hex[:8]}")
        uploaded = client.upload_file(folder.item_id, source, show_progress)
        remote = client.get_item(uploaded.item_id)
        if remote.size_bytes != source.stat().st_size:
            raise RuntimeError(
                f"El tamaño remoto no coincide: {remote.size_bytes} != {source.stat().st_size}"
            )
        print(f"Validado: {remote.size_bytes} bytes.", flush=True)
    finally:
        if folder is not None:
            client.delete_item(folder.item_id)
            print("Carpeta temporal enviada a la papelera de OneDrive.", flush=True)
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Valida una Upload Session contra OneDrive.")
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    validate(source)


if __name__ == "__main__":
    main()
