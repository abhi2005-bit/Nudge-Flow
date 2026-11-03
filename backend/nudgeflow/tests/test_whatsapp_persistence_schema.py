import pytest
from sqlalchemy.exc import IntegrityError

from nudgeflow.database import Base
from nudgeflow.models import (
    Contact,
    Tenant,
    WhatsAppBusinessChannel,
    WhatsAppConversation,
    WhatsAppInboundMessage,
    WhatsAppWebhookEvent,
)


def _foreign_key(table, name: str):
    return next(
        constraint
        for constraint in table.foreign_key_constraints
        if constraint.name == name
    )


def test_whatsapp_persistence_models_are_registered():
    assert {
        "whatsapp_business_channels",
        "whatsapp_conversations",
        "whatsapp_inbound_messages",
    }.issubset(Base.metadata.tables)


def test_whatsapp_contact_references_are_tenant_scoped_and_nullable():
    for model, constraint_name in (
        (WhatsAppConversation, "fk_whatsapp_conversations_tenant_contact"),
        (WhatsAppInboundMessage, "fk_whatsapp_inbound_messages_tenant_contact"),
    ):
        constraint = _foreign_key(model.__table__, constraint_name)
        assert constraint.column_keys == ["tenant_id", "contact_id"]
        assert [element.target_fullname for element in constraint.elements] == [
            "contacts.tenant_id",
            "contacts.id",
        ]
        assert constraint.ondelete == "RESTRICT"
        assert model.__table__.columns["contact_id"].nullable is True


def test_inbound_message_channel_matches_its_tenant_conversation():
    constraint = _foreign_key(
        WhatsAppInboundMessage.__table__,
        "fk_whatsapp_inbound_messages_tenant_channel_conversation",
    )
    assert constraint.column_keys == ["tenant_id", "channel_id", "conversation_id"]
    assert [element.target_fullname for element in constraint.elements] == [
        "whatsapp_conversations.tenant_id",
        "whatsapp_conversations.channel_id",
        "whatsapp_conversations.id",
    ]


def test_database_rejects_cross_tenant_contact_and_channel_references(db_session):
    tenant_one = Tenant(name="Tenant one")
    tenant_two = Tenant(name="Tenant two")
    db_session.add_all([tenant_one, tenant_two])
    db_session.flush()

    channel_one = WhatsAppBusinessChannel(
        tenant_id=tenant_one.id,
        phone_number_id="phone-one",
    )
    channel_two = WhatsAppBusinessChannel(
        tenant_id=tenant_two.id,
        phone_number_id="phone-two",
    )
    contact_two = Contact(
        tenant_id=tenant_two.id,
        name="Other tenant",
        phone_number="+15550000002",
    )
    db_session.add_all([channel_one, channel_two, contact_two])
    db_session.flush()

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(
                WhatsAppConversation(
                    tenant_id=tenant_one.id,
                    channel_id=channel_one.id,
                    contact_id=contact_two.id,
                    sender_phone_number="+15550000003",
                )
            )
            db_session.flush()

    conversation = WhatsAppConversation(
        tenant_id=tenant_one.id,
        channel_id=channel_one.id,
        contact_id=None,
        sender_phone_number="+15550000004",
    )
    event = WhatsAppWebhookEvent(
        phone_number_id="phone-one",
        event_id="message-one",
        event_type="message",
        status_value="",
    )
    db_session.add_all([conversation, event])
    db_session.flush()

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(
                WhatsAppInboundMessage(
                    webhook_event_id=event.id,
                    tenant_id=tenant_one.id,
                    channel_id=channel_two.id,
                    conversation_id=conversation.id,
                    contact_id=None,
                    meta_message_id="meta-message-one",
                    sender_phone_number="+15550000004",
                    message_type="text",
                    text_body="hello",
                    processing_status="persisted",
                )
            )
            db_session.flush()
