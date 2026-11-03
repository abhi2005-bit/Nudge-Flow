"""Tenant-scoped customer conversations sourced from trusted WhatsApp channels."""

from datetime import datetime

from sqlalchemy import (
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from nudgeflow.database import Base
from nudgeflow.models.types import UTCDateTime


class WhatsAppConversation(Base):
    """A stable conversation key for one sender on one tenant channel."""

    __tablename__ = "whatsapp_conversations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "channel_id",
            "id",
            name="uq_whatsapp_conversations_tenant_channel_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "channel_id",
            "sender_phone_number",
            name="uq_whatsapp_conversations_tenant_channel_sender",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "channel_id"],
            ["whatsapp_business_channels.tenant_id", "whatsapp_business_channels.id"],
            name="fk_whatsapp_conversations_tenant_channel",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "contact_id"],
            ["contacts.tenant_id", "contacts.id"],
            name="fk_whatsapp_conversations_tenant_contact",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    channel_id: Mapped[int] = mapped_column(nullable=False, index=True)
    contact_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    sender_phone_number: Mapped[str] = mapped_column(String(16), nullable=False)
    latest_message_timestamp: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=func.now(), nullable=False
    )
