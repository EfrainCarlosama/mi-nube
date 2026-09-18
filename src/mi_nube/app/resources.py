from __future__ import annotations

from importlib.resources import files


def update_public_key_bytes() -> bytes:
    return files("mi_nube.assets").joinpath("update_public_key.pem").read_bytes()
