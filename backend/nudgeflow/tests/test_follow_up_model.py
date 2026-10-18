from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from nudgeflow.models.contact import Contact
from nudgeflow.models.follow_up import FollowUp


def test_follow_up_has_contact_foreign_key_and_cascade():
    foreign_key = next(iter(FollowUp.__table__.c.contact_id.foreign_keys))
    assert foreign_key.target_fullname == "contacts.id"
    assert foreign_key.ondelete == "CASCADE"


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
        contact = Contact(name="Status Test", phone_number="+15550000001")
        session.add(contact)
        session.flush()
        session.add(
            FollowUp(
                contact_id=contact.id,
                title="Call",
                due_at=datetime.now(timezone.utc),
                status="cancelled",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
