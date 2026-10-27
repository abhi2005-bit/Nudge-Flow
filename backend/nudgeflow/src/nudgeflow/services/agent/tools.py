"""Messaging tools with an opt-in WhatsApp Cloud API implementation."""

import re
from typing import Protocol

import httpx

from nudgeflow.config import settings


class MessagingTool(Protocol):
    name: str

    def send(
        self,
        *,
        run_id: int,
        message: str,
        recipient_phone: str,
    ) -> dict[str, object]: ...


class MockMessagingTool:
    """Safe local tool that records acceptance without contacting a provider."""

    name = "mock_messaging"

    def send(
        self,
        *,
        run_id: int,
        message: str,
        recipient_phone: str,
    ) -> dict[str, object]:
        del message, recipient_phone
        return {
            "provider": "mock",
            "message_id": f"mock-{run_id}",
            "run_id": run_id,
            "accepted": True,
        }


class WhatsAppOutcomeUncertainError(RuntimeError):
    """The provider may have accepted the request, so it must not be retried."""


class WhatsAppCloudMessagingTool:
    """Send text via Meta's WhatsApp Cloud API; acceptance is not delivery."""

    name = "whatsapp_cloud_api"
    _recipient_pattern = re.compile(r"^\+[1-9][0-9]{7,14}$")
    _version_pattern = re.compile(r"^v[0-9]+\.[0-9]+$")

    def send(
        self,
        *,
        run_id: int,
        message: str,
        recipient_phone: str,
    ) -> dict[str, object]:
        if not settings.whatsapp_enabled:
            raise RuntimeError("WhatsApp sending is disabled.")
        if not isinstance(recipient_phone, str) or not self._recipient_pattern.fullmatch(recipient_phone):
            raise ValueError("Recipient must be in international E.164 format.")
        if not isinstance(message, str) or not message.strip() or len(message) > 4096:
            raise ValueError("Message must contain 1 to 4096 characters.")
        token = settings.whatsapp_access_token.get_secret_value()
        phone_number_id = settings.whatsapp_phone_number_id
        version = settings.whatsapp_api_version
        if not token or not phone_number_id or not phone_number_id.isdigit():
            raise RuntimeError("WhatsApp Cloud API credentials are not configured.")
        if not self._version_pattern.fullmatch(version):
            raise RuntimeError("WhatsApp API version is invalid.")

        endpoint = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_phone[1:],
            "type": "text",
            "text": {"preview_url": False, "body": message},
        }
        # No retries: a timeout or transport failure may occur after Meta accepted it.
        with httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
            response = client.post(
                endpoint,
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )

        if 400 <= response.status_code < 500:
            # A provider error response is a definitive rejection. Never surface its
            # body because it may contain request data or provider diagnostics.
            return {
                "provider": self.name,
                "message_id": None,
                "run_id": run_id,
                "accepted": False,
            }
        if not 200 <= response.status_code < 300:
            raise WhatsAppOutcomeUncertainError("WhatsApp provider outcome is uncertain.")
        try:
            body = response.json()
            messages = body.get("messages") if isinstance(body, dict) else None
            message_id = messages[0].get("id") if isinstance(messages, list) and messages else None
        except (ValueError, TypeError, AttributeError, IndexError):
            message_id = None
        if not isinstance(message_id, str) or not message_id:
            raise WhatsAppOutcomeUncertainError("WhatsApp provider outcome is uncertain.")
        return {
            "provider": self.name,
            "message_id": message_id,
            "run_id": run_id,
            "accepted": True,
        }


# Existing or previously approved mock runs remain bound to the mock provider.
# The WhatsApp tool is available only when the explicit opt-in flag is true.
TOOL_REGISTRY: dict[str, MessagingTool] = {
    MockMessagingTool.name: MockMessagingTool(),
}
if settings.whatsapp_enabled:
    TOOL_REGISTRY[WhatsAppCloudMessagingTool.name] = WhatsAppCloudMessagingTool()
