"""Hermetic regression tests for the Groq LLM client."""

import json
from urllib.error import HTTPError, URLError

import pytest
from pydantic import SecretStr

from nudgeflow.config import Settings
from nudgeflow.services.agent.llm_client import (
    GROQ_CHAT_COMPLETIONS_URL,
    GroqChatClient,
    LLMProviderError,
    get_llm_client,
)


class MockHTTPResponse:
    def __init__(self, data: bytes, status: int = 200) -> None:
        self._data = data
        self.status = status

    def read(self, n: int = -1) -> bytes:
        if n == -1 or n >= len(self._data):
            res = self._data
            self._data = b""
            return res
        res = self._data[:n]
        self._data = self._data[n:]
        return res

    def __enter__(self) -> "MockHTTPResponse":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        return False


def test_groq_client_payload_headers_and_parsing(monkeypatch):
    """Client sends correct URL, bearer auth, User-Agent, and parses completion."""
    captured: list[tuple] = []

    expected_output = json.dumps({"request_summary": "Inquiry about service"})
    groq_api_response = {
        "id": "chatcmpl-mock-123",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": expected_output,
                },
                "finish_reason": "stop",
            }
        ],
    }

    def fake_urlopen(request, timeout):
        captured.append((request, timeout))
        return MockHTTPResponse(json.dumps(groq_api_response).encode("utf-8"))

    monkeypatch.setattr("nudgeflow.services.agent.llm_client.urlopen", fake_urlopen)

    client = GroqChatClient(
        api_key="mock-api-key-test-only",
        model="openai/gpt-oss-20b",
        timeout_seconds=12,
        user_agent="NudgeFlow/0.1.0",
    )

    result = client.complete_json(
        system_prompt="You are an extractor.",
        user_prompt="Customer message text.",
    )

    assert result == expected_output
    assert len(captured) == 1
    req, timeout = captured[0]

    assert timeout == 12
    assert req.full_url == GROQ_CHAT_COMPLETIONS_URL
    assert req.get_method() == "POST"

    # Verify headers: Bearer token, JSON content type, and User-Agent
    assert req.get_header("Authorization") == "Bearer mock-api-key-test-only"
    assert req.get_header("Content-type") == "application/json; charset=utf-8"
    assert req.get_header("User-agent") == "NudgeFlow/0.1.0"

    # Verify payload format
    payload = json.loads(req.data.decode("utf-8"))
    assert payload["model"] == "openai/gpt-oss-20b"
    assert payload["temperature"] == 0
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"] == [
        {"role": "system", "content": "You are an extractor."},
        {"role": "user", "content": "Customer message text."},
    ]


def test_missing_or_blank_configuration_returns_none():
    """get_llm_client returns None when API key or model is missing."""
    cfg_no_key = Settings(
        llm_api_key=SecretStr(""),
        llm_model="openai/gpt-oss-20b",
    )
    assert get_llm_client(cfg_no_key) is None

    cfg_no_model = Settings(
        llm_api_key=SecretStr("mock-key"),
        llm_model=None,
    )
    assert get_llm_client(cfg_no_model) is None

    cfg_whitespace = Settings(
        llm_api_key=SecretStr("   "),
        llm_model="   ",
    )
    assert get_llm_client(cfg_whitespace) is None

    cfg_valid = Settings(
        llm_api_key=SecretStr("mock-valid-key"),
        llm_model="openai/gpt-oss-20b",
        llm_timeout_seconds=20,
    )
    client = get_llm_client(cfg_valid)
    assert client is not None
    assert client._model == "openai/gpt-oss-20b"
    assert client._timeout_seconds == 20
    assert client._api_key == "mock-valid-key"


@pytest.mark.parametrize(
    ("http_status", "expected_code"),
    [
        (401, "provider_authentication_failed"),
        (403, "provider_permission_denied"),
        (404, "provider_model_not_found"),
        (400, "provider_invalid_request"),
        (429, "provider_rate_limited"),
        (500, "provider_request_failed"),
        (503, "provider_request_failed"),
    ],
)
def test_http_error_classification(monkeypatch, http_status, expected_code):
    """HTTP status codes are mapped to sanitized provider error codes."""
    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, http_status, f"HTTP {http_status}", {}, None)

    monkeypatch.setattr("nudgeflow.services.agent.llm_client.urlopen", fake_urlopen)

    client = GroqChatClient(
        api_key="mock-key",
        model="openai/gpt-oss-20b",
        timeout_seconds=10,
    )

    with pytest.raises(LLMProviderError) as exc_info:
        client.complete_json(system_prompt="sys", user_prompt="user")

    assert exc_info.value.error_code == expected_code
    assert str(exc_info.value) == expected_code
    # Confirm credentials are not exposed
    assert "mock-key" not in repr(exc_info.value)


def test_timeout_and_network_errors(monkeypatch):
    """Network connection errors and timeouts map to distinct codes."""
    client = GroqChatClient(api_key="mock-key", model="test-model", timeout_seconds=5)

    def fake_timeout(request, timeout):
        raise TimeoutError("Socket timeout")

    monkeypatch.setattr("nudgeflow.services.agent.llm_client.urlopen", fake_timeout)
    with pytest.raises(LLMProviderError) as exc_info:
        client.complete_json(system_prompt="sys", user_prompt="user")
    assert exc_info.value.error_code == "provider_timeout"

    def fake_connection_err(request, timeout):
        raise URLError(OSError("Connection refused"))

    monkeypatch.setattr("nudgeflow.services.agent.llm_client.urlopen", fake_connection_err)
    with pytest.raises(LLMProviderError) as exc_info:
        client.complete_json(system_prompt="sys", user_prompt="user")
    assert exc_info.value.error_code == "provider_connection_failed"


@pytest.mark.parametrize(
    "malformed_body",
    [
        b"not json at all",
        b"12345",
        b"[]",
        json.dumps({}).encode("utf-8"),
        json.dumps({"choices": []}).encode("utf-8"),
        json.dumps({"choices": [{}]}).encode("utf-8"),
        json.dumps({"choices": [{"message": {}}]}).encode("utf-8"),
        json.dumps({"choices": [{"message": {"content": ""}}]}).encode("utf-8"),
        json.dumps({"choices": [{"message": {"content": 100}}]}).encode("utf-8"),
        json.dumps({"choices": [{"message": {"content": None}}]}).encode("utf-8"),
    ],
)
def test_malformed_json_responses(monkeypatch, malformed_body):
    """Malformed or unexpected response structures raise provider_invalid_response."""
    def fake_urlopen(request, timeout):
        return MockHTTPResponse(malformed_body)

    monkeypatch.setattr("nudgeflow.services.agent.llm_client.urlopen", fake_urlopen)

    client = GroqChatClient(api_key="mock-key", model="test-model", timeout_seconds=5)
    with pytest.raises(LLMProviderError) as exc_info:
        client.complete_json(system_prompt="sys", user_prompt="user")
    assert exc_info.value.error_code == "provider_invalid_response"


def test_response_too_large(monkeypatch):
    """Responses exceeding 64KB raise provider_response_too_large."""
    large_body = b"A" * 64_005

    def fake_urlopen(request, timeout):
        return MockHTTPResponse(large_body)

    monkeypatch.setattr("nudgeflow.services.agent.llm_client.urlopen", fake_urlopen)

    client = GroqChatClient(api_key="mock-key", model="test-model", timeout_seconds=5)
    with pytest.raises(LLMProviderError) as exc_info:
        client.complete_json(system_prompt="sys", user_prompt="user")
    assert exc_info.value.error_code == "provider_response_too_large"


def test_groq_client_unicode_response_preservation(monkeypatch):
    """Groq client faithfully preserves UTF-8 text (apostrophes, accents, symbols, emojis)."""
    unicode_content = json.dumps(
        {"message": "Hi Mira, you’re welcome to visit our café! ₹500 discount for you. ✨"},
        ensure_ascii=False,
    )
    response_data = {
        "choices": [
            {
                "message": {"content": unicode_content},
            }
        ]
    }
    encoded_body = json.dumps(response_data, ensure_ascii=False).encode("utf-8")

    class MockUTF8Response(MockHTTPResponse):
        class Headers:
            @staticmethod
            def get_content_charset():
                return "utf-8"

        headers = Headers()

    def fake_urlopen(request, timeout):
        return MockUTF8Response(encoded_body)

    monkeypatch.setattr("nudgeflow.services.agent.llm_client.urlopen", fake_urlopen)

    client = GroqChatClient(api_key="mock-key", model="test-model", timeout_seconds=5)
    result = client.complete_json(system_prompt="sys", user_prompt="user")
    assert result == unicode_content
    assert "you’re" in result
    assert "café" in result
    assert "₹500" in result
    assert "✨" in result
