from __future__ import annotations

import base64
import hashlib
import json

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mi_nube.updates.errors import UpdateError
from mi_nube.updates.manifest import canonical_manifest_payload
from mi_nube.updates.service import UpdateService


def signed_manifest(installer: bytes, version: str = "1.0.0") -> tuple[bytes, bytes]:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    values: dict[str, object] = {
        "schema": 1,
        "version": version,
        "installer_url": "https://updates.example.test/MiNubeSetup.exe",
        "sha256": hashlib.sha256(installer).hexdigest(),
        "size_bytes": len(installer),
        "published_at": "2026-09-18T12:00:00+00:00",
        "release_notes": "Versión de prueba",
    }
    values["signature"] = base64.b64encode(
        private_key.sign(canonical_manifest_payload(values))
    ).decode("ascii")
    return json.dumps(values).encode(), public_key


def test_signed_update_is_checked_downloaded_and_hashed(tmp_path) -> None:
    installer = b"signed installer bytes"
    manifest, public_key = signed_manifest(installer)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("manifest.json"):
            return httpx.Response(200, content=manifest)
        return httpx.Response(200, content=installer)

    service = UpdateService(
        "0.9.0",
        "https://updates.example.test/manifest.json",
        public_key,
        tmp_path,
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = service.check()
    progress: list[tuple[int, int]] = []
    path = service.download(result.manifest, lambda done, total: progress.append((done, total)))

    assert result.available
    assert path.read_bytes() == installer
    assert progress[-1] == (len(installer), len(installer))


def test_tampered_manifest_signature_is_rejected(tmp_path) -> None:
    manifest, public_key = signed_manifest(b"installer")
    values = json.loads(manifest)
    values["version"] = "9.9.9"
    tampered = json.dumps(values).encode()
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=tampered))
    )
    service = UpdateService(
        "0.9.0",
        "https://updates.example.test/manifest.json",
        public_key,
        tmp_path,
        client,
    )

    with pytest.raises(UpdateError, match="firma"):
        service.check()


def test_update_channel_rejects_non_https_urls(tmp_path) -> None:
    with pytest.raises(UpdateError, match="HTTPS"):
        UpdateService("0.9.0", "http://example.test/manifest.json", b"key", tmp_path)


def test_download_rejects_content_different_from_signed_hash(tmp_path) -> None:
    manifest, public_key = signed_manifest(b"expected")

    def handler(request: httpx.Request) -> httpx.Response:
        content = manifest if request.url.path.endswith("manifest.json") else b"modified"
        return httpx.Response(200, content=content)

    service = UpdateService(
        "0.9.0",
        "https://updates.example.test/manifest.json",
        public_key,
        tmp_path,
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = service.check()

    with pytest.raises(UpdateError, match="no coincide"):
        service.download(result.manifest)
    assert not tuple(tmp_path.glob("*.download"))
