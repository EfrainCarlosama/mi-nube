from __future__ import annotations

import argparse
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from mi_nube.auth.token_cache import WindowsDpapiProtector


def default_private_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    return base / "MiNube" / "release-keys" / "update-private.dpapi"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Genera la clave Ed25519 de actualizaciones")
    parser.add_argument("--private-output", type=Path, default=default_private_path())
    parser.add_argument(
        "--public-output",
        type=Path,
        default=Path("src/mi_nube/assets/update_public_key.pem"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.private_output.exists() or args.public_output.exists():
        raise SystemExit("Las claves ya existen; no se reemplazaron.")
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    protector = WindowsDpapiProtector(b"Mi Nube update signing key v1")
    args.private_output.parent.mkdir(parents=True, exist_ok=True)
    args.public_output.parent.mkdir(parents=True, exist_ok=True)
    args.private_output.write_bytes(protector.protect(private_pem))
    args.public_output.write_bytes(public_pem)
    print(f"Clave privada protegida: {args.private_output}")
    print(f"Clave pública para la aplicación: {args.public_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
