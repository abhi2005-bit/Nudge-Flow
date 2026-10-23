"""Small optional Groq-compatible chat client; no request is retried automatically."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from nudgeflow.config import settings

GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"


class LLMProviderError(Exception):
    """Provider failure with a safe code that can be persisted without raw details."""

    def __init__(self, error_code: str):
        super().__init__(error_code)
        self.error_code = error_code


class GroqChatClient:
    def __init__(self, *, api_key: str, model: str, timeout_seconds: int) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self._model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        request = Request(
            GROQ_CHAT_COMPLETIONS_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                response_body = response.read(64_001)
            if len(response_body) > 64_000:
                raise LLMProviderError("provider_response_too_large")
            decoded = json.loads(response_body)
            content = decoded["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise LLMProviderError("provider_invalid_response")
            return content
        except HTTPError as exc:
            if exc.code in {401, 403}:
                code = "provider_authentication_failed"
            elif exc.code == 429:
                code = "provider_rate_limited"
            else:
                code = "provider_request_failed"
            raise LLMProviderError(code) from None
        except (TimeoutError, OSError) as exc:
            # URLError is an OSError subclass. Do not include its reason or request.
            if isinstance(exc, TimeoutError):
                code = "provider_timeout"
            else:
                code = "provider_connection_failed"
            raise LLMProviderError(code) from None
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            raise LLMProviderError("provider_invalid_response") from None


def get_llm_client() -> GroqChatClient | None:
    """Return a client only when both key and model are configured."""

    api_key = settings.llm_api_key.get_secret_value().strip()
    model = (settings.llm_model or "").strip()
    if not api_key or not model:
        return None
    return GroqChatClient(
        api_key=api_key,
        model=model,
        timeout_seconds=settings.llm_timeout_seconds,
    )
