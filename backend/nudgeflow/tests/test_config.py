
from nudgeflow.config import Settings


def test_settings_use_defaults():
    config = Settings(_env_file=None)

    assert config.app_name == "NudgeFlow API"
    assert config.app_version == "0.1.0"
    assert config.environment == "development"
    assert config.debug is False


def test_settings_read_environment_variables(monkeypatch):
    monkeypatch.setenv("NUDGEFLOW_APP_NAME", "NudgeFlow Test")
    monkeypatch.setenv("NUDGEFLOW_DEBUG", "true")

    config = Settings(_env_file=None)

    assert config.app_name == "NudgeFlow Test"
    assert config.debug is True
