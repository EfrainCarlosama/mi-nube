from pathlib import Path

from mi_nube.auth.token_cache import ProtectedFileTokenCacheStore


class ReversingProtector:
    def protect(self, data: bytes) -> bytes:
        return data[::-1]

    def unprotect(self, data: bytes) -> bytes:
        return data[::-1]


def test_protected_cache_roundtrip_and_clear(tmp_path: Path) -> None:
    cache_path = tmp_path / "auth" / "cache.bin"
    store = ProtectedFileTokenCacheStore(cache_path, ReversingProtector())

    store.save('{"token": "sensitive"}')

    assert b"sensitive" not in cache_path.read_bytes()
    assert store.load() == '{"token": "sensitive"}'
    store.clear()
    assert store.load() is None
