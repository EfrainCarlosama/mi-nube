from __future__ import annotations

import ctypes
import os
import sys
import tempfile
from ctypes import wintypes
from pathlib import Path
from typing import Protocol


class DataProtector(Protocol):
    def protect(self, data: bytes) -> bytes: ...

    def unprotect(self, data: bytes) -> bytes: ...


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class WindowsDpapiProtector:
    """Encrypts data for the current Windows user through DPAPI."""

    _UI_FORBIDDEN = 0x1

    def __init__(self, entropy: bytes = b"Mi Nube token cache v1") -> None:
        if sys.platform != "win32":
            raise RuntimeError("DPAPI solo está disponible en Windows")
        self._entropy = entropy
        self._crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        self._crypt32.CryptProtectData.argtypes = (
            ctypes.POINTER(_DataBlob),
            wintypes.LPCWSTR,
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        )
        self._crypt32.CryptProtectData.restype = wintypes.BOOL
        self._crypt32.CryptUnprotectData.argtypes = (
            ctypes.POINTER(_DataBlob),
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        )
        self._crypt32.CryptUnprotectData.restype = wintypes.BOOL
        self._kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
        self._kernel32.LocalFree.restype = ctypes.c_void_p

    @staticmethod
    def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
        buffer = ctypes.create_string_buffer(data)
        blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        return blob, buffer

    def protect(self, data: bytes) -> bytes:
        data_blob, data_buffer = self._blob(data)
        entropy_blob, entropy_buffer = self._blob(self._entropy)
        output_blob = _DataBlob()
        success = self._crypt32.CryptProtectData(
            ctypes.byref(data_blob),
            "Mi Nube",
            ctypes.byref(entropy_blob),
            None,
            None,
            self._UI_FORBIDDEN,
            ctypes.byref(output_blob),
        )
        del data_buffer, entropy_buffer
        if not success:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            self._kernel32.LocalFree(output_blob.pbData)

    def unprotect(self, data: bytes) -> bytes:
        data_blob, data_buffer = self._blob(data)
        entropy_blob, entropy_buffer = self._blob(self._entropy)
        output_blob = _DataBlob()
        description = wintypes.LPWSTR()
        success = self._crypt32.CryptUnprotectData(
            ctypes.byref(data_blob),
            ctypes.byref(description),
            ctypes.byref(entropy_blob),
            None,
            None,
            self._UI_FORBIDDEN,
            ctypes.byref(output_blob),
        )
        del data_buffer, entropy_buffer
        if not success:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return ctypes.string_at(output_blob.pbData, output_blob.cbData)
        finally:
            if description:
                self._kernel32.LocalFree(description)
            self._kernel32.LocalFree(output_blob.pbData)


class ProtectedFileTokenCacheStore:
    def __init__(self, cache_path: Path, protector: DataProtector) -> None:
        self._cache_path = cache_path
        self._protector = protector

    def load(self) -> str | None:
        if not self._cache_path.exists():
            return None
        encrypted = self._cache_path.read_bytes()
        return self._protector.unprotect(encrypted).decode("utf-8")

    def save(self, serialized_cache: str) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        encrypted = self._protector.protect(serialized_cache.encode("utf-8"))
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self._cache_path.parent,
            prefix="token-cache-",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as temporary_file:
                temporary_file.write(encrypted)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self._cache_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    def clear(self) -> None:
        self._cache_path.unlink(missing_ok=True)


class MemoryTokenCacheStore:
    """Non-persistent store used by tests and unsupported development platforms."""

    def __init__(self) -> None:
        self.value: str | None = None

    def load(self) -> str | None:
        return self.value

    def save(self, serialized_cache: str) -> None:
        self.value = serialized_cache

    def clear(self) -> None:
        self.value = None


class MemoryDataProtector:
    """Reversible development protector; production on Windows always uses DPAPI."""

    def protect(self, data: bytes) -> bytes:
        return data

    def unprotect(self, data: bytes) -> bytes:
        return data


def create_transfer_protector() -> DataProtector:
    if sys.platform == "win32":
        return WindowsDpapiProtector(b"Mi Nube transfer sessions v1")
    return MemoryDataProtector()


def create_token_cache_store(
    auth_dir: Path,
) -> ProtectedFileTokenCacheStore | MemoryTokenCacheStore:
    if sys.platform == "win32":
        return ProtectedFileTokenCacheStore(
            auth_dir / "msal-cache.bin",
            WindowsDpapiProtector(),
        )
    return MemoryTokenCacheStore()
