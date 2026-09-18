from __future__ import annotations

import base64
import hashlib
from pathlib import Path


def quick_xor_hash(path: Path, block_size: int = 1024 * 1024) -> str:
    """Return Microsoft's 160-bit QuickXorHash as Base64."""
    width_bits = 160
    shift = 11
    digest = bytearray(width_bits // 8)
    length = 0
    with path.open("rb") as source:
        while chunk := source.read(block_size):
            for index, value in enumerate(chunk, start=length):
                bit_position = (index * shift) % width_bits
                byte_position, bit_offset = divmod(bit_position, 8)
                digest[byte_position] ^= (value << bit_offset) & 0xFF
                if bit_offset:
                    digest[(byte_position + 1) % len(digest)] ^= value >> (8 - bit_offset)
            length += len(chunk)
    for index, value in enumerate(length.to_bytes(8, "little")):
        digest[len(digest) - 8 + index] ^= value
    return base64.b64encode(digest).decode("ascii")


def sha1_hash(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha1(usedforsecurity=False)
    with path.open("rb") as source:
        while chunk := source.read(block_size):
            digest.update(chunk)
    return digest.hexdigest().upper()
