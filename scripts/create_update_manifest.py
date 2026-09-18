from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.serialization import load_pem_private_key

from mi_nube import __version__
from mi_nube.auth.token_cache import WindowsDpapiProtector
from mi_nube.updates.manifest import canonical_manifest_payload


def default_private_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    return base / "MiNube" / "release-keys" / "update-private.dpapi"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crea un manifiesto de actualización firmado")
    parser.add_argument("installer", type=Path)
    parser.add_argument("installer_url")
    parser.add_argument("--private-key", type=Path, default=default_private_path())
    parser.add_argument("--output", type=Path, default=Path("dist/update-manifest.json"))
    parser.add_argument("--release-notes", default="Mejoras de estabilidad y seguridad.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.installer.is_file():
        raise SystemExit(f"No existe el instalador: {args.installer}")
    if not args.installer_url.startswith("https://"):
        raise SystemExit("La URL del instalador debe comenzar con https://")
    protected = args.private_key.read_bytes()
    private_pem = WindowsDpapiProtector(b"Mi Nube update signing key v1").unprotect(protected)
    private_key = load_pem_private_key(private_pem, password=None)
    content = args.installer.read_bytes()
    values: dict[str, object] = {
        "schema": 1,
        "version": __version__,
        "installer_url": args.installer_url,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "published_at": datetime.now(UTC).isoformat(),
        "release_notes": args.release_notes,
    }
    values["signature"] = base64.b64encode(
        private_key.sign(canonical_manifest_payload(values))
    ).decode("ascii")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(values, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Manifiesto firmado: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
