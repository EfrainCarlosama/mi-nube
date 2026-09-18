from __future__ import annotations

import logging
import os
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from mi_nube.auth.ports import AuthService
from mi_nube.domain.models import (
    DeltaChange,
    DeltaResult,
    DownloadDescriptor,
    DriveItem,
    DriveQuota,
    SharingPermission,
)
from mi_nube.graph.errors import (
    GraphAuthenticationError,
    GraphConflictError,
    GraphDeltaResetRequired,
    GraphError,
    GraphNetworkError,
    GraphNotFoundError,
    GraphPermissionError,
    GraphServiceError,
    GraphThrottledError,
    GraphUploadCancelled,
    GraphValidationError,
)

LOGGER = logging.getLogger(__name__)
GRAPH_SCOPES = ("Files.ReadWrite", "User.Read")
MIB = 1024 * 1024
SIMPLE_UPLOAD_THRESHOLD = 10 * MIB
SMALL_UPLOAD_LIMIT = 250 * MIB
MAX_UPLOAD_SIZE = 250 * 1024 * MIB
UPLOAD_CHUNK_SIZE = 10 * MIB
_TRANSIENT_STATUSES = {429, 500, 502, 503, 504}


class HttpGraphDriveClient:
    def __init__(
        self,
        auth_service: AuthService,
        http_client: httpx.Client | None = None,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._auth_service = auth_service
        self._client = http_client or httpx.Client(
            base_url="https://graph.microsoft.com/v1.0",
            timeout=httpx.Timeout(30, connect=10),
            follow_redirects=True,
        )
        self._owns_client = http_client is None
        self._max_retries = max_retries
        self._sleep = sleep
        self._drive_id: str | None = None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _headers(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        token = self._auth_service.acquire_access_token(GRAPH_SCOPES)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _validate_url(url: str) -> str:
        if url.startswith("/"):
            return url
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "graph.microsoft.com"
            or parsed.port not in {None, 443}
            or parsed.username is not None
        ):
            raise GraphServiceError("Microsoft Graph devolvió un enlace de paginación no válido.")
        return url

    @staticmethod
    def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
        if response is not None:
            value = response.headers.get("Retry-After")
            if value:
                try:
                    return min(max(float(value), 0.0), 60.0)
                except ValueError:
                    pass
        return min(float(2**attempt), 30.0)

    def _request(
        self,
        method: str,
        url: str,
        *,
        before_attempt: Callable[[], None] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        safe_url = self._validate_url(url)
        extra_headers = kwargs.pop("extra_headers", None)
        for attempt in range(self._max_retries + 1):
            if before_attempt:
                before_attempt()
            try:
                response = self._client.request(
                    method,
                    safe_url,
                    headers=self._headers(extra_headers),
                    **kwargs,
                )
            except (httpx.TimeoutException, httpx.TransportError) as error:
                if attempt >= self._max_retries:
                    LOGGER.warning("Microsoft Graph no está disponible: %s", type(error).__name__)
                    raise GraphNetworkError(
                        "No se pudo conectar con OneDrive. Comprueba tu conexión a Internet."
                    ) from error
                self._sleep(self._retry_delay(None, attempt))
                continue

            if response.status_code in _TRANSIENT_STATUSES and attempt < self._max_retries:
                delay = self._retry_delay(response, attempt)
                LOGGER.info(
                    "Reintentando Microsoft Graph tras HTTP %s en %.1f s",
                    response.status_code,
                    delay,
                )
                self._sleep(delay)
                continue
            if response.is_success:
                return response
            self._raise_for_response(response)
        raise GraphServiceError("Microsoft Graph no completó la solicitud.")

    @staticmethod
    def _error_details(response: httpx.Response) -> tuple[str, str]:
        try:
            payload = response.json()
        except ValueError:
            return "unknownError", "Microsoft Graph devolvió una respuesta no válida."
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        if not isinstance(error, dict):
            return "unknownError", "Microsoft Graph no completó la operación."
        return str(error.get("code") or "unknownError"), str(
            error.get("message") or "Microsoft Graph no completó la operación."
        )

    @classmethod
    def _raise_for_response(cls, response: httpx.Response) -> None:
        code, message = cls._error_details(response)
        request_id = response.headers.get("request-id") or response.headers.get("client-request-id")
        LOGGER.warning(
            "Error Microsoft Graph HTTP %s code=%s request_id=%s",
            response.status_code,
            code,
            request_id,
        )
        status = response.status_code
        if status == 401:
            raise GraphAuthenticationError("La sesión expiró. Inicia sesión nuevamente.")
        if status == 403:
            raise GraphPermissionError(
                "Tu cuenta no tiene permiso para realizar esta operación en OneDrive."
            )
        if status == 404:
            raise GraphNotFoundError("El archivo o carpeta ya no existe en OneDrive.")
        if status == 410:
            raise GraphDeltaResetRequired(
                "El cursor de sincronización expiró y debe crearse nuevamente."
            )
        if status in {409, 412}:
            raise GraphConflictError(
                "El elemento cambió o ya existe otro con el mismo nombre. "
                "Actualiza e inténtalo de nuevo."
            )
        if status == 429:
            raise GraphThrottledError(
                "OneDrive está recibiendo demasiadas solicitudes. "
                "Inténtalo nuevamente en unos minutos."
            )
        if status >= 500:
            raise GraphServiceError("OneDrive no está disponible temporalmente.")
        raise GraphError(f"Microsoft Graph rechazó la operación: {message} [{code}]")

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    @classmethod
    def _parse_item(cls, payload: Mapping[str, Any]) -> DriveItem:
        modified_identity = payload.get("lastModifiedBy") or {}
        user = modified_identity.get("user") or modified_identity.get("application") or {}
        parent = payload.get("parentReference") or {}
        folder = payload.get("folder")
        file_data = payload.get("file") or {}
        return DriveItem(
            item_id=str(payload.get("id") or ""),
            name=str(payload.get("name") or "Sin nombre"),
            is_folder=isinstance(folder, Mapping),
            size_bytes=int(payload.get("size") or 0),
            modified_at=cls._parse_datetime(payload.get("lastModifiedDateTime")),
            modified_by=str(user.get("displayName") or "—"),
            parent_path=str(parent.get("path") or ""),
            web_url=str(payload["webUrl"]) if payload.get("webUrl") else None,
            mime_type=str(file_data["mimeType"]) if file_data.get("mimeType") else None,
            etag=str(payload["eTag"]) if payload.get("eTag") else None,
            child_count=int(folder.get("childCount", 0)) if isinstance(folder, Mapping) else None,
        )

    def _paged_items(self, url: str) -> tuple[DriveItem, ...]:
        items: list[DriveItem] = []
        next_url: str | None = url
        while next_url:
            response = self._request("GET", next_url)
            payload = response.json()
            values = payload.get("value", []) if isinstance(payload, dict) else []
            items.extend(self._parse_item(value) for value in values if isinstance(value, dict))
            next_value = payload.get("@odata.nextLink") if isinstance(payload, dict) else None
            next_url = str(next_value) if next_value else None
        return tuple(items)

    def list_children(self, item_id: str | None = None) -> Sequence[DriveItem]:
        endpoint = (
            f"/me/drive/items/{quote(item_id, safe='')}/children"
            if item_id
            else "/me/drive/root/children"
        )
        return self._paged_items(endpoint)

    def search(self, query: str) -> Sequence[DriveItem]:
        cleaned = query.strip()
        if not cleaned:
            raise GraphValidationError("Escribe un término para buscar.")
        escaped = cleaned.replace("'", "''")
        endpoint = f"/me/drive/root/search(q='{quote(escaped, safe='')}')"
        return self._paged_items(endpoint)

    def get_item(self, item_id: str) -> DriveItem:
        response = self._request("GET", f"/me/drive/items/{quote(item_id, safe='')}")
        return self._parse_item(response.json())

    def _get_root(self) -> DriveItem:
        response = self._request("GET", "/me/drive/root")
        return self._parse_item(response.json())

    def get_quota(self) -> DriveQuota:
        response = self._request("GET", "/me/drive")
        payload = response.json()
        quota = payload.get("quota") or {}
        return DriveQuota(
            used_bytes=int(quota.get("used") or 0),
            total_bytes=int(quota.get("total") or 0),
            remaining_bytes=int(quota.get("remaining") or 0),
            state=str(quota.get("state") or "normal"),
        )

    def _get_drive_id(self) -> str:
        if self._drive_id:
            return self._drive_id
        response = self._request("GET", "/me/drive")
        payload = response.json()
        drive_id = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(drive_id, str) or not drive_id:
            raise GraphServiceError("OneDrive no devolvió el identificador de la unidad.")
        self._drive_id = drive_id
        return drive_id

    @classmethod
    def _parse_delta_change(cls, payload: Mapping[str, Any]) -> DeltaChange:
        modified_identity = payload.get("lastModifiedBy") or {}
        if not isinstance(modified_identity, Mapping):
            modified_identity = {}
        identity = modified_identity.get("user") or modified_identity.get("application") or {}
        if not isinstance(identity, Mapping):
            identity = {}
        parent = payload.get("parentReference") or {}
        if not isinstance(parent, Mapping):
            parent = {}
        return DeltaChange(
            item_id=str(payload.get("id") or ""),
            name=str(payload.get("name") or ""),
            parent_item_id=str(parent["id"]) if parent.get("id") else None,
            is_folder=isinstance(payload.get("folder"), Mapping),
            is_deleted=isinstance(payload.get("deleted"), Mapping),
            etag=str(payload["eTag"]) if payload.get("eTag") else None,
            created_at=cls._parse_datetime(payload.get("createdDateTime")),
            modified_at=cls._parse_datetime(payload.get("lastModifiedDateTime")),
            modified_by=str(identity.get("displayName") or "Cuenta Microsoft"),
        )

    def delta(
        self,
        item_id: str | None = None,
        *,
        delta_link: str | None = None,
        latest: bool = False,
    ) -> DeltaResult:
        if delta_link:
            next_url = self._validate_url(delta_link)
        elif item_id:
            drive_id = quote(self._get_drive_id(), safe="")
            encoded_item = quote(item_id, safe="")
            suffix = "?token=latest" if latest else ""
            next_url = f"/drives/{drive_id}/items/{encoded_item}/delta{suffix}"
        else:
            suffix = "?token=latest" if latest else ""
            next_url = f"/me/drive/root/delta{suffix}"

        by_id: dict[str, DeltaChange] = {}
        final_link: str | None = None
        while next_url:
            try:
                response = self._request(
                    "GET",
                    next_url,
                    extra_headers={"deltaExcludeParent": "true"},
                )
            except GraphError:
                raise
            payload = response.json()
            values = payload.get("value", []) if isinstance(payload, dict) else []
            for value in values:
                if not isinstance(value, Mapping):
                    continue
                change = self._parse_delta_change(value)
                if change.item_id:
                    by_id[change.item_id] = change
            next_value = payload.get("@odata.nextLink") if isinstance(payload, dict) else None
            delta_value = payload.get("@odata.deltaLink") if isinstance(payload, dict) else None
            if delta_value:
                final_link = self._validate_url(str(delta_value))
            next_url = str(next_value) if next_value else ""
        if not final_link:
            raise GraphServiceError("OneDrive no devolvió un cursor de sincronización válido.")
        return DeltaResult(tuple(by_id.values()), final_link)

    def create_folder(self, parent_id: str | None, name: str) -> DriveItem:
        cleaned = name.strip()
        if not cleaned:
            raise GraphValidationError("El nombre de la carpeta no puede estar vacío.")
        endpoint = (
            f"/me/drive/items/{quote(parent_id, safe='')}/children"
            if parent_id
            else "/me/drive/root/children"
        )
        response = self._request(
            "POST",
            endpoint,
            json={
                "name": cleaned,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "fail",
            },
            extra_headers={"Content-Type": "application/json"},
        )
        return self._parse_item(response.json())

    def upload_small_file(self, parent_id: str | None, source: Path) -> DriveItem:
        if not source.is_file():
            raise GraphValidationError("El archivo local seleccionado ya no existe.")
        size = source.stat().st_size
        if size > SMALL_UPLOAD_LIMIT:
            raise GraphValidationError(
                "Este archivo supera el límite de la carga directa; usa una sesión fragmentada."
            )
        parent_path = f"items/{quote(parent_id, safe='')}" if parent_id else "root"
        filename = quote(source.name, safe="")
        endpoint = (
            f"/me/drive/{parent_path}:/{filename}:/content?@microsoft.graph.conflictBehavior=fail"
        )
        with source.open("rb") as file_handle:
            response = self._request(
                "PUT",
                endpoint,
                content=file_handle,
                before_attempt=lambda: file_handle.seek(0),
                extra_headers={
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(size),
                },
            )
        return self._parse_item(response.json())

    @staticmethod
    def _validate_upload_url(url: str) -> str:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        trusted_host = (
            hostname == "graph.microsoft.com"
            or hostname == "api.onedrive.com"
            or hostname == "my.microsoftpersonalcontent.com"
            or hostname.endswith(".up.1drv.com")
            or hostname.endswith(".up.onedrive.com")
        )
        if (
            parsed.scheme != "https"
            or not trusted_host
            or parsed.port not in {None, 443}
            or parsed.username is not None
        ):
            LOGGER.warning("Host de Upload Session no reconocido: %s", hostname or "<vacío>")
            raise GraphServiceError("OneDrive devolvió una dirección de carga no válida.")
        return url

    @staticmethod
    def _check_upload_cancelled(is_cancelled: Callable[[], bool]) -> None:
        if is_cancelled():
            raise GraphUploadCancelled("La subida fue cancelada.")

    @staticmethod
    def _next_upload_offset(payload: Any, fallback: int) -> int:
        ranges = payload.get("nextExpectedRanges") if isinstance(payload, dict) else None
        if not isinstance(ranges, list) or not ranges:
            return fallback
        first_range = ranges[0]
        if not isinstance(first_range, str):
            return fallback
        start = first_range.split("-", maxsplit=1)[0]
        try:
            return max(0, int(start))
        except ValueError:
            return fallback

    def _create_upload_session(self, parent_id: str | None, source: Path) -> str:
        parent_path = f"items/{quote(parent_id, safe='')}" if parent_id else "root"
        filename = quote(source.name, safe="")
        endpoint = f"/me/drive/{parent_path}:/{filename}:/createUploadSession"
        response = self._request(
            "POST",
            endpoint,
            json={
                "item": {
                    "@microsoft.graph.conflictBehavior": "fail",
                    "name": source.name,
                }
            },
            extra_headers={"Content-Type": "application/json"},
        )
        payload = response.json()
        upload_url = payload.get("uploadUrl") if isinstance(payload, dict) else None
        if not isinstance(upload_url, str) or not upload_url:
            raise GraphServiceError("OneDrive no devolvió una sesión de carga válida.")
        return self._validate_upload_url(upload_url)

    def _upload_session_request(
        self,
        method: str,
        upload_url: str,
        *,
        is_cancelled: Callable[[], bool],
        **kwargs: Any,
    ) -> httpx.Response:
        safe_url = self._validate_upload_url(upload_url)
        for attempt in range(self._max_retries + 1):
            self._check_upload_cancelled(is_cancelled)
            try:
                # uploadUrl ya está preautorizada: no debe recibir el token OAuth.
                response = self._client.request(method, safe_url, **kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as error:
                if attempt >= self._max_retries:
                    raise GraphNetworkError(
                        "La subida se interrumpió. Comprueba tu conexión y vuelve a intentarlo."
                    ) from error
                self._sleep(self._retry_delay(None, attempt))
                continue
            if response.status_code in _TRANSIENT_STATUSES and attempt < self._max_retries:
                self._sleep(self._retry_delay(response, attempt))
                continue
            return response
        raise GraphServiceError("OneDrive no completó la subida.")

    def _cancel_upload_session(self, upload_url: str) -> None:
        try:
            self._client.request("DELETE", self._validate_upload_url(upload_url))
        except (httpx.HTTPError, GraphError):
            LOGGER.info("No se pudo descartar la sesión cancelada de OneDrive.")

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
    ) -> DriveItem:
        """Upload a file while exposing enough state to resume after an app restart."""
        if not source.is_file():
            raise GraphValidationError("El archivo local seleccionado ya no existe.")
        total_size = source.stat().st_size
        if total_size > MAX_UPLOAD_SIZE:
            raise GraphValidationError("El archivo supera el límite de 250 GB de OneDrive.")
        notify = progress or (lambda _transferred, _total: None)
        save = checkpoint or (lambda _url, _offset: None)
        cancelled = is_cancelled or (lambda: False)
        self._check_upload_cancelled(cancelled)
        if total_size <= SIMPLE_UPLOAD_THRESHOLD:
            notify(0, total_size)
            result = self.upload_small_file(parent_id, source)
            save(None, total_size)
            notify(total_size, total_size)
            return result

        upload_url = session_url
        offset = min(max(transferred, 0), total_size)
        if upload_url:
            status = self._upload_session_request("GET", upload_url, is_cancelled=cancelled)
            if status.status_code == 404:
                upload_url = None
                offset = 0
            elif status.is_success:
                offset = self._next_upload_offset(status.json(), offset)
            else:
                self._raise_for_response(status)
        if not upload_url:
            upload_url = self._create_upload_session(parent_id, source)
            offset = 0
            save(upload_url, offset)
        notify(offset, total_size)

        with source.open("rb") as file_handle:
            while offset < total_size:
                self._check_upload_cancelled(cancelled)
                file_handle.seek(offset)
                chunk = file_handle.read(min(UPLOAD_CHUNK_SIZE, total_size - offset))
                if not chunk:
                    raise GraphServiceError("No se pudo leer el archivo local completo.")
                end = offset + len(chunk) - 1
                response = self._upload_session_request(
                    "PUT",
                    upload_url,
                    is_cancelled=cancelled,
                    content=chunk,
                    headers={
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {offset}-{end}/{total_size}",
                        "Content-Type": "application/octet-stream",
                    },
                )
                if response.status_code in {200, 201}:
                    save(None, total_size)
                    notify(total_size, total_size)
                    return self._parse_item(response.json())
                if response.status_code == 202:
                    next_offset = self._next_upload_offset(response.json(), end + 1)
                    if next_offset <= offset or next_offset > total_size:
                        raise GraphServiceError("OneDrive devolvió un progreso de carga no válido.")
                    offset = next_offset
                    save(upload_url, offset)
                    notify(offset, total_size)
                    continue
                if response.status_code == 416:
                    status = self._upload_session_request("GET", upload_url, is_cancelled=cancelled)
                    if status.is_success:
                        offset = self._next_upload_offset(status.json(), offset)
                        save(upload_url, offset)
                        notify(offset, total_size)
                        continue
                if response.status_code == 404:
                    upload_url = self._create_upload_session(parent_id, source)
                    offset = 0
                    save(upload_url, offset)
                    notify(offset, total_size)
                    continue
                self._raise_for_response(response)
        raise GraphServiceError("OneDrive terminó la sesión sin confirmar el archivo.")

    def discard_upload_session(self, upload_url: str) -> None:
        self._cancel_upload_session(upload_url)

    @staticmethod
    def _validate_download_url(url: str) -> str:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        trusted_host = hostname.endswith(
            (".1drv.com", ".onedrive.com", ".sharepoint.com", ".microsoftpersonalcontent.com")
        ) or hostname in {"api.onedrive.com", "graph.microsoft.com"}
        if (
            parsed.scheme != "https"
            or not trusted_host
            or parsed.port not in {None, 443}
            or parsed.username is not None
        ):
            LOGGER.warning("Host de descarga no reconocido: %s", hostname or "<vacío>")
            raise GraphServiceError("OneDrive devolvió una dirección de descarga no válida.")
        return url

    def get_download_descriptor(self, item_id: str) -> DownloadDescriptor:
        response = self._request("GET", f"/me/drive/items/{quote(item_id, safe='')}")
        payload = response.json()
        download_url = payload.get("@microsoft.graph.downloadUrl")
        if not isinstance(download_url, str) or not download_url:
            raise GraphServiceError("OneDrive no devolvió un enlace temporal de descarga.")
        file_data = payload.get("file") or {}
        hashes = file_data.get("hashes") or {} if isinstance(file_data, Mapping) else {}
        return DownloadDescriptor(
            item_id=str(payload.get("id") or item_id),
            name=str(payload.get("name") or "archivo"),
            size_bytes=int(payload.get("size") or 0),
            etag=str(payload["eTag"]) if payload.get("eTag") else None,
            download_url=self._validate_download_url(download_url),
            quick_xor_hash=(str(hashes["quickXorHash"]) if hashes.get("quickXorHash") else None),
            sha1_hash=str(hashes["sha1Hash"]) if hashes.get("sha1Hash") else None,
        )

    def download_to_part(
        self,
        descriptor: DownloadDescriptor,
        part_path: Path,
        *,
        progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> int:
        notify = progress or (lambda _transferred, _total: None)
        cancelled = is_cancelled or (lambda: False)
        part_path.parent.mkdir(parents=True, exist_ok=True)
        start = part_path.stat().st_size if part_path.exists() else 0
        if start > descriptor.size_bytes:
            part_path.unlink()
            start = 0
        notify(start, descriptor.size_bytes)
        headers = {"Range": f"bytes={start}-"} if start else {}
        safe_url = self._validate_download_url(descriptor.download_url)
        for attempt in range(self._max_retries + 1):
            self._check_upload_cancelled(cancelled)
            try:
                # El enlace es preautorizado y nunca recibe el token OAuth.
                with self._client.stream("GET", safe_url, headers=headers) as response:
                    if response.status_code in _TRANSIENT_STATUSES and attempt < self._max_retries:
                        self._sleep(self._retry_delay(response, attempt))
                        continue
                    if response.status_code not in {200, 206}:
                        response.read()
                        self._raise_for_response(response)
                    append = start > 0 and response.status_code == 206
                    written = start if append else 0
                    with part_path.open("ab" if append else "wb") as destination_file:
                        for chunk in response.iter_bytes():
                            self._check_upload_cancelled(cancelled)
                            destination_file.write(chunk)
                            written += len(chunk)
                            notify(written, descriptor.size_bytes)
                    return written
            except GraphUploadCancelled:
                raise
            except (httpx.TimeoutException, httpx.TransportError) as error:
                if attempt >= self._max_retries:
                    raise GraphNetworkError(
                        "La descarga se interrumpió. Se conservará el progreso para reanudarla."
                    ) from error
                self._sleep(self._retry_delay(None, attempt))
                start = part_path.stat().st_size if part_path.exists() else 0
                headers = {"Range": f"bytes={start}-"} if start else {}
        raise GraphServiceError("OneDrive no completó la descarga.")

    def upload_large_file(
        self,
        parent_id: str | None,
        source: Path,
        progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> DriveItem:
        if not source.is_file():
            raise GraphValidationError("El archivo local seleccionado ya no existe.")
        total_size = source.stat().st_size
        if total_size > MAX_UPLOAD_SIZE:
            raise GraphValidationError("El archivo supera el límite de 250 GB de OneDrive.")
        if total_size == 0:
            return self.upload_small_file(parent_id, source)

        notify = progress or (lambda _transferred, _total: None)
        cancelled = is_cancelled or (lambda: False)
        self._check_upload_cancelled(cancelled)
        upload_url = self._create_upload_session(parent_id, source)
        offset = 0
        notify(offset, total_size)
        try:
            with source.open("rb") as file_handle:
                while offset < total_size:
                    self._check_upload_cancelled(cancelled)
                    file_handle.seek(offset)
                    chunk = file_handle.read(min(UPLOAD_CHUNK_SIZE, total_size - offset))
                    if not chunk:
                        raise GraphServiceError("No se pudo leer el archivo local completo.")
                    end = offset + len(chunk) - 1
                    response = self._upload_session_request(
                        "PUT",
                        upload_url,
                        is_cancelled=cancelled,
                        content=chunk,
                        headers={
                            "Content-Length": str(len(chunk)),
                            "Content-Range": f"bytes {offset}-{end}/{total_size}",
                            "Content-Type": "application/octet-stream",
                        },
                    )
                    if response.status_code in {200, 201}:
                        notify(total_size, total_size)
                        return self._parse_item(response.json())
                    if response.status_code == 202:
                        next_offset = self._next_upload_offset(response.json(), end + 1)
                        if next_offset <= offset or next_offset > total_size:
                            raise GraphServiceError(
                                "OneDrive devolvió un progreso de carga no válido."
                            )
                        offset = next_offset
                        notify(offset, total_size)
                        continue
                    if response.status_code == 416:
                        status = self._upload_session_request(
                            "GET", upload_url, is_cancelled=cancelled
                        )
                        if status.is_success:
                            offset = self._next_upload_offset(status.json(), offset)
                            notify(offset, total_size)
                            continue
                    if response.status_code == 404:
                        raise GraphServiceError(
                            "La sesión de carga expiró. Inicia la subida nuevamente."
                        )
                    self._raise_for_response(response)
        except GraphUploadCancelled:
            self._cancel_upload_session(upload_url)
            raise
        raise GraphServiceError("OneDrive terminó la sesión sin confirmar el archivo.")

    def upload_file(
        self,
        parent_id: str | None,
        source: Path,
        progress: Callable[[int, int], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> DriveItem:
        if not source.is_file():
            raise GraphValidationError("El archivo local seleccionado ya no existe.")
        size = source.stat().st_size
        if size > MAX_UPLOAD_SIZE:
            raise GraphValidationError("El archivo supera el límite de 250 GB de OneDrive.")
        notify = progress or (lambda _transferred, _total: None)
        cancelled = is_cancelled or (lambda: False)
        self._check_upload_cancelled(cancelled)
        if size <= SIMPLE_UPLOAD_THRESHOLD:
            notify(0, size)
            result = self.upload_small_file(parent_id, source)
            notify(size, size)
            return result
        return self.upload_large_file(parent_id, source, notify, cancelled)

    def download_file(self, item_id: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}-",
            suffix=".part",
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        endpoint = f"/me/drive/items/{quote(item_id, safe='')}/content"
        try:
            for attempt in range(self._max_retries + 1):
                try:
                    with self._client.stream("GET", endpoint, headers=self._headers()) as response:
                        if (
                            response.status_code in _TRANSIENT_STATUSES
                            and attempt < self._max_retries
                        ):
                            self._sleep(self._retry_delay(response, attempt))
                            continue
                        if not response.is_success:
                            response.read()
                            self._raise_for_response(response)
                        with temporary_path.open("wb") as destination_file:
                            for chunk in response.iter_bytes():
                                destination_file.write(chunk)
                        os.replace(temporary_path, destination)
                        return destination
                except (httpx.TimeoutException, httpx.TransportError) as error:
                    if attempt >= self._max_retries:
                        raise GraphNetworkError(
                            "La descarga se interrumpió. Comprueba tu conexión "
                            "e inténtalo de nuevo."
                        ) from error
                    self._sleep(self._retry_delay(None, attempt))
            raise GraphServiceError("OneDrive no completó la descarga.")
        finally:
            temporary_path.unlink(missing_ok=True)

    def rename_item(self, item_id: str, new_name: str, etag: str | None = None) -> DriveItem:
        cleaned = new_name.strip()
        if not cleaned:
            raise GraphValidationError("El nombre no puede estar vacío.")
        headers = {"Content-Type": "application/json"}
        if etag:
            headers["If-Match"] = etag
        response = self._request(
            "PATCH",
            f"/me/drive/items/{quote(item_id, safe='')}",
            json={"name": cleaned},
            extra_headers=headers,
        )
        return self._parse_item(response.json())

    def move_item(self, item_id: str, parent_id: str | None) -> DriveItem:
        target_id = parent_id or self._get_root().item_id
        response = self._request(
            "PATCH",
            f"/me/drive/items/{quote(item_id, safe='')}",
            json={"parentReference": {"id": target_id}},
            extra_headers={"Content-Type": "application/json"},
        )
        return self._parse_item(response.json())

    def delete_item(self, item_id: str, etag: str | None = None) -> None:
        headers = {"If-Match": etag} if etag else None
        self._request(
            "DELETE",
            f"/me/drive/items/{quote(item_id, safe='')}",
            extra_headers=headers,
        )

    @staticmethod
    def _parse_permission(payload: Mapping[str, Any]) -> SharingPermission:
        granted = payload.get("grantedToV2") or payload.get("grantedTo") or {}
        if not isinstance(granted, Mapping):
            granted = {}
        identity = granted.get("user") or granted.get("siteUser") or {}
        if not isinstance(identity, Mapping):
            identity = {}
        identities = payload.get("grantedToIdentitiesV2") or payload.get("grantedToIdentities")
        if not identity and isinstance(identities, list) and identities:
            first = identities[0]
            if isinstance(first, Mapping):
                candidate = first.get("user") or first.get("siteUser") or {}
                if isinstance(candidate, Mapping):
                    identity = candidate
        invitation = payload.get("invitation") or {}
        if not isinstance(invitation, Mapping):
            invitation = {}
        roles = payload.get("roles")
        return SharingPermission(
            permission_id=str(payload.get("id") or ""),
            roles=tuple(str(role) for role in roles) if isinstance(roles, list) else (),
            grantee_name=(str(identity["displayName"]) if identity.get("displayName") else None),
            grantee_email=(
                str(identity.get("email") or invitation.get("email"))
                if identity.get("email") or invitation.get("email")
                else None
            ),
            inherited=isinstance(payload.get("inheritedFrom"), Mapping),
        )

    def invite_user(
        self,
        item_id: str,
        email: str,
        role: str,
        *,
        send_invitation: bool = True,
        message: str = "",
    ) -> SharingPermission:
        if role not in {"read", "write"}:
            raise GraphValidationError("OneDrive Personal solo admite acceso read o write.")
        cleaned_email = email.strip()
        if not cleaned_email:
            raise GraphValidationError("Escribe el correo de la persona invitada.")
        response = self._request(
            "POST",
            f"/me/drive/items/{quote(item_id, safe='')}/invite",
            json={
                "recipients": [{"email": cleaned_email}],
                "message": message[:2000],
                "requireSignIn": True,
                "sendInvitation": send_invitation,
                "roles": [role],
            },
            extra_headers={"Content-Type": "application/json"},
        )
        payload = response.json()
        values = payload.get("value") if isinstance(payload, dict) else None
        if not isinstance(values, list) or not values or not isinstance(values[0], Mapping):
            raise GraphServiceError("OneDrive no confirmó el permiso de la invitación.")
        permission = self._parse_permission(values[0])
        if not permission.permission_id:
            raise GraphServiceError("OneDrive devolvió un permiso sin identificador.")
        return permission

    def list_permissions(self, item_id: str) -> Sequence[SharingPermission]:
        permissions: list[SharingPermission] = []
        next_url: str | None = f"/me/drive/items/{quote(item_id, safe='')}/permissions"
        while next_url:
            response = self._request("GET", next_url)
            payload = response.json()
            values = payload.get("value", []) if isinstance(payload, dict) else []
            permissions.extend(
                self._parse_permission(value) for value in values if isinstance(value, Mapping)
            )
            next_value = payload.get("@odata.nextLink") if isinstance(payload, dict) else None
            next_url = str(next_value) if next_value else None
        return tuple(permissions)

    def delete_permission(self, item_id: str, permission_id: str) -> None:
        self._request(
            "DELETE",
            (
                f"/me/drive/items/{quote(item_id, safe='')}/permissions/"
                f"{quote(permission_id, safe='')}"
            ),
        )
