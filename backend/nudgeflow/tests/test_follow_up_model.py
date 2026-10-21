from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from nudgeflow.models.contact import Contact
from nudgeflow.models.follow_up import FollowUp
from nudgeflow.models.tenant import Tenant


def test_follow_up_has_contact_foreign_key_and_cascade():
    foreign_key = next(iter(FollowUp.__table__.c.contact_id.foreign_keys))
    assert foreign_key.target_fullname == "contacts.id"
    assert foreign_key.ondelete == "CASCADE"


def test_follow_up_database_constraint_requires_contact_in_same_tenant(test_engine):
    with Session(test_engine) as session:
        first_tenant = Tenant(name="First business")
        second_tenant = Tenant(name="Second business")
        session.add_all([first_tenant, second_tenant])
        session.flush()
        other_contact = Contact(
            tenant_id=second_tenant.id,
            name="Other tenant contact",
            phone_number="+15550000009",
        )
        session.add(other_contact)
        session.flush()

        session.add(
            FollowUp(
                tenant_id=first_tenant.id,
                contact_id=other_contact.id,
                title="Cross-tenant task",
                due_at=datetime.now(timezone.utc),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_follow_up_status_is_limited_in_database():
    constraint = next(
        constraint
        for constraint in FollowUp.__table__.constraints
        if constraint.name == "ck_follow_ups_status"
    )
    assert "pending" in str(constraint.sqltext)
    assert "completed" in str(constraint.sqltext)
    assert FollowUp.__table__.c.status.server_default.arg == "pending"


def test_database_rejects_invalid_follow_up_status(test_engine):
    with Session(test_engine) as session:
        tenant = Tenant(name="Status workspace")
        session.add(tenant)
        session.flush()
        contact = Contact(
            tenant_id=tenant.id,
            name="Status Test",
            phone_number="+15550000001",
        )
        session.add(contact)
        session.flush()
        session.add(
            FollowUp(
                tenant_id=tenant.id,
                contact_id=contact.id,
                title="Call",
                due_at=datetime.now(timezone.utc),
                status="cancelled",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
