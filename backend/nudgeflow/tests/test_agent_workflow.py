from datetime import datetime, timedelta, timezone
import uuid


def create_follow_up(client):
    contact_response = client.post(
        "/contacts",
        json={
            "name": "Mira Rao",
            "phone_number": f"+91{uuid.uuid4().int % 10**10:010d}",
        },
    )
    assert contact_response.status_code == 201, contact_response.text
    follow_up_response = client.post(
        "/follow-ups",
        json={
            "contact_id": contact_response.json()["id"],
            "title": "the product quotation",
            "notes": "Do not include private notes in the message draft.",
            "due_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
    )
    assert follow_up_response.status_code == 201, follow_up_response.text
    return contact_response.json(), follow_up_response.json()


def start_run(client, follow_up_id):
    return client.post("/agent/runs", json={"follow_up_id": follow_up_id})


class CountingTool:
    name = "mock_messaging"

    def __init__(self, result_factory=None, error=None):
        self.calls = []
        self.result_factory = result_factory
        self.error = error

    def send(self, *, run_id, message):
        self.calls.append((run_id, message))
        if self.error:
            raise self.error
        if self.result_factory:
            return self.result_factory(run_id, message)
        return {
            "provider": "mock",
            "message_id": f"mock-{run_id}",
            "run_id": run_id,
            "accepted": True,
        }


def register_tool(monkeypatch, tool):
    from nudgeflow.services.agent.tools import TOOL_REGISTRY

    monkeypatch.setitem(TOOL_REGISTRY, "mock_messaging", tool)


def test_run_persists_draft_awaiting_approval_without_sending(client, monkeypatch):
    contact, follow_up = create_follow_up(client)
    tool = CountingTool()
    register_tool(monkeypatch, tool)

    response = start_run(client, follow_up["id"])

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "awaiting_approval"
    assert data["approval_decision"] is None
    assert data["execution"] is None
    assert data["plan"] == {
        "follow_up_id": follow_up["id"],
        "intended_action": "send_follow_up_message",
        "message": data["proposed_message"],
        "tool_name": "mock_messaging",
    }
    assert contact["name"] in data["proposed_message"]
    assert "private notes" not in data["proposed_message"]
    assert [event["action"] for event in data["audit"]] == ["run_created"]
    assert tool.calls == []

    persisted = client.get(f"/agent/runs/{data['id']}")
    assert persisted.status_code == 200
    assert persisted.json()["status"] == "awaiting_approval"
    assert tool.calls == []


def test_approval_executes_mock_once_and_records_verified_result(client, monkeypatch):
    _, follow_up = create_follow_up(client)
    tool = CountingTool()
    register_tool(monkeypatch, tool)
    run = start_run(client, follow_up["id"]).json()

    response = client.post(f"/agent/runs/{run['id']}/approve")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "completed"
    assert data["approval_decision"] == "approved"
    assert data["execution"]["status"] == "succeeded"
    assert data["execution"]["verified"] is True
    assert data["execution"]["result"]["message_id"] == f"mock-{run['id']}"
    assert [event["action"] for event in data["audit"]] == [
        "run_created",
        "approval_granted",
        "execution_claimed",
        "tool_invocation_started",
        "execution_recorded",
        "execution_verified",
    ]
    assert len(tool.calls) == 1


def test_rejection_is_persisted_and_never_executes(client, monkeypatch):
    _, follow_up = create_follow_up(client)
    tool = CountingTool()
    register_tool(monkeypatch, tool)
    run = start_run(client, follow_up["id"]).json()

    rejected = client.post(
        f"/agent/runs/{run['id']}/reject", json={"reason": "Needs editing"}
    )
    repeated = client.post(f"/agent/runs/{run['id']}/reject", json={})

    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["approval_decision"] == "rejected"
    assert rejected.json()["rejection_reason"] == "Needs editing"
    assert repeated.status_code == 200
    assert repeated.json()["status"] == "rejected"
    assert [event["action"] for event in repeated.json()["audit"]] == [
        "run_created",
        "approval_rejected",
    ]
    assert tool.calls == []

    assert client.post(f"/agent/runs/{run['id']}/approve").status_code == 409
    assert tool.calls == []


def test_repeated_approval_returns_result_without_duplicate_send(client, monkeypatch):
    _, follow_up = create_follow_up(client)
    tool = CountingTool()
    register_tool(monkeypatch, tool)
    run = start_run(client, follow_up["id"]).json()

    first = client.post(f"/agent/runs/{run['id']}/approve")
    second = client.post(f"/agent/runs/{run['id']}/approve")

    assert first.status_code == second.status_code == 200
    assert first.json()["execution"]["id"] == second.json()["execution"]["id"]
    assert second.json()["status"] == "completed"
    assert len(tool.calls) == 1


def test_completed_run_cannot_be_rejected(client):
    _, follow_up = create_follow_up(client)
    run = start_run(client, follow_up["id"]).json()
    assert client.post(f"/agent/runs/{run['id']}/approve").json()["status"] == "completed"

    response = client.post(f"/agent/runs/{run['id']}/reject", json={})

    assert response.status_code == 409


def test_tool_failure_is_persisted_without_false_success(client, monkeypatch):
    _, follow_up = create_follow_up(client)
    tool = CountingTool(error=RuntimeError("private message and secret must not leak"))
    register_tool(monkeypatch, tool)
    run = start_run(client, follow_up["id"]).json()

    response = client.post(f"/agent/runs/{run['id']}/approve")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "outcome_uncertain"
    assert data["approval_decision"] == "approved"
    assert data["execution"]["status"] == "uncertain"
    assert data["execution"]["verified"] is False
    assert data["execution"]["error_code"] == "tool_error_RuntimeError"
    assert "private message" not in response.text
    assert "secret must not leak" not in response.text
    assert [event["action"] for event in data["audit"]][-2:] == [
        "execution_recorded",
        "execution_outcome_uncertain",
    ]
    assert len(tool.calls) == 1

    # Failed approved runs are terminal and do not retry a possibly ambiguous tool call.
    again = client.post(f"/agent/runs/{run['id']}/approve")
    assert again.status_code == 200
    assert again.json()["status"] == "outcome_uncertain"
    assert len(tool.calls) == 1


def test_unaccepted_tool_result_is_not_reported_as_success(client, monkeypatch):
    _, follow_up = create_follow_up(client)
    tool = CountingTool(
        result_factory=lambda run_id, message: {
            "provider": "mock",
            "message_id": f"mock-{run_id}",
            "run_id": run_id,
            "accepted": False,
        }
    )
    register_tool(monkeypatch, tool)
    run = start_run(client, follow_up["id"]).json()

    response = client.post(f"/agent/runs/{run['id']}/approve")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["execution"]["status"] == "failed"
    assert response.json()["execution"]["verified"] is False
    assert len(tool.calls) == 1


def test_runs_and_followups_are_isolated_by_tenant(client):
    _, follow_up = create_follow_up(client)
    run = start_run(client, follow_up["id"]).json()
    registration = client.post(
        "/auth/register",
        json={
            "email": f"other-{uuid.uuid4().hex}@example.com",
            "password": "Another-password-123!",
        },
    )
    assert registration.status_code == 201, registration.text
    login = client.post(
        "/auth/login",
        json={
            "email": registration.json()["email"],
            "password": "Another-password-123!",
        },
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert start_run(client, follow_up["id"]).status_code == 201
    assert client.post(
        "/agent/runs", json={"follow_up_id": follow_up["id"]}, headers=other_headers
    ).status_code == 404
    assert client.get(f"/agent/runs/{run['id']}", headers=other_headers).status_code == 404
    assert client.post(
        f"/agent/runs/{run['id']}/approve", headers=other_headers
    ).status_code == 404


def test_unknown_followup_and_deleted_contact_are_not_available(client):
    assert start_run(client, 999999999).status_code == 404
    contact, follow_up = create_follow_up(client)
    assert client.delete(f"/contacts/{contact['id']}").status_code == 204

    response = start_run(client, follow_up["id"])

    assert response.status_code == 404
    assert response.json()["detail"] == "Follow-up not found."


def test_agent_routes_require_authentication(anonymous_client):
    assert anonymous_client.post("/agent/runs", json={"follow_up_id": 1}).status_code == 401
    assert anonymous_client.get("/agent/runs/1").status_code == 401


def mark_interrupted(db_session, run_id, *, invocation_started):
    from nudgeflow.models.agent import AgentRun
    from nudgeflow.services.agent.workflow import EXECUTION_LEASE

    run = db_session.get(AgentRun, run_id)
    now = datetime.now(timezone.utc)
    run.status = "executing"
    run.approval_decision = "approved"
    run.execution_token = str(uuid.uuid4())
    run.execution_lease_expires_at = now - EXECUTION_LEASE - timedelta(seconds=1)
    run.tool_invocation_started_at = now - EXECUTION_LEASE if invocation_started else None
    db_session.commit()


def test_recovery_marks_expired_pre_invocation_run_ready_without_sending(
    client, db_session, monkeypatch
):
    _, follow_up = create_follow_up(client)
    tool = CountingTool()
    register_tool(monkeypatch, tool)
    run = start_run(client, follow_up["id"]).json()
    mark_interrupted(db_session, run["id"], invocation_started=False)

    recovered = client.post(f"/agent/runs/{run['id']}/recover")
    repeated_approval = client.post(f"/agent/runs/{run['id']}/approve")

    assert recovered.status_code == 200
    assert recovered.json()["status"] == "ready_to_execute"
    assert repeated_approval.json()["status"] == "ready_to_execute"
    assert tool.calls == []
    assert [event["action"] for event in recovered.json()["audit"]][-1] == (
        "recovery_ready_to_execute"
    )


def test_explicit_execute_resumes_proven_not_invoked_run_once(
    client, db_session, monkeypatch
):
    _, follow_up = create_follow_up(client)
    tool = CountingTool()
    register_tool(monkeypatch, tool)
    run = start_run(client, follow_up["id"]).json()
    mark_interrupted(db_session, run["id"], invocation_started=False)
    assert client.post(f"/agent/runs/{run['id']}/recover").json()["status"] == (
        "ready_to_execute"
    )

    first = client.post(f"/agent/runs/{run['id']}/execute")
    second = client.post(f"/agent/runs/{run['id']}/execute")

    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == second.json()["status"] == "completed"
    assert len(tool.calls) == 1


def test_expired_run_after_tool_marker_is_uncertain_and_never_resent(
    client, db_session, monkeypatch
):
    _, follow_up = create_follow_up(client)
    tool = CountingTool()
    register_tool(monkeypatch, tool)
    run = start_run(client, follow_up["id"]).json()
    mark_interrupted(db_session, run["id"], invocation_started=True)

    recovered = client.post(f"/agent/runs/{run['id']}/recover")
    approve_again = client.post(f"/agent/runs/{run['id']}/approve")
    execute_again = client.post(f"/agent/runs/{run['id']}/execute")

    assert recovered.json()["status"] == "outcome_uncertain"
    assert recovered.json()["execution"] is None
    assert approve_again.json()["status"] == "outcome_uncertain"
    assert execute_again.json()["status"] == "outcome_uncertain"
    assert [event["action"] for event in recovered.json()["audit"]][-1] == (
        "recovery_outcome_uncertain"
    )
    assert tool.calls == []


def test_unexpired_execution_is_not_reclaimed(client, db_session, monkeypatch):
    from nudgeflow.models.agent import AgentRun

    _, follow_up = create_follow_up(client)
    tool = CountingTool()
    register_tool(monkeypatch, tool)
    run = start_run(client, follow_up["id"]).json()
    active = db_session.get(AgentRun, run["id"])
    active.status = "executing"
    active.approval_decision = "approved"
    active.execution_token = str(uuid.uuid4())
    active.execution_lease_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    active.tool_invocation_started_at = datetime.now(timezone.utc)
    db_session.commit()

    recovered = client.post(f"/agent/runs/{run['id']}/recover")
    repeated_approval = client.post(f"/agent/runs/{run['id']}/approve")

    assert recovered.json()["status"] == "executing"
    assert repeated_approval.json()["status"] == "executing"
    assert tool.calls == []


def test_tool_exception_is_uncertain_and_repeated_approval_does_not_retry(
    client, monkeypatch
):
    _, follow_up = create_follow_up(client)
    tool = CountingTool(error=RuntimeError("provider result may be ambiguous"))
    register_tool(monkeypatch, tool)
    run = start_run(client, follow_up["id"]).json()

    first = client.post(f"/agent/runs/{run['id']}/approve")
    second = client.post(f"/agent/runs/{run['id']}/approve")

    assert first.json()["status"] == second.json()["status"] == "outcome_uncertain"
    assert first.json()["execution"]["status"] == "uncertain"
    assert first.json()["execution"]["verified"] is False
    assert len(tool.calls) == 1


def test_recovery_is_tenant_scoped(client, db_session, monkeypatch):
    from nudgeflow.models.agent import AgentRun

    _, follow_up = create_follow_up(client)
    run = start_run(client, follow_up["id"]).json()
    mark_interrupted(db_session, run["id"], invocation_started=False)
    registration = client.post(
        "/auth/register",
        json={
            "email": f"recover-{uuid.uuid4().hex}@example.com",
            "password": "Another-password-123!",
        },
    )
    assert registration.status_code == 201
    login = client.post(
        "/auth/login",
        json={
            "email": registration.json()["email"],
            "password": "Another-password-123!",
        },
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(f"/agent/runs/{run['id']}/recover", headers=other_headers)

    assert response.status_code == 404
    assert db_session.get(AgentRun, run["id"]).status == "executing"


def test_definitive_tool_rejection_is_failed_and_not_retried(client, monkeypatch):
    _, follow_up = create_follow_up(client)
    tool = CountingTool(
        result_factory=lambda run_id, message: {
            "provider": "mock",
            "message_id": f"mock-{run_id}",
            "run_id": run_id,
            "accepted": False,
        }
    )
    register_tool(monkeypatch, tool)
    run = start_run(client, follow_up["id"]).json()

    first = client.post(f"/agent/runs/{run['id']}/approve")
    repeated = client.post(f"/agent/runs/{run['id']}/approve")

    assert first.json()["status"] == repeated.json()["status"] == "failed"
    assert first.json()["execution"]["status"] == "failed"
    assert first.json()["execution"]["verified"] is False
    assert len(tool.calls) == 1
