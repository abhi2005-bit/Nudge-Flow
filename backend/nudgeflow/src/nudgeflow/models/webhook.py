"""Persisted WhatsApp webhook event records for idempotency and audit."""

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from nudgeflow.database import Base
from nudgeflow.models.types import UTCDateTime


class WhatsAppWebhookEvent(Base):
    """A WhatsApp webhook event record ensuring deduplication and audit trail."""

    __tablename__ = "whatsapp_webhook_events"
    __table_args__ = (
        UniqueConstraint(
            "phone_number_id",
            "event_id",
            "event_type",
            "status_value",
            name="uq_whatsapp_webhook_events_dedup",
        ),
        CheckConstraint(
            "event_type IN ('message', 'status')",
            name="ck_whatsapp_webhook_events_event_type",
        ),
        CheckConstraint(
            "processed_status IN ('processed', 'duplicate', 'unmatched', 'ignored')",
            name="ck_whatsapp_webhook_events_processed_status",
        ),
        Index(
            "ix_whatsapp_webhook_events_phone_event",
            "phone_number_id",
            "event_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    phone_number_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    event_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status_value: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    message_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload_timestamp: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
    processed_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="processed"
    )
    tenant_id: Mapped[int | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, default=None
    )
