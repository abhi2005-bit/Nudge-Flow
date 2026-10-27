import httpx
import pytest
from pydantic import SecretStr

from nudgeflow.config import Settings, settings
from nudgeflow.services.agent.tools import (
    MockMessagingTool,
    WhatsAppCloudMessagingTool,
    WhatsAppOutcomeUncertainError,
)


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class FakeClient:
    def __init__(self, response=None, error=None, calls=None, **kwargs):
        self.response = response
        self.error = error
        self.calls = calls if calls is not None else []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, url, *, headers, json):
        self.calls.append((url, headers, json))
        if self.error:
            raise self.error
        return self.response


def configured(monkeypatch, *, enabled=True):
    monkeypatch.setattr(settings, "whatsapp_enabled", enabled)
    monkeypatch.setattr(settings, "whatsapp_access_token", SecretStr("test-token"))
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "1234567890")
    monkeypatch.setattr(settings, "whatsapp_api_version", "v25.0")


def test_mock_tool_works_without_whatsapp_credentials():
    result = MockMessagingTool().send(
        run_id=7, message="hello", recipient_phone="+919876543210"
    )
    assert result == {
        "provider": "mock",
        "message_id": "mock-7",
        "run_id": 7,
        "accepted": True,
    }


def test_whatsapp_is_disabled_by_default():
    config = Settings(_env_file=None)
    assert config.whatsapp_enabled is False
    assert config.whatsapp_access_token.get_secret_value() == ""


def test_disabled_whatsapp_tool_performs_no_network_calls(monkeypatch):
    configured(monkeypatch, enabled=False)
    monkeypatch.setattr(
        "nudgeflow.services.agent.tools.httpx.Client",
        lambda **_kwargs: pytest.fail("network client must not be created"),
    )
    with pytest.raises(RuntimeError, match="disabled"):
        WhatsAppCloudMessagingTool().send(
            run_id=1, message="hello", recipient_phone="+919876543210"
        )


def test_provider_acceptance_is_normalized_and_does_not_claim_delivery(monkeypatch):
    configured(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "nudgeflow.services.agent.tools.httpx.Client",
        lambda **kwargs: FakeClient(
            response=FakeResponse(200, {"messages": [{"id": "wamid.test"}]}),
            calls=calls,
            **kwargs,
        ),
    )

    result = WhatsAppCloudMessagingTool().send(
        run_id=4, message="Hi Mira", recipient_phone="+919876543210"
    )

    assert result == {
        "provider": "whatsapp_cloud_api",
        "message_id": "wamid.test",
        "run_id": 4,
        "accepted": True,
    }
    url, headers, payload = calls[0]
    assert url == "https://graph.facebook.com/v25.0/1234567890/messages"
    assert headers["Authorization"] == "Bearer test-token"
    assert payload["to"] == "919876543210"
    assert payload["text"]["body"] == "Hi Mira"
    assert len(calls) == 1


def test_definitive_provider_rejection_is_sanitized(monkeypatch):
    configured(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "nudgeflow.services.agent.tools.httpx.Client",
        lambda **kwargs: FakeClient(
            response=FakeResponse(400, {"error": {"message": "secret and phone"}}),
            calls=calls,
            **kwargs,
        ),
    )
    result = WhatsAppCloudMessagingTool().send(
        run_id=4, message="private body", recipient_phone="+919876543210"
    )
    assert result["accepted"] is False
    assert result["message_id"] is None
    assert "secret" not in repr(result)
    assert "private body" not in repr(result)
    assert "919876543210" not in repr(result)
    assert len(calls) == 1


@pytest.mark.parametrize("error", [httpx.TimeoutException("timeout"), httpx.ConnectError("failed")])
def test_ambiguous_network_failure_is_not_retried(monkeypatch, error):
    configured(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "nudgeflow.services.agent.tools.httpx.Client",
        lambda **kwargs: FakeClient(error=error, calls=calls, **kwargs),
    )
    with pytest.raises(type(error)):
        WhatsAppCloudMessagingTool().send(
            run_id=4, message="hello", recipient_phone="+919876543210"
        )
    assert len(calls) == 1


def test_success_response_without_message_id_is_uncertain(monkeypatch):
    configured(monkeypatch)
    calls = []
    monkeypatch.setattr(
        "nudgeflow.services.agent.tools.httpx.Client",
        lambda **kwargs: FakeClient(
            response=FakeResponse(200, {"messages": []}), calls=calls, **kwargs
        ),
    )
    with pytest.raises(WhatsAppOutcomeUncertainError):
        WhatsAppCloudMessagingTool().send(
            run_id=4, message="hello", recipient_phone="+919876543210"
        )
    assert len(calls) == 1


@pytest.mark.parametrize(
    "message, phone",
    [("", "+919876543210"), ("Hi", "not-a-phone"), ("x" * 4097, "+919876543210")],
)
def test_invalid_payload_is_rejected_before_network(monkeypatch, message, phone):
    configured(monkeypatch)
    monkeypatch.setattr(
        "nudgeflow.services.agent.tools.httpx.Client",
        lambda **_kwargs: pytest.fail("invalid payload must not make a request"),
    )
    with pytest.raises(ValueError):
        WhatsAppCloudMessagingTool().send(run_id=1, message=message, recipient_phone=phone)
