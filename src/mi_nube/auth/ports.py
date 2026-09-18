from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from mi_nube.domain.models import AccountProfile


class AuthService(Protocol):
    def current_profile(self) -> AccountProfile | None: ...

    def sign_in(self) -> AccountProfile: ...

    def sign_out(self) -> None: ...

    def acquire_access_token(self, scopes: Sequence[str]) -> str: ...


class TokenCacheStore(Protocol):
    def load(self) -> str | None: ...

    def save(self, serialized_cache: str) -> None: ...

    def clear(self) -> None: ...
