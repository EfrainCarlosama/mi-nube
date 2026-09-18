from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

import httpx
from packaging.version import InvalidVersion, Version

from mi_nube.updates.errors import UpdateError
from mi_nube.updates.manifest import parse_and_verify_manifest
from mi_nube.updates.models import UpdateCheckResult, UpdateManifest

_MAX_MANIFEST_BYTES = 256 * 1024
_MAX_INSTALLER_BYTES = 1024**3


class UpdateService:
    def __init__(
        self,
        current_version: str,
        manifest_url: str,
        public_key_pem: bytes,
        download_dir: Path,
        client: httpx.Client | None = None,
    ) -> None:
        self._current_version = current_version
        self._manifest_url = self._validated_https_url(manifest_url, "manifiesto")
        self._public_key_pem = public_key_pem
        self._download_dir = download_dir
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(30, read=60), follow_redirects=False
        )
        self._owns_client = client is None

    @staticmethod
    def _validated_https_url(value: str, label: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise UpdateError(f"La URL de {label} debe usar HTTPS y no contener credenciales.")
        return value

    def check(self) -> UpdateCheckResult:
        try:
            response = self._client.get(self._manifest_url)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise UpdateError("No se pudo consultar el canal de actualizaciones.") from error
        content = response.content
        if len(content) > _MAX_MANIFEST_BYTES:
            raise UpdateError("El manifiesto de actualización supera el tamaño permitido.")
        manifest = parse_and_verify_manifest(content, self._public_key_pem)
        self._validated_https_url(manifest.installer_url, "instalador")
        try:
            available = Version(manifest.version) > Version(self._current_version)
        except InvalidVersion as error:
            raise UpdateError("El manifiesto contiene una versión inválida.") from error
        return UpdateCheckResult(available, self._current_version, manifest)

    def download(
        self,
        manifest: UpdateManifest,
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        if manifest.size_bytes > _MAX_INSTALLER_BYTES:
            raise UpdateError("El instalador declarado supera el límite de seguridad.")
        url = self._validated_https_url(manifest.installer_url, "instalador")
        self._download_dir.mkdir(parents=True, exist_ok=True)
        destination = self._download_dir / f"MiNubeSetup-{manifest.version}.exe"
        partial = destination.with_suffix(".download")
        digest = hashlib.sha256()
        received = 0
        try:
            with self._client.stream("GET", url) as response:
                response.raise_for_status()
                with partial.open("wb") as target:
                    for chunk in response.iter_bytes(1024 * 1024):
                        received += len(chunk)
                        if received > manifest.size_bytes or received > _MAX_INSTALLER_BYTES:
                            raise UpdateError("La descarga supera el tamaño firmado.")
                        target.write(chunk)
                        digest.update(chunk)
                        if progress:
                            progress(received, manifest.size_bytes)
                    target.flush()
                    os.fsync(target.fileno())
        except httpx.HTTPError as error:
            partial.unlink(missing_ok=True)
            raise UpdateError("No se pudo descargar el instalador.") from error
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        if received != manifest.size_bytes or digest.hexdigest() != manifest.sha256:
            partial.unlink(missing_ok=True)
            raise UpdateError("El instalador descargado no coincide con el manifiesto firmado.")
        os.replace(partial, destination)
        return destination

    @staticmethod
    def launch_installer(installer: Path) -> None:
        if sys.platform != "win32" or not installer.is_file():
            raise UpdateError("El instalador de Windows no está disponible.")
        try:
            subprocess.Popen(
                [str(installer), "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
                close_fds=True,
            )
        except OSError as error:
            raise UpdateError("Windows no pudo iniciar el instalador.") from error

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
