from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from nudgeflow.config import settings
from nudgeflow.database import get_db
from nudgeflow.models.webhook import WhatsAppWebhookEvent
from nudgeflow.services.inbound.persistence import persist_inbound_message


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/webhooks",
    tags=["Webhooks"],
)


def _parse_timestamp(ts: object) -> datetime | None:
    """Safely parse Unix epoch timestamp into timezone-aware UTC datetime."""
    if ts is None:
        return None

    try:
        ts_float = float(ts)
        return datetime.fromtimestamp(ts_float, tz=timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def verify_webhook_signature(
    raw_body: bytes,
    signature_header: str | None,
) -> None:
    """Validate X-Hub-Signature-256 using HMAC-SHA256 against Meta App Secret.

    Raises HTTPException(403) on invalid or missing signature or unconfigured secret.
    """
    app_secret = settings.whatsapp_app_secret.get_secret_value().strip()

    if not app_secret:
        logger.warning("WhatsApp webhook rejected: App secret not configured.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="App secret not configured.",
        )

    if not signature_header or not signature_header.startswith("sha256="):
        logger.warning(
            "WhatsApp webhook rejected: Missing or invalid signature header."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing or invalid signature header.",
        )

    expected_sig = "sha256=" + hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not secrets.compare_digest(expected_sig, signature_header):
        logger.warning("WhatsApp webhook rejected: Signature mismatch.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook signature.",
        )


@router.get("/whatsapp", response_class=PlainTextResponse)
def verify_whatsapp_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(
        default=None,
        alias="hub.verify_token",
    ),
    hub_challenge: str | None = Query(
        default=None,
        alias="hub.challenge",
    ),
) -> PlainTextResponse:
    """Meta webhook verification endpoint.

    Validates hub.mode == 'subscribe' and hub.verify_token matches
    the configured token. Returns hub.challenge as plain text on success.
    """
    expected_token = (
        settings.whatsapp_webhook_verify_token.get_secret_value().strip()
    )

    if not expected_token:
        logger.warning(
            "WhatsApp webhook verification failed: Verify token not configured."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Webhook verify token not configured.",
        )

    if hub_mode != "subscribe" or not hub_verify_token:
        logger.warning(
            "WhatsApp webhook verification failed: Invalid mode or missing token."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verification failed: mode must be 'subscribe' with verify token.",
        )

    if not secrets.compare_digest(hub_verify_token, expected_token):
        logger.warning("WhatsApp webhook verification failed: Token mismatch.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verification token mismatch.",
        )

    if hub_challenge is None:
        logger.warning("WhatsApp webhook verification failed: Missing challenge.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing hub.challenge query parameter.",
        )

    logger.info("WhatsApp webhook verified successfully.")

    return PlainTextResponse(
        content=hub_challenge,
        status_code=status.HTTP_200_OK,
    )


@router.post("/whatsapp")
async def receive_whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Receive and safely process WhatsApp webhook events from Meta.

    Validates HMAC-SHA256 signature, deduplicates message/status events,
    and records them idempotently.

    Never creates agent runs or sends automatic replies.
    """

   
    # 1. Read and authenticate the raw request body
   

    raw_body = await request.body()
    sig_header = request.headers.get("x-hub-signature-256")

    verify_webhook_signature(raw_body, sig_header)

   
    # 2. Parse the JSON payload
   

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("WhatsApp webhook rejected: Malformed JSON payload.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed JSON payload.",
        )

    if not isinstance(payload, dict):
        logger.warning("WhatsApp webhook rejected: Payload is not a JSON object.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload structure: expected JSON object.",
        )

   
    # 3. Ignore unrelated webhook objects
   

    if payload.get("object") != "whatsapp_business_account":
        logger.info("WhatsApp webhook acknowledged non-business object.")
        return {"status": "ignored"}

    entries = payload.get("entry")

    if not isinstance(entries, list):
        return {
            "status": "ok",
            "processed": 0,
            "duplicates": 0,
        }

    processed_count = 0
    duplicates_count = 0

   
    # 4. Process webhook entries and changes
   

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        changes = entry.get("changes")

        if not isinstance(changes, list):
            continue

        for change in changes:
            if not isinstance(change, dict):
                continue

            if change.get("field") != "messages":
                continue

            value = change.get("value")

            if not isinstance(value, dict):
                continue

         
            # 5. Extract the trusted receiving channel ID
         

            metadata = value.get("metadata")
            phone_number_id = None

            if isinstance(metadata, dict):
                raw_phone_number_id = metadata.get("phone_number_id")

                if isinstance(raw_phone_number_id, str):
                    phone_number_id = raw_phone_number_id.strip()

            # Without a receiving channel ID, we cannot safely
            # associate this event with a registered business.
            if not phone_number_id:
                continue

           
            # 6. PROCESS INBOUND CUSTOMER MESSAGES
           

            messages = value.get("messages")

            if isinstance(messages, list):
                for msg in messages:
                    if not isinstance(msg, dict):
                        continue

                    # Extract message fields.
                    msg_id = msg.get("id")
                    msg_type = msg.get("type")
                    sender_phone = msg.get("from")

                    text_data = msg.get("text")

                    text_body = (
                        text_data.get("body")
                        if isinstance(text_data, dict)
                        else None
                    )

                    # Message ID is required for deduplication.
                    if not isinstance(msg_id, str) or not msg_id.strip():
                        continue

                    msg_id = msg_id.strip()

                    msg_type = (
                        msg_type
                        if isinstance(msg_type, str)
                        else None
                    )

                    ts = _parse_timestamp(msg.get("timestamp"))

                 
                    # 6A. Check whether this message was already received
                 

                    existing = db.scalar(
                        select(WhatsAppWebhookEvent.id).where(
                            WhatsAppWebhookEvent.phone_number_id == phone_number_id,
                            WhatsAppWebhookEvent.event_id == msg_id,
                            WhatsAppWebhookEvent.event_type == "message",
                            WhatsAppWebhookEvent.status_value == "",
                        )
                    )

                    if existing is not None:
                        duplicates_count += 1
                        continue

                 
                    # 6B. Create the webhook event
                 

                    event_record = WhatsAppWebhookEvent(
                        phone_number_id=phone_number_id,
                        event_id=msg_id,
                        event_type="message",
                        status_value="",
                        message_type=msg_type,
                        payload_timestamp=ts,
                        processed_status="ignored",
                        tenant_id=None,
                    )

                    db.add(event_record)

                    try:
                        # Generate event_record.id without committing.
                        db.flush()

                     
                        # 6C. Persist the actual inbound message
                     

                        persist_inbound_message(
                            db,
                            event=event_record,
                            sender_phone=sender_phone,
                            message_type=msg_type,
                            text_body=text_body,
                            message_timestamp=ts,
                        )

                     
                        # 6D. Commit the complete transaction
                     

                        db.commit()
                        processed_count += 1

                    except IntegrityError:
                        db.rollback()

                        # A uniqueness violation may mean another
                        # request processed this event concurrently.
                        existing = db.scalar(
                            select(WhatsAppWebhookEvent.id).where(
                                WhatsAppWebhookEvent.phone_number_id == phone_number_id,
                                WhatsAppWebhookEvent.event_id == msg_id,
                                WhatsAppWebhookEvent.event_type == "message",
                                WhatsAppWebhookEvent.status_value == "",
                            )
                        )

                        if existing is not None:
                            duplicates_count += 1
                        else:
                            # Do not hide unrelated database errors.
                            raise

           
            # 7. PROCESS DELIVERY STATUS UPDATES
           

            statuses = value.get("statuses")

            if isinstance(statuses, list):
                for status_item in statuses:
                    if not isinstance(status_item, dict):
                        continue

                    status_id = status_item.get("id")

                    if not isinstance(status_id, str) or not status_id.strip():
                        continue

                    status_id = status_id.strip()

                    status_val = (
                        status_item.get("status")
                        if isinstance(status_item.get("status"), str)
                        else ""
                    ).strip()

                    ts = _parse_timestamp(status_item.get("timestamp"))

                    # Extract the first error code, if available.
                    error_code: int | None = None
                    errors = status_item.get("errors")

                    if (
                        isinstance(errors, list)
                        and errors
                        and isinstance(errors[0], dict)
                    ):
                        raw_code = errors[0].get("code")

                        if isinstance(raw_code, int):
                            error_code = raw_code

                 
                    # 7A. Check whether this status event already exists
                 

                    existing = db.scalar(
                        select(WhatsAppWebhookEvent.id).where(
                            WhatsAppWebhookEvent.phone_number_id == phone_number_id,
                            WhatsAppWebhookEvent.event_id == status_id,
                            WhatsAppWebhookEvent.event_type == "status",
                            WhatsAppWebhookEvent.status_value == status_val,
                        )
                    )

                    if existing is not None:
                        duplicates_count += 1
                        continue

                 
                    # 7B. Persist the delivery status event only
                 

                    event_record = WhatsAppWebhookEvent(
                        phone_number_id=phone_number_id,
                        event_id=status_id,
                        event_type="status",
                        status_value=status_val,
                        error_code=error_code,
                        payload_timestamp=ts,
                        processed_status="processed",
                        tenant_id=None,
                    )

                    db.add(event_record)

                    try:
                        db.commit()
                        processed_count += 1

                    except IntegrityError:
                        db.rollback()

                        # Confirm that the failure was actually a duplicate.
                        existing = db.scalar(
                            select(WhatsAppWebhookEvent.id).where(
                                WhatsAppWebhookEvent.phone_number_id == phone_number_id,
                                WhatsAppWebhookEvent.event_id == status_id,
                                WhatsAppWebhookEvent.event_type == "status",
                                WhatsAppWebhookEvent.status_value == status_val,
                            )
                        )

                        if existing is not None:
                            duplicates_count += 1
                        else:
                            raise

   
    # 8. Return the webhook acknowledgement
   

    logger.info(
        "WhatsApp webhook processed successfully: processed=%d, duplicates=%d",
        processed_count,
        duplicates_count,
    )

    return {
        "status": "ok",
        "processed": processed_count,
        "duplicates": duplicates_count,
    }
