from __future__ import annotations

import base64
import json
import re
from collections.abc import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from mi_nube.updates.errors import UpdateError
from mi_nube.updates.models import UpdateManifest

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SIGNED_FIELDS = (
    "schema",
    "version",
    "installer_url",
    "sha256",
    "size_bytes",
    "published_at",
    "release_notes",
)


def canonical_manifest_payload(values: Mapping[str, object]) -> bytes:
    try:
        payload = {field: values[field] for field in _SIGNED_FIELDS}
    except KeyError as error:
        raise UpdateError(
            f"El manifiesto no contiene el campo requerido: {error.args[0]}."
        ) from error
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def parse_and_verify_manifest(content: bytes, public_key_pem: bytes) -> UpdateManifest:
    try:
        values = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UpdateError(
            "El servidor devolvió un manifiesto de actualización inválido."
        ) from error
    if not isinstance(values, dict):
        raise UpdateError("El manifiesto de actualización debe ser un objeto JSON.")
    try:
        signature = base64.b64decode(str(values["signature"]), validate=True)
        public_key = load_pem_public_key(public_key_pem)
        public_key.verify(signature, canonical_manifest_payload(values))
    except KeyError as error:
        raise UpdateError("El manifiesto no incluye una firma.") from error
    except (ValueError, TypeError, InvalidSignature) as error:
        raise UpdateError("La firma del manifiesto de actualización no es válida.") from error

    try:
        manifest = UpdateManifest(
            schema=int(values["schema"]),
            version=str(values["version"]),
            installer_url=str(values["installer_url"]),
            sha256=str(values["sha256"]).lower(),
            size_bytes=int(values["size_bytes"]),
            published_at=str(values["published_at"]),
            release_notes=str(values["release_notes"]),
            signature=str(values["signature"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise UpdateError("El manifiesto firmado contiene valores inválidos.") from error
    if manifest.schema != 1:
        raise UpdateError("La versión del formato de actualización no es compatible.")
    if not _SHA256_PATTERN.fullmatch(manifest.sha256):
        raise UpdateError("El manifiesto no contiene un hash SHA-256 válido.")
    if manifest.size_bytes <= 0:
        raise UpdateError("El tamaño declarado del instalador no es válido.")
    return manifest
