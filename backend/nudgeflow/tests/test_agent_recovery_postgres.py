from datetime import datetime, timedelta, timezone
import os
import secrets
import uuid

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from nudgeflow.models.agent import AgentRun
from nudgeflow.models.contact import Contact
from nudgeflow.models.follow_up import FollowUp
from nudgeflow.models.tenant import Tenant
from nudgeflow.models.user import User
from nudgeflow.services.agent.workflow import (
    EXECUTION_LEASE,
    _release_execution_lock,
    _try_execution_lock,
    recover_interrupted_run,
)

AGENT_TEST_URL = os.environ.get("NUDGEFLOW_AGENT_TEST_URL")


def _validated_url():
    url = make_url(AGENT_TEST_URL)
    if not url.drivername.startswith("postgresql"):
        pytest.fail("agent test URL must use PostgreSQL")
    if url.host not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("agent test URL must target a loopback host")
    if not (url.database or "").startswith("nudgeflow_test_"):
        pytest.fail("database name must start with nudgeflow_test_")
    return url


@pytest.mark.skipif(
    not AGENT_TEST_URL,
    reason="set NUDGEFLOW_AGENT_TEST_URL to a disposable loopback PostgreSQL database",
)
def test_live_execution_lock_cannot_be_reclaimed_by_another_session():
    url = _validated_url()
    engine = create_engine(url)
    run_lock_id = secrets.randbelow(2_000_000_000) + 1
    first = Session(engine)
    second = Session(engine)
    try:
        assert _try_execution_lock(first, run_lock_id) is True
        assert _try_execution_lock(second, run_lock_id) is False
        _release_execution_lock(first, run_lock_id)
        assert _try_execution_lock(second, run_lock_id) is True
    finally:
        _release_execution_lock(second, run_lock_id)
        first.close()
        second.close()
        engine.dispose()


@pytest.mark.skipif(
    not AGENT_TEST_URL,
    reason="set NUDGEFLOW_AGENT_TEST_URL to a disposable loopback PostgreSQL database",
)
def test_recovery_does_not_claim_an_expired_but_live_execution():
    url = _validated_url()
    engine = create_engine(url)
    if not inspect(engine).has_table("agent_runs"):
        pytest.skip("apply the Alembic head before running the agent lock integration test")

    setup = Session(engine)
    recovery = Session(engine)
    lock_holder = Session(engine)
    try:
        now = datetime.now(timezone.utc)
        tenant = Tenant(name=f"advisory-lock-{uuid.uuid4().hex}")
        setup.add(tenant)
        setup.flush()
        user = User(
            email=f"lock-{uuid.uuid4().hex}@example.test",
            hashed_password="test-only-hash",
            tenant_id=tenant.id,
            tenant_role="owner",
        )
        setup.add(user)
        setup.flush()
        contact = Contact(
            name="Lock test",
            phone_number=f"+1555{secrets.randbelow(10**7):07d}",
            tenant_id=tenant.id,
            owner_id=user.id,
        )
        setup.add(contact)
        setup.flush()
        follow_up = FollowUp(
            contact_id=contact.id,
            tenant_id=tenant.id,
            title="Lock test follow-up",
            due_at=now + timedelta(days=1),
        )
        setup.add(follow_up)
        setup.flush()
        run = AgentRun(
            tenant_id=tenant.id,
            follow_up_id=follow_up.id,
            created_by_user_id=user.id,
            intended_action="send_follow_up_message",
            tool_name="mock_messaging",
            proposed_message="test message",
            status="executing",
            approval_decision="approved",
            execution_token=str(uuid.uuid4()),
            execution_lease_expires_at=now - EXECUTION_LEASE - timedelta(seconds=1),
            tool_invocation_started_at=now - EXECUTION_LEASE,
            updated_at=now - EXECUTION_LEASE,
        )
        setup.add(run)
        setup.commit()
        run_id = run.id

        assert _try_execution_lock(lock_holder, run_id) is True
        live = recover_interrupted_run(recovery, user=user, run_id=run_id)
        assert live["status"] == "executing"
        assert live["execution"] is None

        _release_execution_lock(lock_holder, run_id)
        interrupted = recover_interrupted_run(recovery, user=user, run_id=run_id)
        assert interrupted["status"] == "outcome_uncertain"
        assert interrupted["execution"] is None
        assert interrupted["audit"][-1]["action"] == "recovery_outcome_uncertain"
    finally:
        _release_execution_lock(lock_holder, locals().get("run_id", -1))
        if "run_id" in locals():
            cleanup = setup.get(AgentRun, run_id)
            if cleanup is not None:
                setup.delete(cleanup)
                setup.commit()
        setup.close()
        recovery.close()
        lock_holder.close()
        engine.dispose()
