"""Small optional Groq-compatible chat client; no request is retried automatically."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from nudgeflow.config import Settings, settings

GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_USER_AGENT = f"NudgeFlow/{settings.app_version}"


class LLMProviderError(Exception):
    """Provider failure with a safe code that can be persisted without raw details."""

    def __init__(self, error_code: str):
        super().__init__(error_code)
        self.error_code = error_code


class GroqChatClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: int,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._user_agent = user_agent

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
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": self._user_agent,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                response_body = response.read(64_001)
            if len(response_body) > 64_000:
                raise LLMProviderError("provider_response_too_large")
            headers = getattr(response, "headers", None)
            get_charset = getattr(headers, "get_content_charset", None)
            charset = (get_charset() if callable(get_charset) else None) or "utf-8"
            try:
                response_text = response_body.decode(charset)
            except (UnicodeDecodeError, LookupError):
                response_text = response_body.decode("utf-8", errors="replace")
            decoded = json.loads(response_text)
            content = decoded["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise LLMProviderError("provider_invalid_response")
            return content
        except HTTPError as exc:
            if exc.code == 401:
                code = "provider_authentication_failed"
            elif exc.code == 403:
                code = "provider_permission_denied"
            elif exc.code == 404:
                code = "provider_model_not_found"
            elif exc.code == 400:
                code = "provider_invalid_request"
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


def get_llm_client(cfg: Settings | None = None) -> GroqChatClient | None:
    """Return a client only when both key and model are configured."""

    active_settings = cfg if cfg is not None else settings
    api_key = active_settings.llm_api_key.get_secret_value().strip()
    model = (active_settings.llm_model or "").strip()
    if not api_key or not model:
        return None
    return GroqChatClient(
        api_key=api_key,
        model=model,
        timeout_seconds=active_settings.llm_timeout_seconds,
        user_agent=f"NudgeFlow/{active_settings.app_version}",
    )
