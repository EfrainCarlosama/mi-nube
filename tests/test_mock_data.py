from datetime import datetime

from mi_nube.services.mock_data import MockDataService


def test_mock_data_is_deterministic_with_fixed_time() -> None:
    now = datetime(2026, 9, 17, 12, 0)
    service = MockDataService(now=now)
    assert len(service.projects()) == 3
    assert service.projects()[0].modified_at < now
    assert service.storage().ratio > 0
    assert any(item.kind == "Carpeta" for item in service.personal_items())
