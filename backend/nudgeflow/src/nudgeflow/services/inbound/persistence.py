"""Durable, tenant-safe inbound message persistence without AI side effects."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from nudgeflow.models.conversation import WhatsAppConversation
from nudgeflow.models.inbound_message import WhatsAppInboundMessage
from nudgeflow.models.webhook import WhatsAppWebhookEvent
from nudgeflow.models.whatsapp_channel import WhatsAppBusinessChannel
from nudgeflow.services.inbound.identity import (
    normalize_whatsapp_phone_number,
    resolve_tenant_contact,
)


def persist_inbound_message(
    db: Session,
    *,
    event: WhatsAppWebhookEvent,
    sender_phone: object,
    message_type: str | None,
    text_body: object,
    message_timestamp: datetime | None,
) -> str:
    """Persist one inbound message after resolving a trusted receiving channel.

    Returns ``persisted``, ``unsupported``, or ``unmatched``. This function does
    not invoke any model, create agent runs, or trigger external side effects.
    """
    channel = db.scalar(
        select(WhatsAppBusinessChannel).where(
            WhatsAppBusinessChannel.phone_number_id == event.phone_number_id,
            WhatsAppBusinessChannel.is_active.is_(True),
        )
    )
    sender = normalize_whatsapp_phone_number(sender_phone)
    if channel is None or sender is None:
        event.processed_status = "unmatched"
        return "unmatched"

    contact = resolve_tenant_contact(
        db, tenant_id=channel.tenant_id, sender_phone_number=sender
    )
    conversation = db.scalar(
        select(WhatsAppConversation).where(
            WhatsAppConversation.tenant_id == channel.tenant_id,
            WhatsAppConversation.channel_id == channel.id,
            WhatsAppConversation.sender_phone_number == sender,
        )
    )
    if conversation is None:
        conversation = WhatsAppConversation(
            tenant_id=channel.tenant_id,
            channel_id=channel.id,
            contact_id=contact.id if contact is not None else None,
            sender_phone_number=sender,
            latest_message_timestamp=message_timestamp,
        )
        db.add(conversation)
        db.flush()
    elif conversation.contact_id is None and contact is not None:
        # A previously unknown identity can be linked only to an existing
        # tenant-scoped contact; untrusted profile data never creates contacts.
        conversation.contact_id = contact.id

    if (
        message_timestamp is not None
        and (
            conversation.latest_message_timestamp is None
            or message_timestamp > conversation.latest_message_timestamp
        )
    ):
        conversation.latest_message_timestamp = message_timestamp

    clean_type = message_type.strip() if isinstance(message_type, str) else "unknown"
    is_text = clean_type == "text" and isinstance(text_body, str) and bool(text_body.strip())
    inbound = WhatsAppInboundMessage(
        webhook_event_id=event.id,
        tenant_id=channel.tenant_id,
        channel_id=channel.id,
        conversation_id=conversation.id,
        contact_id=contact.id if contact is not None else None,
        meta_message_id=event.event_id,
        sender_phone_number=sender,
        message_type=clean_type or "unknown",
        text_body=text_body.strip() if is_text else None,
        message_timestamp=message_timestamp,
        processing_status="persisted" if is_text else "unsupported",
    )
    db.add(inbound)
    try:
        db.flush()
    except IntegrityError:
        # The event uniqueness constraint normally catches retries before this
        # point. This protects the separate message identity invariant too.
        raise
    event.tenant_id = channel.tenant_id
    event.processed_status = "processed"
    return inbound.processing_status
