"""Opt-in PostgreSQL integration tests for persisted agent classification fields."""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from nudgeflow.models.agent import AgentRun
from nudgeflow.models.contact import Contact
from nudgeflow.models.follow_up import FollowUp
from nudgeflow.models.tenant import Tenant
from nudgeflow.models.user import User
from nudgeflow.services.agent import workflow


AGENT_TEST_URL = os.environ.get("NUDGEFLOW_AGENT_TEST_URL")


@pytest.mark.skipif(
    not AGENT_TEST_URL,
    reason="set NUDGEFLOW_AGENT_TEST_URL to a disposable loopback PostgreSQL database",
)
def test_classification_persistence_missing_input_unavailable_and_tenant_isolation(
    monkeypatch,
):
    url = make_url(AGENT_TEST_URL)
    if not url.drivername.startswith("postgresql"):
        pytest.fail("agent test URL must use PostgreSQL")
    if url.host not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("agent test URL must target a loopback host")
    if not (url.database or "").startswith("nudgeflow_test_"):
        pytest.fail("database name must start with nudgeflow_test_")

    engine = create_engine(url)
    connection = engine.connect()
    outer_transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        tenant = Tenant(name=f"classification-{uuid.uuid4().hex}")
        db.add(tenant)
        db.flush()
        user = User(
            email=f"classification-{uuid.uuid4().hex}@example.test",
            hashed_password="test-only-hash",
            tenant_id=tenant.id,
            tenant_role="owner",
        )
        db.add(user)
        db.flush()
        contact = Contact(
            name="Classification test",
            phone_number=f"+1555{uuid.uuid4().int % 10**7:07d}",
            tenant_id=tenant.id,
            owner_id=user.id,
        )
        db.add(contact)
        db.flush()
        follow_up = FollowUp(
            contact_id=contact.id,
            tenant_id=tenant.id,
            title="Classification test follow-up",
            due_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db.add(follow_up)

        other_tenant = Tenant(name=f"classification-other-{uuid.uuid4().hex}")
        db.add(other_tenant)
        db.flush()
        other_user = User(
            email=f"classification-other-{uuid.uuid4().hex}@example.test",
            hashed_password="test-only-hash",
            tenant_id=other_tenant.id,
            tenant_role="owner",
        )
        db.add(other_user)
        db.commit()
        follow_up_id = follow_up.id

        seen_messages = []

        def classified(message):
            seen_messages.append(message)
            return {
                "status": "classified",
                "reason": None,
                "intent": "service_enquiry",
                "confidence": 0.91,
                "error_code": None,
            }

        monkeypatch.setattr(workflow, "classify_customer_message", classified)
        classified_run = workflow.start_run(
            db,
            user=user,
            follow_up_id=follow_up_id,
            customer_message="Can you service my unit?",
        )
        assert seen_messages == ["Can you service my unit?"]
        persisted = db.get(AgentRun, classified_run["id"])
        assert persisted is not None
        assert persisted.intent_classification_status == "classified"
        assert persisted.predicted_intent == "service_enquiry"
        assert persisted.intent_confidence == pytest.approx(0.91)

        monkeypatch.setattr(
            workflow,
            "classify_customer_message",
            lambda _message: pytest.fail("missing input must not invoke classification"),
        )
        missing_run = workflow.start_run(db, user=user, follow_up_id=follow_up_id)
        missing = db.get(AgentRun, missing_run["id"])
        assert missing is not None
        assert missing.intent_classification_status == "not_performed"
        assert missing.intent_classification_reason == "missing_input"
        assert missing.predicted_intent is None
        assert missing.intent_confidence is None

        monkeypatch.setattr(
            workflow,
            "classify_customer_message",
            lambda _message: {
                "status": "unavailable",
                "reason": None,
                "intent": None,
                "confidence": None,
                "error_code": "model_artifact_missing",
            },
        )
        unavailable_run = workflow.start_run(
            db,
            user=user,
            follow_up_id=follow_up_id,
            customer_message="Please help",
        )
        unavailable = db.get(AgentRun, unavailable_run["id"])
        assert unavailable is not None
        assert unavailable.intent_classification_status == "unavailable"
        assert unavailable.intent_classification_error_code == "model_artifact_missing"
        assert unavailable.predicted_intent is None
        assert unavailable.intent_confidence is None

        monkeypatch.setattr(
            workflow,
            "classify_customer_message",
            lambda _message: pytest.fail("another tenant must not reach classification"),
        )
        with pytest.raises(HTTPException) as not_found:
            workflow.start_run(
                db,
                user=other_user,
                follow_up_id=follow_up_id,
                customer_message="Private message",
            )
        assert not_found.value.status_code == 404
    finally:
        db.close()
        outer_transaction.rollback()
        connection.close()
        engine.dispose()
