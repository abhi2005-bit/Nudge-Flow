"""Persisted agent workflow records."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Index,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from nudgeflow.database import Base
from nudgeflow.models.types import UTCDateTime


class AgentRun(Base):
    """A tenant-scoped, approval-gated deterministic agent run."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('awaiting_approval', 'rejected', 'executing', 'completed', 'failed', 'ready_to_execute', 'outcome_uncertain')",
            name="ck_agent_runs_status",
        ),
        CheckConstraint(
            "approval_decision IS NULL OR approval_decision IN ('approved', 'rejected')",
            name="ck_agent_runs_approval_decision",
        ),
        CheckConstraint(
            "intent_classification_status IN ('classified', 'not_performed', 'unavailable', 'error')",
            name="ck_agent_runs_intent_classification_status",
        ),
        CheckConstraint(
            "predicted_intent IS NULL OR predicted_intent IN "
            "('booking_enquiry', 'purchase_enquiry', 'service_enquiry', "
            "'complaint_support', 'cancellation', 'other_uncertain')",
            name="ck_agent_runs_predicted_intent",
        ),
        CheckConstraint(
            "intent_confidence IS NULL OR (intent_confidence >= 0 AND intent_confidence <= 1)",
            name="ck_agent_runs_intent_confidence",
        ),
        CheckConstraint(
            "message_extraction_status IN ('completed', 'not_performed', 'unavailable', 'failed')",
            name="ck_agent_runs_message_extraction_status",
        ),
        CheckConstraint(
            "(message_extraction_status = 'completed' AND message_extraction_json IS NOT NULL) "
            "OR (message_extraction_status <> 'completed' AND message_extraction_json IS NULL)",
            name="ck_agent_runs_message_extraction_data",
        ),
        CheckConstraint(
            "draft_status IN ('generated', 'fallback')",
            name="ck_agent_runs_draft_status",
        ),
        CheckConstraint(
            "draft_source IN ('llm', 'deterministic')",
            name="ck_agent_runs_draft_source",
        ),
        CheckConstraint(
            "(draft_status = 'generated' AND draft_source = 'llm') OR "
            "(draft_status = 'fallback' AND draft_source = 'deterministic')",
            name="ck_agent_runs_draft_status_source",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_agent_runs_tenant_id_id"),
        UniqueConstraint("execution_token", name="uq_agent_runs_execution_token"),
        Index("ix_agent_runs_status_lease", "status", "execution_lease_expires_at"),
        ForeignKeyConstraint(
            ["tenant_id", "follow_up_id"],
            ["follow_ups.tenant_id", "follow_ups.id"],
            name="fk_agent_runs_tenant_follow_up",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    follow_up_id: Mapped[int] = mapped_column(nullable=False, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    intended_action: Mapped[str] = mapped_column(String(80), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(80), nullable=False)
    proposed_message: Mapped[str] = mapped_column(Text, nullable=False)
    intent_classification_status: Mapped[str] = mapped_column(
        String(20), default="not_performed", server_default="not_performed", nullable=False
    )
    intent_classification_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    predicted_intent: Mapped[str | None] = mapped_column(String(40), nullable=True)
    intent_confidence: Mapped[float | None] = mapped_column(nullable=True)
    intent_classification_error_code: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )
    message_extraction_status: Mapped[str] = mapped_column(
        String(20), default="not_performed", server_default="not_performed", nullable=False
    )
    message_extraction_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_extraction_error_code: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )
    draft_status: Mapped[str] = mapped_column(
        String(20), default="fallback", server_default="fallback", nullable=False
    )
    draft_source: Mapped[str] = mapped_column(
        String(20), default="deterministic", server_default="deterministic", nullable=False
    )
    draft_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30),
        default="awaiting_approval",
        server_default="awaiting_approval",
        nullable=False,
    )
    approval_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    approval_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approval_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    execution_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    execution_lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    tool_invocation_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AgentExecution(Base):
    """The durable result from the allow-listed mock messaging tool."""

    __tablename__ = "agent_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('succeeded', 'failed', 'uncertain')", name="ck_agent_executions_status"
        ),
        UniqueConstraint(
            "tenant_id", "run_id", name="uq_agent_executions_tenant_run"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            name="fk_agent_executions_tenant_run",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    run_id: Mapped[int] = mapped_column(nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    executed_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class AgentAuditEvent(Base):
    """Append-only workflow transitions; details exclude message content."""

    __tablename__ = "agent_audit_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            name="fk_agent_audit_events_tenant_run",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    run_id: Mapped[int] = mapped_column(nullable=False, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
