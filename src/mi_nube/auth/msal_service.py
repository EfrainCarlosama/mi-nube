from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from threading import Lock
from typing import Any

import msal

from mi_nube.auth.errors import (
    AuthenticationCancelled,
    AuthenticationConfigurationError,
    AuthenticationError,
    ReauthenticationRequired,
)
from mi_nube.auth.ports import TokenCacheStore
from mi_nube.domain.models import AccountProfile

LOGGER = logging.getLogger(__name__)
SIGN_IN_SCOPES = ("User.Read", "Files.ReadWrite")
_CANCELLED_ERRORS = {"access_denied", "authentication_canceled", "user_cancelled"}


class MsalAuthService:
    def __init__(
        self,
        client_id: str | None,
        tenant_id: str,
        cache_store: TokenCacheStore,
        client_factory: Callable[..., Any] = msal.PublicClientApplication,
    ) -> None:
        self._client_id = client_id
        self._tenant_id = tenant_id
        self._cache_store = cache_store
        self._client_factory = client_factory
        self._lock = Lock()
        self._cache = msal.SerializableTokenCache()
        self._client: Any | None = None

        try:
            serialized_cache = self._cache_store.load()
        except (OSError, UnicodeError):
            LOGGER.warning("La caché MSAL protegida no pudo descifrarse; se descartará")
            self._cache_store.clear()
            serialized_cache = None
        if serialized_cache:
            try:
                self._cache.deserialize(serialized_cache)
            except (ValueError, TypeError):
                LOGGER.warning("La caché MSAL protegida no pudo leerse; se descartará")
                self._cache_store.clear()

    @property
    def is_configured(self) -> bool:
        return bool(self._client_id)

    def _get_client(self) -> Any:
        if not self._client_id:
            raise AuthenticationConfigurationError(
                "Falta MICROSOFT_CLIENT_ID. Configura el registro de Microsoft Entra ID."
            )
        if self._client is None:
            authority = f"https://login.microsoftonline.com/{self._tenant_id}"
            self._client = self._client_factory(
                client_id=self._client_id,
                authority=authority,
                token_cache=self._cache,
            )
        return self._client

    def _persist_cache(self) -> None:
        if self._cache.has_state_changed:
            self._cache_store.save(self._cache.serialize())

    @staticmethod
    def _profile_from_account(account: Mapping[str, Any]) -> AccountProfile:
        email = str(account.get("username") or "")
        display_name = str(account.get("name") or email or "Cuenta Microsoft")
        user_id = str(
            account.get("local_account_id") or account.get("home_account_id") or email or "unknown"
        )
        tenant_id = account.get("realm")
        return AccountProfile(user_id, display_name, email, str(tenant_id) if tenant_id else None)

    @staticmethod
    def _profile_from_result(result: Mapping[str, Any]) -> AccountProfile:
        claims = result.get("id_token_claims") or {}
        if not isinstance(claims, Mapping):
            claims = {}
        email = str(
            claims.get("preferred_username") or claims.get("email") or claims.get("upn") or ""
        )
        display_name = str(claims.get("name") or email or "Cuenta Microsoft")
        user_id = str(claims.get("oid") or claims.get("sub") or email or "unknown")
        tenant_id = claims.get("tid")
        return AccountProfile(user_id, display_name, email, str(tenant_id) if tenant_id else None)

    def current_profile(self) -> AccountProfile | None:
        if not self.is_configured:
            return None
        try:
            with self._lock:
                accounts = self._get_client().get_accounts()
                return self._profile_from_account(accounts[0]) if accounts else None
        except Exception:
            LOGGER.exception("No se pudo restaurar la cuenta Microsoft desde la caché")
            return None

    def sign_in(self) -> AccountProfile:
        with self._lock:
            client = self._get_client()
            accounts = client.get_accounts()
            result: Mapping[str, Any] | None = None
            if accounts:
                result = client.acquire_token_silent(list(SIGN_IN_SCOPES), account=accounts[0])

            if not result or "access_token" not in result:
                LOGGER.info("Iniciando autenticación interactiva de Microsoft")
                result = client.acquire_token_interactive(
                    scopes=list(SIGN_IN_SCOPES),
                    prompt="select_account",
                )

            self._persist_cache()
            if "access_token" in result:
                LOGGER.info("Autenticación Microsoft completada")
                return self._profile_from_result(result)
            self._raise_auth_error(result)
            raise AssertionError("La respuesta de autenticación no produjo un resultado")

    def sign_out(self) -> None:
        if not self.is_configured:
            self._cache_store.clear()
            return
        with self._lock:
            client = self._get_client()
            for account in client.get_accounts():
                client.remove_account(account)
            self._persist_cache()
            self._cache_store.clear()
            LOGGER.info("Sesión Microsoft eliminada del equipo")

    def acquire_access_token(self, scopes: Sequence[str]) -> str:
        with self._lock:
            client = self._get_client()
            accounts = client.get_accounts()
            if not accounts:
                raise ReauthenticationRequired("Inicia sesión nuevamente para continuar.")
            result = client.acquire_token_silent(list(scopes), account=accounts[0])
            self._persist_cache()
            if result and "access_token" in result:
                return str(result["access_token"])
            if result:
                if result.get("error") in {
                    "interaction_required",
                    "consent_required",
                    "invalid_grant",
                    "no_tokens_found",
                }:
                    raise ReauthenticationRequired(
                        "Conecta OneDrive para conceder o renovar el acceso a tus archivos."
                    )
                self._raise_auth_error(result)
            raise ReauthenticationRequired("La sesión expiró. Inicia sesión nuevamente.")

    @staticmethod
    def _raise_auth_error(result: Mapping[str, Any]) -> None:
        error_code = str(result.get("error") or "authentication_failed")
        if error_code in _CANCELLED_ERRORS:
            raise AuthenticationCancelled("El inicio de sesión fue cancelado.")
        correlation_id = result.get("correlation_id")
        description = str(result.get("error_description") or "Microsoft no completó la solicitud.")
        safe_description = description.split("Trace ID:", maxsplit=1)[0].strip()
        LOGGER.warning(
            "Error de autenticación Microsoft: %s (correlation_id=%s)",
            error_code,
            correlation_id,
        )
        raise AuthenticationError(f"{safe_description} [{error_code}]")
