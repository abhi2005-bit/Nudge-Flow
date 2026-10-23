"""add persisted approval-gated agent workflow

Revision ID: 8b37f4c1a9d2
Revises: 64a2cdd93a10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "8b37f4c1a9d2"
down_revision: Union[str, Sequence[str], None] = "64a2cdd93a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_follow_ups_tenant_id_id", "follow_ups", ["tenant_id", "id"]
    )
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("follow_up_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("intended_action", sa.String(length=80), nullable=False),
        sa.Column("tool_name", sa.String(length=80), nullable=False),
        sa.Column("proposed_message", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(length=30), server_default="awaiting_approval", nullable=False
        ),
        sa.Column("approval_decision", sa.String(length=20), nullable=True),
        sa.Column("approval_by_user_id", sa.Integer(), nullable=True),
        sa.Column("approval_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('awaiting_approval', 'rejected', 'executing', 'completed', 'failed')",
            name="ck_agent_runs_status",
        ),
        sa.CheckConstraint(
            "approval_decision IS NULL OR approval_decision IN ('approved', 'rejected')",
            name="ck_agent_runs_approval_decision",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approval_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "follow_up_id"],
            ["follow_ups.tenant_id", "follow_ups.id"],
            name="fk_agent_runs_tenant_follow_up",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_agent_runs_tenant_id_id"),
    )
    op.create_index("ix_agent_runs_tenant_id", "agent_runs", ["tenant_id"])
    op.create_index("ix_agent_runs_follow_up_id", "agent_runs", ["follow_up_id"])

    op.create_table(
        "agent_executions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("verified", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "executed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed')", name="ck_agent_executions_status"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            name="fk_agent_executions_tenant_run",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "run_id", name="uq_agent_executions_tenant_run"),
    )
    op.create_index("ix_agent_executions_tenant_id", "agent_executions", ["tenant_id"])
    op.create_index("ix_agent_executions_run_id", "agent_executions", ["run_id"])

    op.create_table(
        "agent_audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["agent_runs.tenant_id", "agent_runs.id"],
            name="fk_agent_audit_events_tenant_run",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_audit_events_tenant_id", "agent_audit_events", ["tenant_id"])
    op.create_index("ix_agent_audit_events_run_id", "agent_audit_events", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_audit_events_run_id", table_name="agent_audit_events")
    op.drop_index("ix_agent_audit_events_tenant_id", table_name="agent_audit_events")
    op.drop_table("agent_audit_events")
    op.drop_index("ix_agent_executions_run_id", table_name="agent_executions")
    op.drop_index("ix_agent_executions_tenant_id", table_name="agent_executions")
    op.drop_table("agent_executions")
    op.drop_index("ix_agent_runs_follow_up_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_tenant_id", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_constraint(
        "uq_follow_ups_tenant_id_id", "follow_ups", type_="unique"
    )
