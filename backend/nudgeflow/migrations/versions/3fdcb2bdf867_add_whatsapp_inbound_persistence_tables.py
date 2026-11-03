"""add WhatsApp inbound persistence tables

Revision ID: 3fdcb2bdf867
Revises: 834c9b14cbc9
Create Date: 2026-11-03 04:34:07.988076

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3fdcb2bdf867"
down_revision: Union[str, Sequence[str], None] = "834c9b14cbc9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "whatsapp_business_channels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("phone_number_id", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "phone_number_id",
            name="uq_whatsapp_business_channels_phone_number_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_whatsapp_business_channels_tenant_id_id",
        ),
    )
    op.create_index(
        op.f("ix_whatsapp_business_channels_tenant_id"),
        "whatsapp_business_channels",
        ["tenant_id"],
        unique=False,
    )
    op.create_table(
        "whatsapp_conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=True),
        sa.Column("sender_phone_number", sa.String(length=16), nullable=False),
        sa.Column(
            "latest_message_timestamp",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "channel_id"],
            ["whatsapp_business_channels.tenant_id", "whatsapp_business_channels.id"],
            name="fk_whatsapp_conversations_tenant_channel",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "contact_id"],
            ["contacts.tenant_id", "contacts.id"],
            name="fk_whatsapp_conversations_tenant_contact",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "channel_id",
            "id",
            name="uq_whatsapp_conversations_tenant_channel_id_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "channel_id",
            "sender_phone_number",
            name="uq_whatsapp_conversations_tenant_channel_sender",
        ),
    )
    op.create_index(
        op.f("ix_whatsapp_conversations_channel_id"),
        "whatsapp_conversations",
        ["channel_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_whatsapp_conversations_contact_id"),
        "whatsapp_conversations",
        ["contact_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_whatsapp_conversations_tenant_id"),
        "whatsapp_conversations",
        ["tenant_id"],
        unique=False,
    )
    op.create_table(
        "whatsapp_inbound_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("webhook_event_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=True),
        sa.Column("meta_message_id", sa.String(length=128), nullable=False),
        sa.Column("sender_phone_number", sa.String(length=16), nullable=False),
        sa.Column("message_type", sa.String(length=32), nullable=False),
        sa.Column("text_body", sa.Text(), nullable=True),
        sa.Column(
            "message_timestamp",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processing_status", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            "processing_status IN ('persisted', 'unsupported')",
            name="ck_whatsapp_inbound_messages_processing_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "channel_id", "conversation_id"],
            [
                "whatsapp_conversations.tenant_id",
                "whatsapp_conversations.channel_id",
                "whatsapp_conversations.id",
            ],
            name="fk_whatsapp_inbound_messages_tenant_channel_conversation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "contact_id"],
            ["contacts.tenant_id", "contacts.id"],
            name="fk_whatsapp_inbound_messages_tenant_contact",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["webhook_event_id"],
            ["whatsapp_webhook_events.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "channel_id",
            "meta_message_id",
            name="uq_whatsapp_inbound_messages_channel_meta_id",
        ),
        sa.UniqueConstraint(
            "webhook_event_id",
            name="uq_whatsapp_inbound_messages_webhook_event",
        ),
    )
    op.create_index(
        op.f("ix_whatsapp_inbound_messages_channel_id"),
        "whatsapp_inbound_messages",
        ["channel_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_whatsapp_inbound_messages_contact_id"),
        "whatsapp_inbound_messages",
        ["contact_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_whatsapp_inbound_messages_conversation_id"),
        "whatsapp_inbound_messages",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_whatsapp_inbound_messages_tenant_id"),
        "whatsapp_inbound_messages",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_whatsapp_inbound_messages_tenant_id"),
        table_name="whatsapp_inbound_messages",
    )
    op.drop_index(
        op.f("ix_whatsapp_inbound_messages_conversation_id"),
        table_name="whatsapp_inbound_messages",
    )
    op.drop_index(
        op.f("ix_whatsapp_inbound_messages_contact_id"),
        table_name="whatsapp_inbound_messages",
    )
    op.drop_index(
        op.f("ix_whatsapp_inbound_messages_channel_id"),
        table_name="whatsapp_inbound_messages",
    )
    op.drop_table("whatsapp_inbound_messages")
    op.drop_index(
        op.f("ix_whatsapp_conversations_tenant_id"),
        table_name="whatsapp_conversations",
    )
    op.drop_index(
        op.f("ix_whatsapp_conversations_contact_id"),
        table_name="whatsapp_conversations",
    )
    op.drop_index(
        op.f("ix_whatsapp_conversations_channel_id"),
        table_name="whatsapp_conversations",
    )
    op.drop_table("whatsapp_conversations")
    op.drop_index(
        op.f("ix_whatsapp_business_channels_tenant_id"),
        table_name="whatsapp_business_channels",
    )
    op.drop_table("whatsapp_business_channels")
