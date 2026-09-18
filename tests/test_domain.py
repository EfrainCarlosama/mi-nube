from datetime import UTC, datetime, timedelta

from mi_nube.domain.identity import public_display_name
from mi_nube.domain.models import StorageSummary
from mi_nube.domain.permissions import DEFAULT_CAPABILITIES, Capability, PermissionLevel
from mi_nube.ui.formatters import relative_time


def test_storage_ratio_is_clamped() -> None:
    assert StorageSummary(used_bytes=50, total_bytes=100).ratio == 0.5
    assert StorageSummary(used_bytes=120, total_bytes=100).ratio == 1.0
    assert StorageSummary(used_bytes=1, total_bytes=0).ratio == 0.0


def test_full_control_contains_all_capabilities() -> None:
    full = DEFAULT_CAPABILITIES[PermissionLevel.FULL_CONTROL]
    for capability in Capability:
        if capability is not Capability.NONE:
            assert capability in full


def test_view_only_does_not_allow_download() -> None:
    view_only = DEFAULT_CAPABILITIES[PermissionLevel.VIEW_ONLY]
    assert Capability.VIEW in view_only
    assert Capability.DOWNLOAD not in view_only


def test_relative_time_accepts_timezone_aware_values() -> None:
    now = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
    assert relative_time(now - timedelta(hours=2), now) == "Hace 2 h"


def test_public_display_name_never_returns_an_email() -> None:
    assert public_display_name("Juan Caballero", "Usuario") == "Juan Caballero"
    assert public_display_name(" propietario@example.com ", "Propietario") == "Propietario"
    assert public_display_name("", "Usuario") == "Usuario"
