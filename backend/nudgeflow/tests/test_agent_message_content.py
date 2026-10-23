import json
from datetime import datetime, timedelta, timezone
import uuid


def create_follow_up(client):
    contact = client.post(
        "/contacts",
        json={
            "name": "Mira Rao",
            "phone_number": f"+91{uuid.uuid4().int % 10**10:010d}",
        },
    )
    assert contact.status_code == 201, contact.text
    follow_up = client.post(
        "/follow-ups",
        json={
            "contact_id": contact.json()["id"],
            "title": "the garden installation enquiry",
            "notes": "Private staff note that must not reach the model or draft.",
            "due_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
    )
    assert follow_up.status_code == 201, follow_up.text
    return contact.json(), follow_up.json()


def extraction_payload(**overrides):
    payload = {
        "request_summary": "Asks about a garden installation appointment.",
        "requested_action": "Arrange a consultation.",
        "product_or_service": "garden installation",
        "date_or_time_mentioned": "next Friday afternoon",
        "quantity": None,
        "budget": None,
        "other_details": [],
        "missing_information": ["property location", "preferred time"],
    }
    payload.update(overrides)
    return json.dumps(payload)


class FakeLLM:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def complete_json(self, *, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def stub_classifier(monkeypatch):
    from nudgeflow.services.agent import workflow

    monkeypatch.setattr(
        workflow,
        "classify_customer_message",
        lambda _message: {
            "status": "classified",
            "reason": None,
            "intent": "booking_enquiry",
            "confidence": 0.76,
            "error_code": None,
        },
    )


def test_valid_text_is_extracted_and_contextual_draft_is_persisted(client, monkeypatch):
    from nudgeflow.services.agent import workflow

    _, follow_up = create_follow_up(client)
    stub_classifier(monkeypatch)
    message = "Can you arrange a garden installation consultation next Friday afternoon?"
    draft = "Hi Mira, thanks for asking about a consultation. What area is the property in, and what time works for you?"
    llm = FakeLLM(
        extraction_payload(),
        json.dumps({"message": draft}),
    )
    monkeypatch.setattr(workflow, "get_llm_client", lambda: llm)

    response = client.post(
        "/agent/runs",
        json={"follow_up_id": follow_up["id"], "customer_message": message},
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["message_extraction"]["status"] == "completed"
    assert data["message_extraction"]["data"]["date_or_time_mentioned"] == (
        "next Friday afternoon"
    )
    assert data["message_extraction"]["data"]["missing_information"] == [
        "property location",
        "preferred time",
    ]
    assert data["draft"] == {"status": "generated", "source": "llm", "error_code": None}
    assert data["proposed_message"] == draft
    assert data["intent_classification"]["intent"] == "booking_enquiry"
    assert data["status"] == "awaiting_approval"
    assert data["execution"] is None
    assert message not in response.text
    assert len(llm.calls) == 2

    extraction_prompt = llm.calls[0][0].lower()
    assert "never infer dates" in extraction_prompt
    draft_input = json.loads(llm.calls[1][1])
    assert draft_input["customer_message"] == message
    assert draft_input["extraction"]["missing_information"] == [
        "property location",
        "preferred time",
    ]
    assert draft_input["customer_first_name"] == "Mira"
    assert draft_input["follow_up_title"] == "the garden installation enquiry"
    assert "Private staff note" not in llm.calls[1][1]

    persisted = client.get(f"/agent/runs/{data['id']}").json()
    assert persisted["message_extraction"] == data["message_extraction"]
    assert persisted["draft"] == data["draft"]


def test_missing_text_skips_extraction_and_keeps_existing_safe_draft(client, monkeypatch):
    from nudgeflow.services.agent import workflow

    contact, follow_up = create_follow_up(client)
    monkeypatch.setattr(
        workflow,
        "classify_customer_message",
        lambda _message: (_ for _ in ()).throw(AssertionError("no input to classify")),
    )
    monkeypatch.setattr(
        workflow,
        "get_llm_client",
        lambda: (_ for _ in ()).throw(AssertionError("no input to send to LLM")),
    )

    response = client.post("/agent/runs", json={"follow_up_id": follow_up["id"]})

    assert response.status_code == 201
    data = response.json()
    assert data["message_extraction"] == {
        "status": "not_performed",
        "data": None,
        "error_code": "missing_input",
    }
    assert data["draft"] == {
        "status": "fallback",
        "source": "deterministic",
        "error_code": "missing_customer_message",
    }
    assert contact["name"] in data["proposed_message"]
    assert follow_up["title"] in data["proposed_message"]


def test_ambiguous_date_and_unknown_details_remain_unresolved(client, monkeypatch):
    from nudgeflow.services.agent import workflow

    _, follow_up = create_follow_up(client)
    stub_classifier(monkeypatch)
    llm = FakeLLM(
        extraction_payload(
            date_or_time_mentioned="sometime after the holidays",
            quantity=None,
            budget=None,
            missing_information=["exact date", "budget", "number of rooms"],
        ),
        json.dumps({"message": "Could you share an exact date, budget, and room count?"}),
    )
    monkeypatch.setattr(workflow, "get_llm_client", lambda: llm)

    response = client.post(
        "/agent/runs",
        json={
            "follow_up_id": follow_up["id"],
            "customer_message": "Maybe after the holidays, not sure how many rooms yet.",
        },
    )

    extraction = response.json()["message_extraction"]["data"]
    assert extraction["date_or_time_mentioned"] == "sometime after the holidays"
    assert extraction["quantity"] is None
    assert extraction["budget"] is None
    assert extraction["missing_information"] == ["exact date", "budget", "number of rooms"]


def test_missing_llm_configuration_is_explicit_and_falls_back(client, monkeypatch):
    from nudgeflow.services.agent import workflow

    _, follow_up = create_follow_up(client)
    stub_classifier(monkeypatch)
    monkeypatch.setattr(workflow, "get_llm_client", lambda: None)

    response = client.post(
        "/agent/runs",
        json={"follow_up_id": follow_up["id"], "customer_message": "Do you offer installation?"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["message_extraction"]["status"] == "unavailable"
    assert data["message_extraction"]["error_code"] == "llm_not_configured"
    assert data["message_extraction"]["data"] is None
    assert data["draft"]["status"] == "fallback"
    assert data["draft"]["source"] == "deterministic"
    assert data["draft"]["error_code"] == "llm_not_configured"


def test_malformed_extraction_is_not_persisted_as_success(client, monkeypatch):
    from nudgeflow.services.agent import workflow

    _, follow_up = create_follow_up(client)
    stub_classifier(monkeypatch)
    llm = FakeLLM('{"request_summary":"Unsupported", "invented_field":true}')
    monkeypatch.setattr(workflow, "get_llm_client", lambda: llm)

    response = client.post(
        "/agent/runs",
        json={"follow_up_id": follow_up["id"], "customer_message": "Hello there"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["message_extraction"] == {
        "status": "failed",
        "data": None,
        "error_code": "invalid_extraction_output",
    }
    assert data["draft"]["status"] == "fallback"
    assert data["draft"]["source"] == "deterministic"
    assert len(llm.calls) == 1


def test_provider_failure_preserves_run_and_records_error(client, monkeypatch):
    from nudgeflow.services.agent import workflow
    from nudgeflow.services.agent.llm_client import LLMProviderError

    _, follow_up = create_follow_up(client)
    stub_classifier(monkeypatch)
    llm = FakeLLM(LLMProviderError("provider_timeout"))
    monkeypatch.setattr(workflow, "get_llm_client", lambda: llm)

    response = client.post(
        "/agent/runs",
        json={"follow_up_id": follow_up["id"], "customer_message": "Need an appointment"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "awaiting_approval"
    assert data["message_extraction"]["status"] == "failed"
    assert data["message_extraction"]["error_code"] == "provider_timeout"
    assert data["draft"]["status"] == "fallback"
    assert data["draft"]["error_code"] == "extraction_failed"
    assert data["execution"] is None


def test_draft_failure_uses_distinguishable_fallback(client, monkeypatch):
    from nudgeflow.services.agent import workflow
    from nudgeflow.services.agent.llm_client import LLMProviderError

    _, follow_up = create_follow_up(client)
    stub_classifier(monkeypatch)
    llm = FakeLLM(extraction_payload(), LLMProviderError("provider_rate_limited"))
    monkeypatch.setattr(workflow, "get_llm_client", lambda: llm)

    response = client.post(
        "/agent/runs",
        json={"follow_up_id": follow_up["id"], "customer_message": "Can I book next week?"},
    )

    data = response.json()
    assert response.status_code == 201
    assert data["message_extraction"]["status"] == "completed"
    assert data["draft"] == {
        "status": "fallback",
        "source": "deterministic",
        "error_code": "provider_rate_limited",
    }
    assert data["proposed_message"].startswith("Hi Mira, thanks for reaching out.")


def test_generated_draft_does_not_claim_price_availability_or_confirmation(
    client, monkeypatch
):
    from nudgeflow.services.agent import workflow

    _, follow_up = create_follow_up(client)
    stub_classifier(monkeypatch)
    draft = "Could you share your preferred date and location so we can check the details?"
    llm = FakeLLM(extraction_payload(), json.dumps({"message": draft}))
    monkeypatch.setattr(workflow, "get_llm_client", lambda: llm)

    response = client.post(
        "/agent/runs",
        json={
            "follow_up_id": follow_up["id"],
            "customer_message": "Can you install this Friday? How much is it?",
        },
    )

    assert response.status_code == 201
    prompt = " ".join(llm.calls[1][0].lower().split())
    assert "never invent or assert" in prompt
    output = response.json()["proposed_message"].lower()
    assert not any(
        phrase in output
        for phrase in ("₹", "available", "confirmed", "booked", "discount", "we charge")
    )


def test_draft_is_only_a_proposal_and_never_executes_tool(client, monkeypatch):
    from nudgeflow.services.agent import workflow
    from nudgeflow.services.agent.tools import TOOL_REGISTRY

    _, follow_up = create_follow_up(client)
    stub_classifier(monkeypatch)
    calls = []

    class Tool:
        name = "mock_messaging"

        def send(self, *, run_id, message):
            calls.append((run_id, message))
            return {"provider": "mock", "message_id": f"{run_id}", "run_id": run_id, "accepted": True}

    monkeypatch.setitem(TOOL_REGISTRY, "mock_messaging", Tool())
    llm = FakeLLM(
        extraction_payload(),
        json.dumps({"message": "Could you tell us which date suits you?"}),
    )
    monkeypatch.setattr(workflow, "get_llm_client", lambda: llm)

    response = client.post(
        "/agent/runs",
        json={"follow_up_id": follow_up["id"], "customer_message": "Book me for next week"},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "awaiting_approval"
    assert response.json()["draft"]["source"] == "llm"
    assert calls == []
