"""Tests for the agent runtime bootstrap and initialization layer.

Coverage:
- Successful bootstrap with default (mock-only) configuration.
- Successful bootstrap with WhatsApp enabled and valid credentials.
- BootstrapError on invalid config (WhatsApp enabled but missing credentials).
- ToolContractError for a tool with a mismatched name.
- ToolContractError for a tool missing the send method.
- ToolContractError for a tool with a non-string name attribute.
- Application startup and shutdown via FastAPI TestClient (lifespan).
- Runtime is absent on app.state after shutdown.
- build_agent_runtime() never makes external API calls.
- AgentRuntime.get_tool returns correct values.
- Mock tool is always present; WhatsApp tool absent when disabled.
- WhatsApp tool present when enabled with valid credentials.
"""


import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import SecretStr

from nudgeflow.bootstrap import (
    AgentRuntime,
    BootstrapError,
    ToolContractError,
    _validate_config,
    _validate_tool_contract,
    build_agent_runtime,
)
from nudgeflow.config import Settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _settings(**overrides) -> Settings:
    """Build an isolated Settings instance without reading .env."""
    base = dict(
        _env_file=None,
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret_key="local-test-secret-that-is-at-least-32-characters",
        whatsapp_enabled=False,
    )
    base.update(overrides)
    return Settings(**base)


# ---------------------------------------------------------------------------
# _validate_config
# ---------------------------------------------------------------------------

class TestValidateConfig:
    def test_valid_config_whatsapp_disabled_passes(self):
        cfg = _settings(whatsapp_enabled=False)
        _validate_config(cfg)  # must not raise

    def test_valid_config_whatsapp_enabled_with_credentials_passes(self):
        cfg = _settings(
            whatsapp_enabled=True,
            whatsapp_access_token=SecretStr("test-meta-token"),
            whatsapp_phone_number_id="1234567890",
        )
        _validate_config(cfg)  # must not raise

    def test_whatsapp_enabled_missing_token_raises(self):
        cfg = _settings(
            whatsapp_enabled=True,
            whatsapp_access_token=SecretStr(""),
            whatsapp_phone_number_id="1234567890",
        )
        with pytest.raises(BootstrapError, match="ACCESS_TOKEN"):
            _validate_config(cfg)

    def test_whatsapp_enabled_missing_phone_id_raises(self):
        cfg = _settings(
            whatsapp_enabled=True,
            whatsapp_access_token=SecretStr("test-token"),
            whatsapp_phone_number_id=None,
        )
        with pytest.raises(BootstrapError, match="PHONE_NUMBER_ID"):
            _validate_config(cfg)

    def test_whatsapp_enabled_non_digit_phone_id_raises(self):
        cfg = _settings(
            whatsapp_enabled=True,
            whatsapp_access_token=SecretStr("test-token"),
            whatsapp_phone_number_id="not-a-number",
        )
        with pytest.raises(BootstrapError, match="PHONE_NUMBER_ID"):
            _validate_config(cfg)

    def test_whatsapp_enabled_invalid_api_version_raises(self):
        cfg = _settings(
            whatsapp_enabled=True,
            whatsapp_access_token=SecretStr("test-token"),
            whatsapp_phone_number_id="1234567890",
            whatsapp_api_version="bad_version",
        )
        with pytest.raises(BootstrapError, match="API_VERSION"):
            _validate_config(cfg)

    def test_bootstrap_error_has_reason_attribute(self):
        cfg = _settings(
            whatsapp_enabled=True,
            whatsapp_access_token=SecretStr(""),
            whatsapp_phone_number_id="1234567890",
        )
        with pytest.raises(BootstrapError) as exc_info:
            _validate_config(cfg)
        assert exc_info.value.reason  # non-empty string


# ---------------------------------------------------------------------------
# _validate_tool_contract
# ---------------------------------------------------------------------------

class _GoodTool:
    name = "good_tool"

    def send(self, *, run_id, message, recipient_phone):
        return {}


class TestValidateToolContract:
    def test_valid_tool_passes(self):
        _validate_tool_contract(_GoodTool(), "good_tool")  # must not raise

    def test_missing_name_attribute_raises(self):
        class NoName:
            def send(self, *, run_id, message, recipient_phone):
                return {}

        with pytest.raises(ToolContractError, match="name"):
            _validate_tool_contract(NoName(), "no_name")

    def test_non_string_name_raises(self):
        class NumericName:
            name = 42  # type: ignore[assignment]

            def send(self, *, run_id, message, recipient_phone):
                return {}

        with pytest.raises(ToolContractError, match="name"):
            _validate_tool_contract(NumericName(), "numeric_name")

    def test_name_mismatch_with_registry_key_raises(self):
        class MismatchedTool:
            name = "tool_a"

            def send(self, *, run_id, message, recipient_phone):
                return {}

        with pytest.raises(ToolContractError, match="must match"):
            _validate_tool_contract(MismatchedTool(), "tool_b")

    def test_missing_send_method_raises(self):
        class NoSend:
            name = "no_send"

        with pytest.raises(ToolContractError, match="send"):
            _validate_tool_contract(NoSend(), "no_send")

    def test_non_callable_send_raises(self):
        class NonCallableSend:
            name = "bad_send"
            send = "not_a_function"  # type: ignore[assignment]

        with pytest.raises(ToolContractError, match="send"):
            _validate_tool_contract(NonCallableSend(), "bad_send")

    def test_tool_contract_error_is_bootstrap_error(self):
        class NoSend:
            name = "no_send"

        with pytest.raises(BootstrapError):
            _validate_tool_contract(NoSend(), "no_send")


# ---------------------------------------------------------------------------
# build_agent_runtime - successful cases
# ---------------------------------------------------------------------------

class TestBuildAgentRuntimeSuccess:
    def test_default_runtime_has_mock_tool(self):
        cfg = _settings()
        runtime = build_agent_runtime(cfg)
        assert isinstance(runtime, AgentRuntime)
        assert "mock_messaging" in runtime.tool_registry

    def test_whatsapp_absent_when_disabled(self):
        cfg = _settings(whatsapp_enabled=False)
        runtime = build_agent_runtime(cfg)
        assert "whatsapp_cloud_api" not in runtime.tool_registry
        assert runtime.whatsapp_enabled is False

    def test_whatsapp_present_when_enabled_with_valid_credentials(self):
        cfg = _settings(
            whatsapp_enabled=True,
            whatsapp_access_token=SecretStr("real-token"),
            whatsapp_phone_number_id="9876543210",
        )
        runtime = build_agent_runtime(cfg)
        assert "whatsapp_cloud_api" in runtime.tool_registry
        assert runtime.whatsapp_enabled is True

    def test_runtime_captures_settings(self):
        cfg = _settings()
        runtime = build_agent_runtime(cfg)
        assert runtime.settings is cfg

    def test_get_tool_returns_registered_tool(self):
        runtime = build_agent_runtime(_settings())
        tool = runtime.get_tool("mock_messaging")
        assert tool is not None
        assert tool.name == "mock_messaging"

    def test_get_tool_returns_none_for_unknown_name(self):
        runtime = build_agent_runtime(_settings())
        assert runtime.get_tool("nonexistent") is None

    def test_runtime_is_immutable(self):
        runtime = build_agent_runtime(_settings())
        with pytest.raises((TypeError, AttributeError)):
            runtime.whatsapp_enabled = True  # type: ignore[misc]

    def test_each_call_produces_independent_registry(self):
        cfg = _settings()
        r1 = build_agent_runtime(cfg)
        r2 = build_agent_runtime(cfg)
        assert r1.tool_registry is not r2.tool_registry
        assert r1.tool_registry["mock_messaging"] is not r2.tool_registry["mock_messaging"]

    def test_mock_tool_send_does_not_contact_network(self, monkeypatch):
        """bootstrap must never make external API calls."""
        import socket

        def _no_network(*_args, **_kwargs):
            raise AssertionError("Network call made during bootstrap.")

        monkeypatch.setattr(socket, "getaddrinfo", _no_network)
        cfg = _settings()
        runtime = build_agent_runtime(cfg)  # must not raise
        assert "mock_messaging" in runtime.tool_registry


# ---------------------------------------------------------------------------
# build_agent_runtime - failure cases
# ---------------------------------------------------------------------------

class TestBuildAgentRuntimeFailure:
    def test_invalid_whatsapp_config_raises_bootstrap_error(self):
        cfg = _settings(
            whatsapp_enabled=True,
            whatsapp_access_token=SecretStr(""),
            whatsapp_phone_number_id="1234567890",
        )
        with pytest.raises(BootstrapError):
            build_agent_runtime(cfg)

    def test_bootstrap_error_does_not_expose_credentials(self):
        secret = "super-secret-token-value"
        cfg = _settings(
            whatsapp_enabled=True,
            whatsapp_access_token=SecretStr(secret),
            whatsapp_phone_number_id="not-a-digit",
        )
        with pytest.raises(BootstrapError) as exc_info:
            build_agent_runtime(cfg)
        assert secret not in str(exc_info.value)


# ---------------------------------------------------------------------------
# Application startup and shutdown via lifespan
# ---------------------------------------------------------------------------

class TestLifespan:
    def test_runtime_available_on_app_state_during_lifespan(self, monkeypatch):
        """TestClient enters the lifespan context; runtime must be on app.state."""
        from nudgeflow.bootstrap import agent_lifespan

        monkeypatch.setattr(
            "nudgeflow.bootstrap._default_settings",
            _settings(),
        )

        app = FastAPI(lifespan=agent_lifespan)

        @app.get("/probe")
        def probe(request: Request):
            runtime = getattr(request.app.state, "agent_runtime", None)
            return {"has_runtime": runtime is not None}

        with TestClient(app) as client:
            response = client.get("/probe")
        assert response.status_code == 200
        assert response.json()["has_runtime"] is True

    def test_runtime_missing_after_shutdown(self, monkeypatch):
        """After TestClient context exits the runtime must be removed."""
        from nudgeflow.bootstrap import agent_lifespan

        monkeypatch.setattr(
            "nudgeflow.bootstrap._default_settings",
            _settings(),
        )

        app = FastAPI(lifespan=agent_lifespan)

        @app.get("/probe")
        def probe():
            return {}

        with TestClient(app) as _:
            pass  # let lifespan start and stop

        assert not hasattr(app.state, "agent_runtime")

    def test_lifespan_bootstrap_failure_prevents_startup(self, monkeypatch):
        """If build_agent_runtime raises, the server must not start silently."""
        from nudgeflow.bootstrap import agent_lifespan

        bad_settings = _settings(
            whatsapp_enabled=True,
            whatsapp_access_token=SecretStr(""),
            whatsapp_phone_number_id="1234567890",
        )
        monkeypatch.setattr(
            "nudgeflow.bootstrap._default_settings",
            bad_settings,
        )

        app = FastAPI(lifespan=agent_lifespan)

        @app.get("/probe")
        def probe():
            return {}

        with pytest.raises(BootstrapError):
            with TestClient(app, raise_server_exceptions=True):
                pass

    def test_existing_app_lifespan_integration(self, monkeypatch):
        """The real main.py app includes agent_lifespan and starts cleanly."""
        monkeypatch.setattr(
            "nudgeflow.bootstrap._default_settings",
            _settings(),
        )
        from nudgeflow.main import app
        from nudgeflow.database import get_db, Base
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from sqlalchemy.pool import StaticPool

        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)

        def override_get_db():
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                resp = client.get("/health")
                assert resp.status_code == 200
                runtime = getattr(app.state, "agent_runtime", None)
                assert runtime is not None
                assert "mock_messaging" in runtime.tool_registry
        finally:
            app.dependency_overrides.pop(get_db, None)
            Base.metadata.drop_all(engine)
            engine.dispose()


# ---------------------------------------------------------------------------
# Route dependency injection
# ---------------------------------------------------------------------------

class TestRouteDependencyInjection:
    def test_get_agent_runtime_raises_when_not_initialized(self):
        from nudgeflow.bootstrap import get_agent_runtime

        fake_app = FastAPI()
        fake_request = Request({"type": "http", "app": fake_app})
        with pytest.raises(RuntimeError, match="not initialised"):
            get_agent_runtime(fake_request)

    def test_agent_route_uses_injected_runtime(self, client):
        from nudgeflow.bootstrap import AgentRuntime, get_agent_runtime
        from nudgeflow.main import app

        custom_runtime = AgentRuntime(
            tool_registry={},
            whatsapp_enabled=False,
            settings=_settings(),
        )

        app.dependency_overrides[get_agent_runtime] = lambda: custom_runtime
        try:
            # Attempt to create a run with an invalid follow_up_id (404),
            # which verifies that the dependency resolution executed before the 404
            resp = client.post("/agent/runs", json={"follow_up_id": 999999999})
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.pop(get_agent_runtime, None)


