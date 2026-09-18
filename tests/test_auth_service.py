from typing import Any

import pytest

from mi_nube.auth.errors import AuthenticationCancelled, AuthenticationConfigurationError
from mi_nube.auth.msal_service import MsalAuthService
from mi_nube.auth.token_cache import MemoryTokenCacheStore


class FakeMsalClient:
    def __init__(
        self, result: dict[str, Any], accounts: list[dict[str, Any]] | None = None
    ) -> None:
        self.result = result
        self.accounts = accounts or []
        self.removed: list[dict[str, Any]] = []

    def get_accounts(self) -> list[dict[str, Any]]:
        return self.accounts

    def acquire_token_silent(self, scopes, account):
        return None

    def acquire_token_interactive(self, scopes, prompt):
        return self.result

    def remove_account(self, account) -> None:
        self.removed.append(account)


def service_with(client: FakeMsalClient) -> MsalAuthService:
    return MsalAuthService(
        "00000000-0000-0000-0000-000000000001",
        "common",
        MemoryTokenCacheStore(),
        client_factory=lambda **kwargs: client,
    )


def test_interactive_sign_in_returns_profile_without_exposing_token() -> None:
    service = service_with(
        FakeMsalClient(
            {
                "access_token": "must-not-reach-profile",
                "id_token_claims": {
                    "oid": "owner-id",
                    "name": "Efraín Salazar",
                    "preferred_username": "efrain@example.com",
                    "tid": "tenant-id",
                },
            }
        )
    )

    profile = service.sign_in()

    assert profile.user_id == "owner-id"
    assert profile.display_name == "Efraín Salazar"
    assert profile.email == "efrain@example.com"
    assert "token" not in profile.__slots__


def test_cancelled_interactive_sign_in_has_typed_error() -> None:
    service = service_with(FakeMsalClient({"error": "access_denied"}))
    with pytest.raises(AuthenticationCancelled):
        service.sign_in()


def test_missing_client_id_has_actionable_error() -> None:
    service = MsalAuthService(None, "common", MemoryTokenCacheStore())
    with pytest.raises(AuthenticationConfigurationError, match="MICROSOFT_CLIENT_ID"):
        service.sign_in()


def test_cached_account_restores_profile_without_network() -> None:
    account = {
        "local_account_id": "owner-id",
        "name": "Efraín Salazar",
        "username": "efrain@example.com",
        "realm": "tenant-id",
    }
    service = service_with(FakeMsalClient({}, [account]))
    assert service.current_profile().email == "efrain@example.com"


class UnreadableCacheStore(MemoryTokenCacheStore):
    def load(self) -> str | None:
        raise OSError("encrypted for another Windows user")


def test_unreadable_protected_cache_is_discarded() -> None:
    store = UnreadableCacheStore()
    service = MsalAuthService(None, "common", store)
    assert service.current_profile() is None
    assert store.value is None
