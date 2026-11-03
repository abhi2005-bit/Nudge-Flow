"""add_whatsapp_webhook_events

Revision ID: 834c9b14cbc9
Revises: f6b7d3e2a910
Create Date: 2026-10-28 05:32:06.227597

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '834c9b14cbc9'
down_revision: Union[str, Sequence[str], None] = 'f6b7d3e2a910'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "whatsapp_webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("phone_number_id", sa.String(length=64), server_default="", nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("status_value", sa.String(length=32), server_default="", nullable=False),
        sa.Column("message_type", sa.String(length=32), nullable=True),
        sa.Column("error_code", sa.Integer(), nullable=True),
        sa.Column("payload_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "processed_status",
            sa.String(length=32),
            server_default="processed",
            nullable=False,
        ),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "phone_number_id",
            "event_id",
            "event_type",
            "status_value",
            name="uq_whatsapp_webhook_events_dedup",
        ),
        sa.CheckConstraint(
            "event_type IN ('message', 'status')",
            name="ck_whatsapp_webhook_events_event_type",
        ),
        sa.CheckConstraint(
            "processed_status IN ('processed', 'duplicate', 'unmatched', 'ignored')",
            name="ck_whatsapp_webhook_events_processed_status",
        ),
    )
    op.create_index(
        "ix_whatsapp_webhook_events_event_id",
        "whatsapp_webhook_events",
        ["event_id"],
    )
    op.create_index(
        "ix_whatsapp_webhook_events_phone_event",
        "whatsapp_webhook_events",
        ["phone_number_id", "event_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_whatsapp_webhook_events_phone_event",
        table_name="whatsapp_webhook_events",
    )
    op.drop_index(
        "ix_whatsapp_webhook_events_event_id",
        table_name="whatsapp_webhook_events",
    )
    op.drop_table("whatsapp_webhook_events")
