
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from nudgeflow.database import Base
from nudgeflow.models.types import UTCDateTime


class Contact(Base):
    """A person or business communicating with NudgeFlow."""

    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "phone_number",
            name="uq_contacts_tenant_phone",
        ),
        # Required as the referenced key for FollowUp's tenant/contact FK.
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_contacts_tenant_id_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone_number: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        server_default=func.now(),
        nullable=False,
    )
