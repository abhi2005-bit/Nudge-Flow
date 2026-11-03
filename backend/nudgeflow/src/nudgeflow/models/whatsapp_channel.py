"""Trusted tenant-owned WhatsApp Business channel mappings."""

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from nudgeflow.database import Base
from nudgeflow.models.types import UTCDateTime


class WhatsAppBusinessChannel(Base):
    """Maps one Meta business phone-number ID to exactly one tenant."""

    __tablename__ = "whatsapp_business_channels"
    __table_args__ = (
        UniqueConstraint("phone_number_id", name="uq_whatsapp_business_channels_phone_number_id"),
        UniqueConstraint("tenant_id", "id", name="uq_whatsapp_business_channels_tenant_id_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    phone_number_id: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=func.now(), nullable=False
    )
