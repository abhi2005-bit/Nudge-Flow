"""Normalized inbound WhatsApp messages; deliberately separate from AI analysis."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from nudgeflow.database import Base
from nudgeflow.models.types import UTCDateTime


class WhatsAppInboundMessage(Base):
    """One Meta inbound message persisted exactly once after trusted channel resolution."""

    __tablename__ = "whatsapp_inbound_messages"
    __table_args__ = (
        UniqueConstraint(
            "webhook_event_id",
            name="uq_whatsapp_inbound_messages_webhook_event",
        ),
        UniqueConstraint(
            "channel_id",
            "meta_message_id",
            name="uq_whatsapp_inbound_messages_channel_meta_id",
        ),
        CheckConstraint(
            "processing_status IN ('persisted', 'unsupported')",
            name="ck_whatsapp_inbound_messages_processing_status",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "channel_id", "conversation_id"],
            [
                "whatsapp_conversations.tenant_id",
                "whatsapp_conversations.channel_id",
                "whatsapp_conversations.id",
            ],
            name="fk_whatsapp_inbound_messages_tenant_channel_conversation",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "contact_id"],
            ["contacts.tenant_id", "contacts.id"],
            name="fk_whatsapp_inbound_messages_tenant_contact",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    webhook_event_id: Mapped[int] = mapped_column(
        ForeignKey("whatsapp_webhook_events.id", ondelete="RESTRICT"), nullable=False
    )
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    channel_id: Mapped[int] = mapped_column(nullable=False, index=True)
    conversation_id: Mapped[int] = mapped_column(nullable=False, index=True)
    contact_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    meta_message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sender_phone_number: Mapped[str] = mapped_column(String(16), nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), nullable=False)
    text_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_timestamp: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    received_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
    processing_status: Mapped[str] = mapped_column(String(20), nullable=False)
