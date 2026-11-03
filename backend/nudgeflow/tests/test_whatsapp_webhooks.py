"""Tests for the WhatsApp inbound webhook foundation.

Verifies:
1. Webhook configuration validation.
2. GET /webhooks/whatsapp verification (mode, token, challenge).
3. POST /webhooks/whatsapp signature validation (HMAC-SHA256, missing/invalid/tampered).
4. Safe parsing of inbound messages and delivery statuses.
5. Idempotent event deduplication (duplicate message IDs, duplicate status events).
6. Non-association of tenant based on untrusted sender number.
7. Absence of outbound actions, agent runs, or auto-replies.
8. Zero logging of raw payloads, message content, phone numbers, or secrets.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from nudgeflow.config import Settings, validate_whatsapp_webhook_config
from nudgeflow.models.agent import AgentExecution, AgentRun
from nudgeflow.models.contact import Contact
from nudgeflow.models.tenant import Tenant
from nudgeflow.models.webhook import WhatsAppWebhookEvent


TEST_VERIFY_TOKEN = "test-webhook-verify-token-xyz"
TEST_APP_SECRET = "test-meta-app-secret-12345678"


def _sign(body: bytes, secret: str = TEST_APP_SECRET) -> str:
    """Compute X-Hub-Signature-256 header value for raw body bytes."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.fixture(autouse=True)
def configure_webhook_settings(monkeypatch):
    """Ensure webhook test credentials are configured for endpoint tests."""
    from nudgeflow.config import settings

    monkeypatch.setattr(
        settings,
        "whatsapp_webhook_verify_token",
        SecretStr(TEST_VERIFY_TOKEN),
    )
    monkeypatch.setattr(
        settings,
        "whatsapp_app_secret",
        SecretStr(TEST_APP_SECRET),
    )


# ===========================================================================
# 1. Configuration Validation Tests
# ===========================================================================

class TestWebhookConfigValidation:
    def test_valid_config_passes(self):
        cfg = Settings(
            _env_file=None,
            jwt_secret_key="local-test-secret-that-is-at-least-32-characters",
            whatsapp_webhook_verify_token=SecretStr("my-verify-token"),
            whatsapp_app_secret=SecretStr("my-app-secret"),
        )
        validate_whatsapp_webhook_config(cfg)  # must not raise

    def test_missing_verify_token_raises(self):
        cfg = Settings(
            _env_file=None,
            jwt_secret_key="local-test-secret-that-is-at-least-32-characters",
            whatsapp_webhook_verify_token=SecretStr(""),
            whatsapp_app_secret=SecretStr("my-app-secret"),
        )
        with pytest.raises(ValueError, match="VERIFY_TOKEN"):
            validate_whatsapp_webhook_config(cfg)

    def test_missing_app_secret_raises(self):
        cfg = Settings(
            _env_file=None,
            jwt_secret_key="local-test-secret-that-is-at-least-32-characters",
            whatsapp_webhook_verify_token=SecretStr("my-verify-token"),
            whatsapp_app_secret=SecretStr(""),
        )
        with pytest.raises(ValueError, match="APP_SECRET"):
            validate_whatsapp_webhook_config(cfg)

    def test_whitespace_only_token_raises(self):
        cfg = Settings(
            _env_file=None,
            jwt_secret_key="local-test-secret-that-is-at-least-32-characters",
            whatsapp_webhook_verify_token=SecretStr("   "),
            whatsapp_app_secret=SecretStr("my-app-secret"),
        )
        with pytest.raises(ValueError, match="VERIFY_TOKEN"):
            validate_whatsapp_webhook_config(cfg)


# ===========================================================================
# 2. GET /webhooks/whatsapp Verification Tests
# ===========================================================================

class TestWebhookVerification:
    def test_verification_success_returns_challenge(self, anonymous_client):
        response = anonymous_client.get(
            "/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": TEST_VERIFY_TOKEN,
                "hub.challenge": "1158201444",
            },
        )
        assert response.status_code == 200
        assert response.text == "1158201444"
        assert "text/plain" in response.headers.get("content-type", "")

    def test_verification_token_mismatch_rejected(self, anonymous_client):
        response = anonymous_client.get(
            "/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong-token",
                "hub.challenge": "1158201444",
            },
        )
        assert response.status_code == 403
        assert "mismatch" in response.text.lower()

    def test_verification_invalid_mode_rejected(self, anonymous_client):
        response = anonymous_client.get(
            "/webhooks/whatsapp",
            params={
                "hub.mode": "publish",
                "hub.verify_token": TEST_VERIFY_TOKEN,
                "hub.challenge": "1158201444",
            },
        )
        assert response.status_code == 403

    def test_verification_missing_mode_rejected(self, anonymous_client):
        response = anonymous_client.get(
            "/webhooks/whatsapp",
            params={
                "hub.verify_token": TEST_VERIFY_TOKEN,
                "hub.challenge": "1158201444",
            },
        )
        assert response.status_code == 403

    def test_verification_missing_challenge_rejected(self, anonymous_client):
        response = anonymous_client.get(
            "/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": TEST_VERIFY_TOKEN,
            },
        )
        assert response.status_code == 400

    def test_verification_unconfigured_token_rejected(self, anonymous_client, monkeypatch):
        from nudgeflow.config import settings

        monkeypatch.setattr(settings, "whatsapp_webhook_verify_token", SecretStr(""))
        response = anonymous_client.get(
            "/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": TEST_VERIFY_TOKEN,
                "hub.challenge": "1158201444",
            },
        )
        assert response.status_code == 403
        assert "not configured" in response.text.lower()


# ===========================================================================
# 3. POST /webhooks/whatsapp Signature Validation Tests
# ===========================================================================

class TestWebhookSignatureValidation:
    def test_valid_signature_accepted(self, anonymous_client):
        body = json.dumps({"object": "whatsapp_business_account", "entry": []}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _sign(body),
        }
        response = anonymous_client.post("/webhooks/whatsapp", content=body, headers=headers)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_invalid_signature_rejected(self, anonymous_client):
        body = json.dumps({"object": "whatsapp_business_account"}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=0000000000000000000000000000000000000000000000000000000000000000",
        }
        response = anonymous_client.post("/webhooks/whatsapp", content=body, headers=headers)
        assert response.status_code == 403
        assert "invalid webhook signature" in response.text.lower()

    def test_missing_signature_header_rejected(self, anonymous_client):
        body = json.dumps({"object": "whatsapp_business_account"}).encode("utf-8")
        response = anonymous_client.post("/webhooks/whatsapp", content=body)
        assert response.status_code == 403

    def test_malformed_signature_prefix_rejected(self, anonymous_client):
        body = json.dumps({"object": "whatsapp_business_account"}).encode("utf-8")
        raw_digest = hmac.new(TEST_APP_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "X-Hub-Signature-256": raw_digest,  # missing sha256= prefix
        }
        response = anonymous_client.post("/webhooks/whatsapp", content=body, headers=headers)
        assert response.status_code == 403

    def test_tampered_payload_rejected(self, anonymous_client):
        body1 = b'{"object":"whatsapp_business_account","data":1}'
        body2 = b'{"object":"whatsapp_business_account","data":2}'
        headers = {
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _sign(body1),  # signature for body1, but sending body2
        }
        response = anonymous_client.post("/webhooks/whatsapp", content=body2, headers=headers)
        assert response.status_code == 403

    def test_unconfigured_app_secret_rejected(self, anonymous_client, monkeypatch):
        from nudgeflow.config import settings

        monkeypatch.setattr(settings, "whatsapp_app_secret", SecretStr(""))
        body = b'{"object":"whatsapp_business_account"}'
        headers = {
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=abcdef",
        }
        response = anonymous_client.post("/webhooks/whatsapp", content=body, headers=headers)
        assert response.status_code == 403
        assert "not configured" in response.text.lower()


# ===========================================================================
# 4. Malformed Payloads Tests
# ===========================================================================

class TestWebhookMalformedPayloads:
    def test_non_json_payload_rejected(self, anonymous_client):
        body = b"Not a JSON string at all"
        headers = {"X-Hub-Signature-256": _sign(body)}
        response = anonymous_client.post("/webhooks/whatsapp", content=body, headers=headers)
        assert response.status_code == 400
        assert "malformed json" in response.text.lower()

    def test_json_list_rejected(self, anonymous_client):
        body = json.dumps([1, 2, 3]).encode("utf-8")
        headers = {"X-Hub-Signature-256": _sign(body)}
        response = anonymous_client.post("/webhooks/whatsapp", content=body, headers=headers)
        assert response.status_code == 400
        assert "expected json object" in response.text.lower()

    def test_non_business_account_object_ignored_safely(self, anonymous_client):
        body = json.dumps({"object": "user", "entry": []}).encode("utf-8")
        headers = {"X-Hub-Signature-256": _sign(body)}
        response = anonymous_client.post("/webhooks/whatsapp", content=body, headers=headers)
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"

    def test_empty_entry_list_processed_safely(self, anonymous_client):
        body = json.dumps({"object": "whatsapp_business_account", "entry": []}).encode("utf-8")
        headers = {"X-Hub-Signature-256": _sign(body)}
        response = anonymous_client.post("/webhooks/whatsapp", content=body, headers=headers)
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "processed": 0, "duplicates": 0}


# ===========================================================================
# 5. Inbound Messages Processing & Deduplication Tests
# ===========================================================================

class TestInboundMessageProcessing:
    @staticmethod
    def _make_message_payload(
        phone_number_id: str,
        message_id: str,
        sender_phone: str = "919999999999",
        text: str = "Hello test",
        timestamp: int = 1730000000,
    ) -> bytes:
        return json.dumps({
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "1234567890",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "15551845888",
                                    "phone_number_id": phone_number_id,
                                },
                                "contacts": [
                                    {
                                        "profile": {"name": "Test User"},
                                        "wa_id": sender_phone,
                                    }
                                ],
                                "messages": [
                                    {
                                        "from": sender_phone,
                                        "id": message_id,
                                        "timestamp": str(timestamp),
                                        "type": "text",
                                        "text": {"body": text},
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }).encode("utf-8")

    def test_inbound_message_recorded_idempotently(self, anonymous_client, db_session):
        payload = self._make_message_payload("1405385199326466", "wamid.INBOUND_001")
        headers = {"X-Hub-Signature-256": _sign(payload)}

        # 1. First delivery
        res1 = anonymous_client.post("/webhooks/whatsapp", content=payload, headers=headers)
        assert res1.status_code == 200
        assert res1.json() == {"status": "ok", "processed": 1, "duplicates": 0}

        event = db_session.scalar(
            select(WhatsAppWebhookEvent).where(
                WhatsAppWebhookEvent.event_id == "wamid.INBOUND_001"
            )
        )
        assert event is not None
        assert event.phone_number_id == "1405385199326466"
        assert event.event_type == "message"
        assert event.status_value == ""
        assert event.message_type == "text"
        assert event.processed_status == "processed"
        assert event.tenant_id is None  # Must never associate tenant from untrusted sender
        assert event.payload_timestamp == datetime.fromtimestamp(1730000000, tz=timezone.utc)

        # 2. Duplicate retry delivery
        res2 = anonymous_client.post("/webhooks/whatsapp", content=payload, headers=headers)
        assert res2.status_code == 200
        assert res2.json() == {"status": "ok", "processed": 0, "duplicates": 1}

        # Verify only 1 record exists
        count = len(
            list(
                db_session.scalars(
                    select(WhatsAppWebhookEvent).where(
                        WhatsAppWebhookEvent.event_id == "wamid.INBOUND_001"
                    )
                )
            )
        )
        assert count == 1


# ===========================================================================
# 6. Delivery Statuses Processing & Deduplication Tests
# ===========================================================================

class TestDeliveryStatusProcessing:
    @staticmethod
    def _make_status_payload(
        phone_number_id: str,
        message_id: str,
        status_value: str,
        recipient_phone: str = "919999999999",
        timestamp: int = 1730000001,
        error_code: int | None = None,
    ) -> bytes:
        status_obj: dict = {
            "id": message_id,
            "status": status_value,
            "timestamp": str(timestamp),
            "recipient_id": recipient_phone,
        }
        if error_code is not None:
            status_obj["errors"] = [{"code": error_code, "title": "Provider error"}]

        return json.dumps({
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "1234567890",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "15551845888",
                                    "phone_number_id": phone_number_id,
                                },
                                "statuses": [status_obj],
                            },
                        }
                    ],
                }
            ],
        }).encode("utf-8")

    def test_status_lifecycle_and_deduplication(self, anonymous_client, db_session):
        msg_id = "wamid.OUTBOUND_100"
        phone_id = "1405385199326466"

        # 1. 'sent' status
        p_sent = self._make_status_payload(phone_id, msg_id, "sent")
        res_sent = anonymous_client.post(
            "/webhooks/whatsapp", content=p_sent, headers={"X-Hub-Signature-256": _sign(p_sent)}
        )
        assert res_sent.status_code == 200
        assert res_sent.json() == {"status": "ok", "processed": 1, "duplicates": 0}

        # 2. 'delivered' status
        p_delivered = self._make_status_payload(phone_id, msg_id, "delivered")
        res_del = anonymous_client.post(
            "/webhooks/whatsapp", content=p_delivered, headers={"X-Hub-Signature-256": _sign(p_delivered)}
        )
        assert res_del.status_code == 200
        assert res_del.json() == {"status": "ok", "processed": 1, "duplicates": 0}

        # 3. Duplicate 'delivered' status retry
        res_del_dup = anonymous_client.post(
            "/webhooks/whatsapp", content=p_delivered, headers={"X-Hub-Signature-256": _sign(p_delivered)}
        )
        assert res_del_dup.status_code == 200
        assert res_del_dup.json() == {"status": "ok", "processed": 0, "duplicates": 1}

        # 4. 'read' status
        p_read = self._make_status_payload(phone_id, msg_id, "read")
        res_read = anonymous_client.post(
            "/webhooks/whatsapp", content=p_read, headers={"X-Hub-Signature-256": _sign(p_read)}
        )
        assert res_read.status_code == 200
        assert res_read.json() == {"status": "ok", "processed": 1, "duplicates": 0}

        # Verify 3 distinct status records exist in DB
        statuses = list(
            db_session.scalars(
                select(WhatsAppWebhookEvent).where(
                    WhatsAppWebhookEvent.event_id == msg_id,
                    WhatsAppWebhookEvent.event_type == "status",
                ).order_by(WhatsAppWebhookEvent.id)
            )
        )
        assert len(statuses) == 3
        assert [s.status_value for s in statuses] == ["sent", "delivered", "read"]

    def test_failed_status_with_error_code(self, anonymous_client, db_session):
        msg_id = "wamid.OUTBOUND_FAILED_200"
        phone_id = "1405385199326466"
        p_failed = self._make_status_payload(phone_id, msg_id, "failed", error_code=131047)
        res = anonymous_client.post(
            "/webhooks/whatsapp", content=p_failed, headers={"X-Hub-Signature-256": _sign(p_failed)}
        )
        assert res.status_code == 200
        assert res.json() == {"status": "ok", "processed": 1, "duplicates": 0}

        event = db_session.scalar(
            select(WhatsAppWebhookEvent).where(
                WhatsAppWebhookEvent.event_id == msg_id,
                WhatsAppWebhookEvent.status_value == "failed",
            )
        )
        assert event is not None
        assert event.error_code == 131047


# ===========================================================================
# 7. Safety, Tenant Isolation & Side-Effect Free Guarantees Tests
# ===========================================================================

class TestSafetyAndPrivacyGuarantees:
    def test_no_outbound_messages_or_agent_runs_created(self, anonymous_client, db_session):
        initial_runs = len(list(db_session.scalars(select(AgentRun))))
        initial_executions = len(list(db_session.scalars(select(AgentExecution))))

        payload = TestInboundMessageProcessing._make_message_payload(
            "1405385199326466", "wamid.INBOUND_SAFETY_01", text="Can I get pricing?"
        )
        response = anonymous_client.post(
            "/webhooks/whatsapp",
            content=payload,
            headers={"X-Hub-Signature-256": _sign(payload)},
        )
        assert response.status_code == 200

        # Confirm strictly 0 runs or executions created
        after_runs = len(list(db_session.scalars(select(AgentRun))))
        after_executions = len(list(db_session.scalars(select(AgentExecution))))
        assert after_runs == initial_runs
        assert after_executions == initial_executions

    def test_tenant_isolation_preserved_untrusted_sender_never_maps_to_tenant(
        self, anonymous_client, db_session
    ):
        # Create a tenant and a contact with phone "+919876543210"
        tenant = Tenant(name="Test Tenant Alpha")
        db_session.add(tenant)
        db_session.commit()
        db_session.refresh(tenant)

        contact = Contact(
            tenant_id=tenant.id,
            name="Alpha Contact",
            phone_number="+919876543210",
        )
        db_session.add(contact)
        db_session.commit()

        # Inbound message from the exact same phone number
        payload = TestInboundMessageProcessing._make_message_payload(
            "1405385199326466",
            "wamid.INBOUND_TENANT_ISO_01",
            sender_phone="919876543210",
        )
        res = anonymous_client.post(
            "/webhooks/whatsapp",
            content=payload,
            headers={"X-Hub-Signature-256": _sign(payload)},
        )
        assert res.status_code == 200

        event = db_session.scalar(
            select(WhatsAppWebhookEvent).where(
                WhatsAppWebhookEvent.event_id == "wamid.INBOUND_TENANT_ISO_01"
            )
        )
        assert event is not None
        # MUST BE NONE: untrusted sender phone must never associate with tenant
        assert event.tenant_id is None
        assert event.tenant_id != tenant.id

    def test_zero_logging_of_sensitive_data(self, anonymous_client, caplog):
        customer_secret_text = "MySecretPassport12345"
        sender_phone = "919876543210"
        payload = TestInboundMessageProcessing._make_message_payload(
            "1405385199326466",
            "wamid.INBOUND_LOG_CHECK",
            sender_phone=sender_phone,
            text=customer_secret_text,
        )

        with caplog.at_level(logging.DEBUG):
            res = anonymous_client.post(
                "/webhooks/whatsapp",
                content=payload,
                headers={"X-Hub-Signature-256": _sign(payload)},
            )
            assert res.status_code == 200

        full_logs = "\n".join(record.message for record in caplog.records)
        assert customer_secret_text not in full_logs
        assert sender_phone not in full_logs
        assert TEST_APP_SECRET not in full_logs
        assert TEST_VERIFY_TOKEN not in full_logs
        assert "MySecretPassport" not in full_logs
