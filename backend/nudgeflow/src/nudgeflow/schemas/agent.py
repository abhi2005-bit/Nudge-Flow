from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

IntentClassificationStatus = Literal[
    "classified", "not_performed", "unavailable", "error"
]
IntentLabel = Literal[
    "booking_enquiry",
    "purchase_enquiry",
    "service_enquiry",
    "complaint_support",
    "cancellation",
    "other_uncertain",
]

AgentRunStatus = Literal[
    "awaiting_approval",
    "rejected",
    "executing",
    "completed",
    "failed",
    "ready_to_execute",
    "outcome_uncertain",
]


class AgentRunCreate(BaseModel):
    follow_up_id: int = Field(gt=0)
    customer_message: str | None = Field(default=None, max_length=5000)

    @field_validator("customer_message")
    @classmethod
    def validate_customer_message(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("customer_message must not be blank.")
        return value


class AgentRejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class AgentPlanResponse(BaseModel):
    follow_up_id: int
    intended_action: Literal["send_follow_up_message"]
    message: str
    tool_name: Literal["mock_messaging"]


class AgentExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tool_name: str
    status: Literal["succeeded", "failed", "uncertain"]
    result: dict[str, Any]
    error_code: str | None
    verified: bool
    executed_at: datetime
    verified_at: datetime | None


class AgentAuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    actor_user_id: int | None
    details: dict[str, Any]
    created_at: datetime


class IntentClassificationResponse(BaseModel):
    status: IntentClassificationStatus
    reason: Literal["missing_input"] | None
    intent: IntentLabel | None
    confidence: float | None = Field(default=None, ge=0, le=1)
    error_code: str | None


class CustomerMessageExtraction(BaseModel):
    """Validated, advisory facts extracted from one supplied customer message."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_summary: str | None = Field(default=None, max_length=500)
    requested_action: str | None = Field(default=None, max_length=300)
    product_or_service: str | None = Field(default=None, max_length=160)
    date_or_time_mentioned: str | None = Field(default=None, max_length=120)
    quantity: str | None = Field(default=None, max_length=100)
    budget: str | None = Field(default=None, max_length=120)
    other_details: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(
        default_factory=list, max_length=8
    )
    missing_information: list[Annotated[str, Field(min_length=1, max_length=240)]] = Field(
        default_factory=list, max_length=8
    )

    @field_validator(
        "request_summary",
        "requested_action",
        "product_or_service",
        "date_or_time_mentioned",
        "quantity",
        "budget",
        mode="before",
    )
    @classmethod
    def blank_scalar_is_unknown(cls, value: Any) -> Any:
        return None if isinstance(value, str) and not value.strip() else value


class MessageExtractionResponse(BaseModel):
    status: Literal["completed", "not_performed", "unavailable", "failed"]
    data: CustomerMessageExtraction | None
    error_code: str | None


class DraftResponse(BaseModel):
    status: Literal["generated", "fallback"]
    source: Literal["llm", "deterministic"]
    error_code: str | None


class AgentRunResponse(BaseModel):
    id: int
    follow_up_id: int
    status: AgentRunStatus
    plan: AgentPlanResponse
    tool_name: str
    proposed_message: str
    intent_classification: IntentClassificationResponse
    message_extraction: MessageExtractionResponse
    draft: DraftResponse
    approval_decision: Literal["approved", "rejected"] | None
    approval_by_user_id: int | None
    approval_at: datetime | None
    rejection_reason: str | None
    execution_lease_expires_at: datetime | None
    tool_invocation_started_at: datetime | None
    created_at: datetime
    updated_at: datetime
    execution: AgentExecutionResponse | None
    audit: list[AgentAuditEventResponse]
