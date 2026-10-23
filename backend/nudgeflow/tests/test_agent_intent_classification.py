from datetime import datetime, timedelta, timezone
import uuid


def create_follow_up(client):
    contact = client.post(
        "/contacts",
        json={
            "name": "Arun Das",
            "phone_number": f"+91{uuid.uuid4().int % 10**10:010d}",
        },
    )
    assert contact.status_code == 201
    follow_up = client.post(
        "/follow-ups",
        json={
            "contact_id": contact.json()["id"],
            "title": "the annual service plan",
            "due_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
    )
    assert follow_up.status_code == 201
    return follow_up.json()


def test_supplied_customer_message_is_classified_and_persisted(
    client, monkeypatch
):
    from nudgeflow.services.agent import workflow

    follow_up = create_follow_up(client)
    received = []

    def fake_classifier(message):
        received.append(message)
        return {
            "status": "classified",
            "reason": None,
            "intent": "service_enquiry",
            "confidence": 0.91,
            "error_code": None,
        }

    monkeypatch.setattr(workflow, "classify_customer_message", fake_classifier)
    message = "Could someone service my air conditioner next week?"

    response = client.post(
        "/agent/runs",
        json={"follow_up_id": follow_up["id"], "customer_message": message},
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert received == [message]
    assert data["intent_classification"] == {
        "status": "classified",
        "reason": None,
        "intent": "service_enquiry",
        "confidence": 0.91,
        "error_code": None,
    }
    assert data["status"] == "awaiting_approval"
    assert message not in data["proposed_message"]
    assert message not in response.text
    assert data["execution"] is None
    persisted = client.get(f"/agent/runs/{data['id']}").json()
    assert persisted["intent_classification"] == data["intent_classification"]


def test_missing_customer_message_is_explicitly_not_classified(client, monkeypatch):
    from nudgeflow.services.agent import workflow

    follow_up = create_follow_up(client)
    monkeypatch.setattr(
        workflow,
        "classify_customer_message",
        lambda _message: (_ for _ in ()).throw(AssertionError("must not classify")),
    )

    response = client.post("/agent/runs", json={"follow_up_id": follow_up["id"]})

    assert response.status_code == 201, response.text
    assert response.json()["intent_classification"] == {
        "status": "not_performed",
        "reason": "missing_input",
        "intent": None,
        "confidence": None,
        "error_code": None,
    }


def test_unavailable_classifier_is_reported_without_fabricated_prediction(
    client, monkeypatch
):
    from nudgeflow.services.agent import workflow

    follow_up = create_follow_up(client)
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

    response = client.post(
        "/agent/runs",
        json={"follow_up_id": follow_up["id"], "customer_message": "Need help"},
    )

    assert response.status_code == 201
    assert response.json()["intent_classification"] == {
        "status": "unavailable",
        "reason": None,
        "intent": None,
        "confidence": None,
        "error_code": "model_artifact_missing",
    }


def test_inference_exception_does_not_fail_run_creation(client, monkeypatch):
    from nudgeflow.services.agent import workflow

    follow_up = create_follow_up(client)

    def failed_inference(_message):
        raise RuntimeError("the exception must not be exposed")

    monkeypatch.setattr(workflow, "classify_customer_message", failed_inference)

    response = client.post(
        "/agent/runs",
        json={"follow_up_id": follow_up["id"], "customer_message": "Hello"},
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "awaiting_approval"
    assert data["intent_classification"] == {
        "status": "error",
        "reason": None,
        "intent": None,
        "confidence": None,
        "error_code": "inference_failed",
    }
    assert "the exception" not in response.text


def test_classification_does_not_bypass_approval_or_run_tool(
    client, monkeypatch
):
    from nudgeflow.services.agent.tools import TOOL_REGISTRY
    from nudgeflow.services.agent import workflow

    follow_up = create_follow_up(client)
    calls = []

    class Tool:
        name = "mock_messaging"

        def send(self, *, run_id, message):
            calls.append((run_id, message))
            return {
                "provider": "mock",
                "message_id": f"mock-{run_id}",
                "run_id": run_id,
                "accepted": True,
            }

    monkeypatch.setitem(TOOL_REGISTRY, "mock_messaging", Tool())
    monkeypatch.setattr(
        workflow,
        "classify_customer_message",
        lambda _message: {
            "status": "classified",
            "reason": None,
            "intent": "cancellation",
            "confidence": 0.88,
            "error_code": None,
        },
    )

    created = client.post(
        "/agent/runs",
        json={"follow_up_id": follow_up["id"], "customer_message": "Cancel it"},
    )

    assert created.status_code == 201
    run = created.json()
    assert run["intent_classification"]["intent"] == "cancellation"
    assert run["status"] == "awaiting_approval"
    assert calls == []


def test_customer_message_is_validated(client):
    follow_up = create_follow_up(client)

    blank = client.post(
        "/agent/runs",
        json={"follow_up_id": follow_up["id"], "customer_message": "   "},
    )
    too_long = client.post(
        "/agent/runs",
        json={"follow_up_id": follow_up["id"], "customer_message": "x" * 5001},
    )

    assert blank.status_code == 422
    assert too_long.status_code == 422


def test_other_tenant_cannot_submit_message_for_classification(client, monkeypatch):
    from nudgeflow.services.agent import workflow

    follow_up = create_follow_up(client)
    classifier_calls = []
    monkeypatch.setattr(
        workflow,
        "classify_customer_message",
        lambda message: classifier_calls.append(message),
    )
    registration = client.post(
        "/auth/register",
        json={
            "email": f"other-{uuid.uuid4().hex}@example.com",
            "password": "Another-password-123!",
        },
    )
    login = client.post(
        "/auth/login",
        json={
            "email": registration.json()["email"],
            "password": "Another-password-123!",
        },
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(
        "/agent/runs",
        json={
            "follow_up_id": follow_up["id"],
            "customer_message": "Private customer text",
        },
        headers=other_headers,
    )

    assert response.status_code == 404
    assert classifier_calls == []
