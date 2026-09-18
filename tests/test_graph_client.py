from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from mi_nube.graph.errors import (
    GraphDeltaResetRequired,
    GraphPermissionError,
    GraphServiceError,
    GraphUploadCancelled,
    GraphValidationError,
)
from mi_nube.graph.http_client import (
    SIMPLE_UPLOAD_THRESHOLD,
    SMALL_UPLOAD_LIMIT,
    UPLOAD_CHUNK_SIZE,
    HttpGraphDriveClient,
)


class FakeAuthService:
    def current_profile(self):
        return None

    def sign_in(self):
        raise AssertionError("not used")

    def sign_out(self):
        return None

    def acquire_access_token(self, scopes) -> str:
        assert "Files.ReadWrite" in scopes
        return "access-token"


def graph_client(handler, *, retries: int = 0, sleep=lambda _: None) -> HttpGraphDriveClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://graph.microsoft.com/v1.0",
        transport=transport,
        follow_redirects=True,
    )
    return HttpGraphDriveClient(FakeAuthService(), http_client, retries, sleep)


def item_payload(item_id: str, name: str, *, folder: bool = False) -> dict:
    payload = {
        "id": item_id,
        "name": name,
        "size": 123,
        "lastModifiedDateTime": "2026-09-17T12:00:00Z",
        "lastModifiedBy": {"user": {"displayName": "Efraín"}},
        "parentReference": {"path": "/drive/root:"},
        "eTag": '"etag"',
    }
    if folder:
        payload["folder"] = {"childCount": 2}
    else:
        payload["file"] = {"mimeType": "application/pdf"}
    return payload


def test_list_children_follows_graph_next_link() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer access-token"
        if "page=2" in str(request.url):
            return httpx.Response(200, json={"value": [item_payload("2", "Plano.pdf")]})
        return httpx.Response(
            200,
            json={
                "value": [item_payload("1", "Proyectos", folder=True)],
                "@odata.nextLink": (
                    "https://graph.microsoft.com/v1.0/me/drive/root/children?page=2"
                ),
            },
        )

    items = graph_client(handler).list_children()

    assert [item.name for item in items] == ["Proyectos", "Plano.pdf"]
    assert items[0].is_folder
    assert items[1].mime_type == "application/pdf"


def test_create_folder_uses_fail_conflict_policy() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.method == "POST"
        assert request.url.path.endswith("/me/drive/root/children")
        assert payload["name"] == "Nuevo proyecto"
        assert payload["@microsoft.graph.conflictBehavior"] == "fail"
        return httpx.Response(201, json=item_payload("new", payload["name"], folder=True))

    item = graph_client(handler).create_folder(None, " Nuevo proyecto ")
    assert item.item_id == "new"


def test_rename_and_delete_send_etag() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        assert request.headers["If-Match"] == '"etag"'
        if request.method == "PATCH":
            assert json.loads(request.content) == {"name": "Nuevo.pdf"}
            return httpx.Response(200, json=item_payload("file", "Nuevo.pdf"))
        return httpx.Response(204)

    client = graph_client(handler)
    renamed = client.rename_item("file", "Nuevo.pdf", '"etag"')
    client.delete_item("file", '"etag"')
    assert renamed.name == "Nuevo.pdf"
    assert methods == ["PATCH", "DELETE"]


def test_untrusted_pagination_link_is_rejected() -> None:
    client = graph_client(
        lambda request: httpx.Response(
            200,
            json={
                "value": [],
                "@odata.nextLink": "https://example.invalid/steal-token",
            },
        )
    )
    with pytest.raises(GraphServiceError, match="paginación"):
        client.list_children()


def test_throttling_honors_retry_after() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "3"},
                json={"error": {"code": "tooManyRequests", "message": "slow down"}},
            )
        return httpx.Response(200, json={"value": []})

    items = graph_client(handler, retries=1, sleep=delays.append).list_children()
    assert items == ()
    assert delays == [3.0]


def test_permission_error_is_translated() -> None:
    client = graph_client(
        lambda request: httpx.Response(
            403,
            json={"error": {"code": "accessDenied", "message": "denied"}},
        )
    )
    with pytest.raises(GraphPermissionError, match="permiso"):
        client.list_children()


def test_upload_small_file_streams_content(tmp_path: Path) -> None:
    source = tmp_path / "plano.pdf"
    source.write_bytes(b"drawing-bytes")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.read() == b"drawing-bytes"
        assert request.url.path.endswith("/root:/plano.pdf:/content")
        assert request.url.params["@microsoft.graph.conflictBehavior"] == "fail"
        return httpx.Response(201, json=item_payload("file", "plano.pdf"))

    uploaded = graph_client(handler).upload_small_file(None, source)
    assert uploaded.name == "plano.pdf"


def test_upload_rejects_files_over_simple_limit(tmp_path: Path) -> None:
    source = tmp_path / "large.rvt"
    with source.open("wb") as file_handle:
        file_handle.seek(SMALL_UPLOAD_LIMIT)
        file_handle.write(b"x")
    with pytest.raises(GraphValidationError, match="carga directa"):
        graph_client(lambda request: pytest.fail("network should not be used")).upload_small_file(
            None, source
        )


def test_upload_file_uses_resumable_chunks_and_reports_progress(tmp_path: Path) -> None:
    source = tmp_path / "modelo.rvt"
    total_size = SIMPLE_UPLOAD_THRESHOLD + 123
    source.write_bytes(b"a" * total_size)
    chunk_ranges: list[str] = []
    progress: list[tuple[int, int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.path.endswith("/root:/modelo.rvt:/createUploadSession")
            assert request.headers["Authorization"] == "Bearer access-token"
            payload = json.loads(request.content)
            assert payload["item"]["@microsoft.graph.conflictBehavior"] == "fail"
            return httpx.Response(
                200,
                json={"uploadUrl": ("https://my.microsoftpersonalcontent.com/upload/session-1")},
            )

        assert request.method == "PUT"
        assert "Authorization" not in request.headers
        content_range = request.headers["Content-Range"]
        chunk_ranges.append(content_range)
        if len(chunk_ranges) == 1:
            assert len(request.read()) == UPLOAD_CHUNK_SIZE
            return httpx.Response(
                202,
                json={"nextExpectedRanges": [f"{UPLOAD_CHUNK_SIZE}-"]},
            )
        assert request.read() == b"a" * 123
        return httpx.Response(201, json=item_payload("large", "modelo.rvt"))

    uploaded = graph_client(handler).upload_file(
        None, source, lambda transferred, total: progress.append((transferred, total))
    )

    assert uploaded.item_id == "large"
    assert chunk_ranges == [
        f"bytes 0-{UPLOAD_CHUNK_SIZE - 1}/{total_size}",
        f"bytes {UPLOAD_CHUNK_SIZE}-{total_size - 1}/{total_size}",
    ]
    assert progress == [
        (0, total_size),
        (UPLOAD_CHUNK_SIZE, total_size),
        (total_size, total_size),
    ]


def test_large_upload_retries_same_chunk_after_transient_failure(tmp_path: Path) -> None:
    source = tmp_path / "video.bin"
    source.write_bytes(b"v" * (SIMPLE_UPLOAD_THRESHOLD + 1))
    attempts: list[str] = []
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={"uploadUrl": "https://graph.microsoft.com/upload/retry"},
            )
        attempts.append(request.headers["Content-Range"])
        if len(attempts) == 1:
            return httpx.Response(503)
        if len(attempts) == 2:
            return httpx.Response(
                202,
                json={"nextExpectedRanges": [f"{UPLOAD_CHUNK_SIZE}-"]},
            )
        return httpx.Response(201, json=item_payload("video", "video.bin"))

    uploaded = graph_client(handler, retries=1, sleep=delays.append).upload_file(None, source)

    assert uploaded.name == "video.bin"
    assert attempts[0] == attempts[1]
    assert delays == [1.0]


def test_cancelling_large_upload_discards_remote_session(tmp_path: Path) -> None:
    source = tmp_path / "cancel.bin"
    source.write_bytes(b"x" * (SIMPLE_UPLOAD_THRESHOLD + 1))
    cancelled = False
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "POST":
            return httpx.Response(
                200,
                json={"uploadUrl": "https://graph.microsoft.com/upload/cancel"},
            )
        assert request.method == "DELETE"
        return httpx.Response(204)

    def progress(_transferred: int, _total: int) -> None:
        nonlocal cancelled
        cancelled = True

    with pytest.raises(GraphUploadCancelled, match="cancelada"):
        graph_client(handler).upload_file(None, source, progress, lambda: cancelled)

    assert methods == ["POST", "DELETE"]


def test_upload_session_rejects_untrusted_upload_url(tmp_path: Path) -> None:
    source = tmp_path / "unsafe.bin"
    source.write_bytes(b"x" * (SIMPLE_UPLOAD_THRESHOLD + 1))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"uploadUrl": "https://example.invalid/upload"})

    with pytest.raises(GraphServiceError, match="dirección de carga"):
        graph_client(handler).upload_file(None, source)


def test_download_is_written_to_requested_destination(tmp_path: Path) -> None:
    client = graph_client(
        lambda request: httpx.Response(
            200,
            content=b"remote-content",
            headers={"Content-Type": "application/octet-stream"},
        )
    )
    destination = tmp_path / "downloaded.dwg"
    result = client.download_file("item-id", destination)
    assert result == destination
    assert destination.read_bytes() == b"remote-content"
    assert not list(tmp_path.glob("*.part"))


def test_resumable_download_uses_range_on_preauthorized_url(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "graph.microsoft.com":
            return httpx.Response(
                200,
                json={
                    **item_payload("remote", "modelo.dwg"),
                    "size": 10,
                    "@microsoft.graph.downloadUrl": (
                        "https://public.dm.files.1drv.com/download/token"
                    ),
                    "file": {"hashes": {"quickXorHash": "hash"}},
                },
            )
        assert "Authorization" not in request.headers
        assert request.headers["Range"] == "bytes=5-"
        return httpx.Response(206, content=b"67890")

    client = graph_client(handler)
    descriptor = client.get_download_descriptor("remote")
    part = tmp_path / ".modelo.part"
    part.write_bytes(b"12345")

    written = client.download_to_part(descriptor, part)

    assert written == 10
    assert part.read_bytes() == b"1234567890"
    assert len(requests) == 2


def test_quota_is_mapped() -> None:
    client = graph_client(
        lambda request: httpx.Response(
            200,
            json={"quota": {"used": 30, "total": 100, "remaining": 70, "state": "normal"}},
        )
    )
    quota = client.get_quota()
    assert quota.ratio == 0.3
    assert quota.remaining_bytes == 70


def test_invite_user_uses_personal_onedrive_read_role() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith("/items/project-root/invite")
        payload = json.loads(request.content)
        assert payload == {
            "recipients": [{"email": "colaborador@example.com"}],
            "message": "Acceso al proyecto",
            "requireSignIn": True,
            "sendInvitation": True,
            "roles": ["read"],
        }
        return httpx.Response(
            200,
            json={
                "value": [
                    {
                        "id": "permission-1",
                        "roles": ["read"],
                        "invitation": {"email": "colaborador@example.com"},
                    }
                ]
            },
        )

    permission = graph_client(handler).invite_user(
        "project-root",
        "colaborador@example.com",
        "read",
        message="Acceso al proyecto",
    )

    assert permission.permission_id == "permission-1"
    assert permission.roles == ("read",)
    assert permission.grantee_email == "colaborador@example.com"


def test_list_and_delete_permissions() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "id": "owner",
                            "roles": ["owner"],
                            "grantedToV2": {
                                "user": {
                                    "displayName": "Efraín",
                                    "email": "owner@example.com",
                                }
                            },
                        },
                        {
                            "id": "inherited",
                            "roles": ["write"],
                            "inheritedFrom": {"id": "parent"},
                        },
                    ]
                },
            )
        assert request.url.path.endswith("/permissions/inherited")
        return httpx.Response(204)

    client = graph_client(handler)
    permissions = client.list_permissions("folder")
    client.delete_permission("folder", "inherited")

    assert permissions[0].grantee_email == "owner@example.com"
    assert permissions[1].inherited
    assert methods == ["GET", "DELETE"]


def test_delta_follows_pages_and_keeps_last_item_version() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["deltaExcludeParent"] == "true"
        if "page=2" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            **item_payload("same", "Final.dwg"),
                            "createdDateTime": "2026-09-17T12:00:00Z",
                        }
                    ],
                    "@odata.deltaLink": (
                        "https://graph.microsoft.com/v1.0/me/drive/root/delta?token=final"
                    ),
                },
            )
        assert request.url.params["token"] == "latest"
        return httpx.Response(
            200,
            json={
                "value": [{**item_payload("same", "Anterior.dwg")}],
                "@odata.nextLink": ("https://graph.microsoft.com/v1.0/me/drive/root/delta?page=2"),
            },
        )

    result = graph_client(handler).delta(latest=True)

    assert len(result.changes) == 1
    assert result.changes[0].name == "Final.dwg"
    assert "token=final" in result.delta_link


def test_delta_translates_expired_cursor() -> None:
    client = graph_client(
        lambda request: httpx.Response(
            410,
            json={"error": {"code": "resyncRequired", "message": "expired"}},
        )
    )
    with pytest.raises(GraphDeltaResetRequired, match="cursor"):
        client.delta(delta_link="https://graph.microsoft.com/v1.0/me/drive/root/delta?token=x")
