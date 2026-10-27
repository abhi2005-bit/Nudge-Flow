import json
from datetime import datetime, timedelta, timezone
import uuid

import pytest


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


def test_llm_authentication_failure_regression(client, monkeypatch):
    """When the LLM provider returns 401/403, run creation falls back safely without failing."""
    from nudgeflow.services.agent import workflow
    from nudgeflow.services.agent.llm_client import LLMProviderError

    _, follow_up = create_follow_up(client)
    stub_classifier(monkeypatch)
    llm = FakeLLM(LLMProviderError("provider_authentication_failed"))
    monkeypatch.setattr(workflow, "get_llm_client", lambda: llm)

    response = client.post(
        "/agent/runs",
        json={"follow_up_id": follow_up["id"], "customer_message": "Hello, need pricing"},
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "awaiting_approval"
    assert data["approval_decision"] is None
    assert data["execution"] is None
    assert data["message_extraction"] == {
        "status": "failed",
        "data": None,
        "error_code": "provider_authentication_failed",
    }
    assert data["draft"] == {
        "status": "fallback",
        "source": "deterministic",
        "error_code": "extraction_failed",
    }
    assert "thanks for reaching out" in data["proposed_message"]


def test_exact_message_bypasses_llm_and_is_approval_gated(client, monkeypatch):
    """Developers can specify exact_message, which completely bypasses the LLM and waits for approval."""
    from nudgeflow.services.agent import workflow

    _, follow_up = create_follow_up(client)
    stub_classifier(monkeypatch)

    class ExplosiveLLM:
        def complete_json(self, **kwargs):
            raise AssertionError("LLM should not be called when exact_message is provided.")

    monkeypatch.setattr(workflow, "get_llm_client", lambda: ExplosiveLLM())

    exact_text = "Hello! This is an authorized exact message for integration verification."
    response = client.post(
        "/agent/runs",
        json={
            "follow_up_id": follow_up["id"],
            "exact_message": exact_text,
        },
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "awaiting_approval"
    assert data["approval_decision"] is None
    assert data["execution"] is None
    assert data["proposed_message"] == exact_text
    assert data["plan"]["message"] == exact_text
    assert data["message_extraction"]["status"] == "not_performed"
    assert data["draft"]["status"] == "fallback"
    assert data["draft"]["source"] == "deterministic"
    assert data["draft"]["error_code"] is None
    audit_events = data["audit"]
    assert audit_events[0]["action"] == "run_created"
    assert audit_events[0]["details"]["exact_message"] is True


def test_exact_message_with_customer_message_classifies_intent_and_uses_exact_draft(
    client, monkeypatch
):
    from nudgeflow.services.agent import workflow

    _, follow_up = create_follow_up(client)
    stub_classifier(monkeypatch)

    class ExplosiveLLM:
        def complete_json(self, **kwargs):
            raise AssertionError("LLM should not be called when exact_message is provided.")

    monkeypatch.setattr(workflow, "get_llm_client", lambda: ExplosiveLLM())

    response = client.post(
        "/agent/runs",
        json={
            "follow_up_id": follow_up["id"],
            "customer_message": "Can I cancel my appointment?",
            "exact_message": "Your appointment has been cancelled as requested.",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "awaiting_approval"
    assert data["intent_classification"]["status"] == "classified"
    assert data["proposed_message"] == "Your appointment has been cancelled as requested."
    assert data["draft"]["source"] == "deterministic"


def test_exact_message_validation_blank_or_too_long(client):
    _, follow_up = create_follow_up(client)

    # Blank message rejected
    blank_resp = client.post(
        "/agent/runs",
        json={"follow_up_id": follow_up["id"], "exact_message": "   "},
    )
    assert blank_resp.status_code == 422

    # Message exceeding 4096 characters rejected
    too_long_resp = client.post(
        "/agent/runs",
        json={"follow_up_id": follow_up["id"], "exact_message": "A" * 4097},
    )
    assert too_long_resp.status_code == 422


def test_groq_client_integration_with_workflow(client, monkeypatch):
    """Workflow successfully uses GroqChatClient with mocked HTTP to extract and draft."""
    from nudgeflow.config import settings
    from nudgeflow.services.agent import workflow
    from nudgeflow.services.agent.llm_client import GroqChatClient

    _, follow_up = create_follow_up(client)
    stub_classifier(monkeypatch)

    extraction_json = extraction_payload()
    draft_json = json.dumps({"message": "Hi Mira, thanks for inquiring. Let's discuss details."})

    responses = [
        json.dumps({"choices": [{"message": {"content": extraction_json}}]}).encode("utf-8"),
        json.dumps({"choices": [{"message": {"content": draft_json}}]}).encode("utf-8"),
    ]
    calls = []

    class MockResponse:
        def __init__(self, data):
            self.data = data

        def read(self, n=-1):
            return self.data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout):
        calls.append((req, timeout))
        return MockResponse(responses.pop(0))

    monkeypatch.setattr("nudgeflow.services.agent.llm_client.urlopen", fake_urlopen)

    groq_client = GroqChatClient(
        api_key="mock-groq-key",
        model="openai/gpt-oss-20b",
        timeout_seconds=15,
        user_agent=f"NudgeFlow/{settings.app_version}",
    )
    monkeypatch.setattr(workflow, "get_llm_client", lambda: groq_client)

    response = client.post(
        "/agent/runs",
        json={
            "follow_up_id": follow_up["id"],
            "customer_message": "Can you provide consultation next Friday?",
        },
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["message_extraction"]["status"] == "completed"
    assert data["draft"]["status"] == "generated"
    assert data["draft"]["source"] == "llm"
    assert data["draft"]["error_code"] is None
    assert data["proposed_message"] == "Hi Mira, thanks for inquiring. Let's discuss details."
    assert len(calls) == 2
    assert calls[0][0].get_header("User-agent") == f"NudgeFlow/{settings.app_version}"
    assert calls[0][0].get_header("Authorization") == "Bearer mock-groq-key"


def test_llm_permission_denied_regression(client, monkeypatch):
    """When the LLM provider returns 403, run creation falls back safely without failing."""
    from nudgeflow.services.agent import workflow
    from nudgeflow.services.agent.llm_client import LLMProviderError

    _, follow_up = create_follow_up(client)
    stub_classifier(monkeypatch)
    llm = FakeLLM(LLMProviderError("provider_permission_denied"))
    monkeypatch.setattr(workflow, "get_llm_client", lambda: llm)

    response = client.post(
        "/agent/runs",
        json={"follow_up_id": follow_up["id"], "customer_message": "Hello, need pricing"},
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "awaiting_approval"
    assert data["message_extraction"] == {
        "status": "failed",
        "data": None,
        "error_code": "provider_permission_denied",
    }
    assert data["draft"] == {
        "status": "fallback",
        "source": "deterministic",
        "error_code": "extraction_failed",
    }


def test_llm_model_not_found_regression(client, monkeypatch):
    """When the LLM provider returns 404 (e.g. invalid model), fallback is used safely."""
    from nudgeflow.services.agent import workflow
    from nudgeflow.services.agent.llm_client import LLMProviderError

    _, follow_up = create_follow_up(client)
    stub_classifier(monkeypatch)
    llm = FakeLLM(LLMProviderError("provider_model_not_found"))
    monkeypatch.setattr(workflow, "get_llm_client", lambda: llm)

    response = client.post(
        "/agent/runs",
        json={"follow_up_id": follow_up["id"], "customer_message": "Hello, need pricing"},
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "awaiting_approval"
    assert data["message_extraction"] == {
        "status": "failed",
        "data": None,
        "error_code": "provider_model_not_found",
    }
    assert data["draft"] == {
        "status": "fallback",
        "source": "deterministic",
        "error_code": "extraction_failed",
    }


def test_unicode_apostrophes_and_characters_preservation(client, monkeypatch):
    """UTF-8 text (curly apostrophes, accents, symbols) is preserved in storage and JSON serialization."""
    from nudgeflow.services.agent import workflow

    _, follow_up = create_follow_up(client)
    stub_classifier(monkeypatch)

    unicode_text = "Hi Mira, you’re welcome to visit our café! We’ll reserve ₹500 credit for you. ✨"
    llm = FakeLLM(
        extraction_payload(),
        json.dumps({"message": unicode_text}, ensure_ascii=False),
    )
    monkeypatch.setattr(workflow, "get_llm_client", lambda: llm)

    response = client.post(
        "/agent/runs",
        json={
            "follow_up_id": follow_up["id"],
            "customer_message": "Can I visit your café next week?",
        },
    )

    assert response.status_code == 201, response.text
    # Verify Content-Type explicitly declares charset=utf-8
    assert response.headers["content-type"] == "application/json; charset=utf-8"
    data = response.json()
    assert data["proposed_message"] == unicode_text
    assert "you’re" in data["proposed_message"]
    assert "café" in data["proposed_message"]
    assert "₹500" in data["proposed_message"]
    assert "✨" in data["proposed_message"]


def test_whitespace_and_spacing_normalization():
    """Draft normalization strips zero-width chars, fixes punctuation spacing, and repairs joined words."""
    from nudgeflow.services.agent.message_content import DraftMessageOutput

    # Zero-width spaces and non-breaking spaces
    raw_with_zw = "Hi Mira,\u200b thanks for reaching\u00a0out.\ufeff We are happy to help."
    cleaned = DraftMessageOutput.model_validate({"message": raw_with_zw}).message
    assert cleaned == "Hi Mira, thanks for reaching out. We are happy to help."
    assert "\u200b" not in cleaned
    assert "\ufeff" not in cleaned
    assert "\u00a0" not in cleaned

    # Punctuation immediately touching a word (e.g. ?Once -> ? Once)
    raw_punctuation = "works for you?Once we have that, we can help.Thanks!"
    cleaned_punc = DraftMessageOutput.model_validate({"message": raw_punctuation}).message
    assert cleaned_punc == "works for you? Once we have that, we can help. Thanks!"

    # Token boundary repair (e.g. Oncewe -> Once we)
    raw_oncewe = "works for you? Oncewe have that, we will share availability."
    cleaned_oncewe = DraftMessageOutput.model_validate({"message": raw_oncewe}).message
    assert cleaned_oncewe == "works for you? Once we have that, we will share availability."
    assert "Oncewe" not in cleaned_oncewe

    # Multi-space collapse
    raw_spaces = "Hi Mira,    thanks   for reaching out!   "
    cleaned_spaces = DraftMessageOutput.model_validate({"message": raw_spaces}).message
    assert cleaned_spaces == "Hi Mira, thanks for reaching out!"


@pytest.mark.parametrize(
    "malformed_draft",
    [
        json.dumps({"message": ""}),
        json.dumps({"message": "    "}),
        json.dumps({"message": 12345}),
        json.dumps({"wrong_field": "Hello"}),
        json.dumps({"message": "Valid text", "extra_forbidden": True}),
        "not json at all",
    ],
)
def test_malformed_llm_draft_outputs_fallback_safely(client, monkeypatch, malformed_draft):
    """Malformed or invalid LLM draft outputs safely fall back to deterministic response."""
    from nudgeflow.services.agent import workflow

    _, follow_up = create_follow_up(client)
    stub_classifier(monkeypatch)

    llm = FakeLLM(
        extraction_payload(),
        malformed_draft,
    )
    monkeypatch.setattr(workflow, "get_llm_client", lambda: llm)

    response = client.post(
        "/agent/runs",
        json={
            "follow_up_id": follow_up["id"],
            "customer_message": "Need information please.",
        },
    )

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "awaiting_approval"
    assert data["message_extraction"]["status"] == "completed"
    assert data["draft"]["status"] == "fallback"
    assert data["draft"]["source"] == "deterministic"
    assert data["draft"]["error_code"] in {"invalid_draft_output", "draft_generation_failed"}
    assert "thanks for reaching out" in data["proposed_message"]


def test_pricing_and_availability_enquiry_drafting(client, monkeypatch):
    """Pricing and availability enquiry asks for missing service and date/time details politely."""
    from nudgeflow.services.agent import workflow

    _, follow_up = create_follow_up(client)
    stub_classifier(monkeypatch)

    customer_message = "Hi! Can you let me know your pricing and available slots next week?"
    extraction = extraction_payload(
        request_summary="Ask about pricing and availability next week",
        requested_action="request pricing and availability",
        product_or_service=None,
        date_or_time_mentioned="next week",
        missing_information=["product_or_service", "specific_date_or_time"],
    )
    draft_message = (
        "Hi Mira, thanks for reaching out! Could you let us know which service or product "
        "you’re interested in and the specific day or time next week that works for you? "
        "Once we have that, we can share pricing and availability. Thanks!"
    )

    llm = FakeLLM(
        extraction,
        json.dumps({"message": draft_message}, ensure_ascii=False),
    )
    monkeypatch.setattr(workflow, "get_llm_client", lambda: llm)

    response = client.post(
        "/agent/runs",
        json={
            "follow_up_id": follow_up["id"],
            "customer_message": customer_message,
        },
    )

    assert response.status_code == 201, response.text
    assert response.headers["content-type"] == "application/json; charset=utf-8"
    data = response.json()

    # Verify run remains in safe awaiting_approval state
    assert data["status"] == "awaiting_approval"
    assert data["approval_decision"] is None
    assert data["execution"] is None

    # Verify extraction identified missing details
    assert data["message_extraction"]["status"] == "completed"
    assert data["message_extraction"]["data"]["missing_information"] == [
        "product_or_service",
        "specific_date_or_time",
    ]

    # Verify draft output
    assert data["draft"]["status"] == "generated"
    assert data["draft"]["source"] == "llm"
    assert data["draft"]["error_code"] is None

    # Verify quality, spacing, and Unicode preservation
    proposed = data["proposed_message"]
    assert "you’re" in proposed
    assert "Once we" in proposed
    assert "Oncewe" not in proposed
    assert "which service or product" in proposed
    assert "pricing and availability" in proposed
