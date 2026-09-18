from pathlib import Path

from mi_nube.app.settings import Settings


def test_settings_use_explicit_data_directory(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MI_NUBE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MI_NUBE_LOG_LEVEL", "debug")
    settings = Settings.from_environment()
    assert settings.data_dir == tmp_path
    assert settings.log_dir == tmp_path / "logs"
    assert settings.log_level == "DEBUG"


def test_microsoft_configuration_is_optional(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MI_NUBE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("MICROSOFT_CLIENT_ID", raising=False)
    settings = Settings.from_environment(env_file=tmp_path / "does-not-exist.env")
    assert not settings.is_microsoft_configured

    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "00000000-0000-0000-0000-000000000001")
    configured = Settings.from_environment(env_file=tmp_path / "does-not-exist.env")
    assert configured.is_microsoft_configured
    assert configured.microsoft_tenant_id == "common"
