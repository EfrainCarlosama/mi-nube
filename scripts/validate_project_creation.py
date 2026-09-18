from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

from mi_nube.app.settings import Settings
from mi_nube.auth.msal_service import MsalAuthService
from mi_nube.auth.token_cache import create_token_cache_store
from mi_nube.database.sqlite import SqliteDatabase
from mi_nube.graph.http_client import HttpGraphDriveClient
from mi_nube.repositories.project_repository import SqliteProjectRepository
from mi_nube.services.project_service import ProjectService


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
    project = None
    with tempfile.TemporaryDirectory(prefix="mi-nube-project-validation-") as temporary_dir:
        repository = SqliteProjectRepository(SqliteDatabase(Path(temporary_dir) / "validation.db"))
        service = ProjectService(client, repository)

        def show_progress(done: int, total: int, label: str) -> None:
            if done == 1 or done == total or done % 10 == 0:
                print(f"Progreso: {done}/{total} — {label}", flush=True)

        try:
            project = service.create_project(
                f"Validación Módulo 4 {uuid4().hex[:8]}",
                "Prueba automática",
                progress=show_progress,
            )
            top_level = client.list_children(project.remote_item_id)
            records = repository.list_folders(project.project_id)
            expected = ProjectService._count_folders(service.default_template().folders)
            if len(top_level) != 9:
                raise RuntimeError(
                    f"Se esperaban 9 carpetas principales y se obtuvieron {len(top_level)}"
                )
            if len(records) != expected:
                raise RuntimeError(
                    f"Se esperaban {expected} registros y se obtuvieron {len(records)}"
                )
            structures = next(
                folder for folder in records if folder.relative_path == "02 Estructuras"
            )
            child_names = {item.name for item in client.list_children(structures.remote_item_id)}
            if {"Planos", "Cálculos", "Memorias", "ETABS", "SAFE", "Revit"} != child_names:
                raise RuntimeError("La estructura remota de ingeniería no coincide.")
            print(
                f"Validado: 9 carpetas principales y {len(records)} carpetas registradas.",
                flush=True,
            )
        finally:
            if project is not None:
                client.delete_item(project.remote_item_id)
                print("Proyecto temporal enviado a la papelera de OneDrive.", flush=True)
            client.close()


if __name__ == "__main__":
    main()
