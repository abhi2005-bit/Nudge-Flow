
import pytest

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
    monkeypatch.setenv(
        "NUDGEFLOW_JWT_SECRET_KEY",
        "local-test-secret-that-is-at-least-32-characters",
    )
    monkeypatch.setenv(
        "NUDGEFLOW_JWT_SECRET_KEY",
        "local-test-secret-that-is-at-least-32-characters",
    )

    config = Settings(_env_file=None)

    assert config.app_name == "NudgeFlow Test"
    assert config.debug is True
    assert config.jwt_secret_key.get_secret_value().startswith("local-test-secret")
    assert config.jwt_secret_key.get_secret_value().startswith("local-test-secret")


def test_production_settings_require_a_strong_jwt_secret():
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        Settings(
            _env_file=None,
            environment="production",
            jwt_secret_key="short",
        )


def test_production_settings_reject_debug_mode():
    with pytest.raises(ValueError, match="DEBUG"):
        Settings(
            _env_file=None,
            environment="production",
            jwt_secret_key="safe-test-secret-that-is-at-least-32-chars",
            debug=True,
        )


def test_production_settings_reject_example_jwt_secret():
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        Settings(
            _env_file=None,
            environment="production",
            jwt_secret_key="replace-with-a-random-secret-of-at-least-32-characters",
        )


def test_settings_reject_wildcard_cors():
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings(_env_file=None, cors_origins=["*"])
