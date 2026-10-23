"""add execution leases and recoverable agent run states

Revision ID: a73c9b14d520
Revises: 8b37f4c1a9d2
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a73c9b14d520"
down_revision: Union[str, Sequence[str], None] = "8b37f4c1a9d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_RUN_STATES = "'awaiting_approval', 'rejected', 'executing', 'completed', 'failed'"
NEW_RUN_STATES = (
    "'awaiting_approval', 'rejected', 'executing', 'completed', 'failed', "
    "'ready_to_execute', 'outcome_uncertain'"
)


def upgrade() -> None:
    op.drop_constraint("ck_agent_runs_status", "agent_runs", type_="check")
    op.create_check_constraint(
        "ck_agent_runs_status", "agent_runs", f"status IN ({NEW_RUN_STATES})"
    )
    op.add_column("agent_runs", sa.Column("execution_token", sa.String(length=36), nullable=True))
    op.add_column(
        "agent_runs",
        sa.Column("execution_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_runs",
        sa.Column("tool_invocation_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Existing executing runs predate the invocation marker. They might already
    # have reached the tool, so conservatively classify them as uncertain.
    op.execute(
        "UPDATE agent_runs SET tool_invocation_started_at = updated_at "
        "WHERE status = 'executing'"
    )
    op.create_unique_constraint(
        "uq_agent_runs_execution_token", "agent_runs", ["execution_token"]
    )
    op.create_index(
        "ix_agent_runs_status_lease",
        "agent_runs",
        ["status", "execution_lease_expires_at"],
    )

    op.drop_constraint("ck_agent_executions_status", "agent_executions", type_="check")
    op.create_check_constraint(
        "ck_agent_executions_status",
        "agent_executions",
        "status IN ('succeeded', 'failed', 'uncertain')",
    )


def downgrade() -> None:
    bind = op.get_bind()
    pending = bind.execute(
        sa.text(
            "SELECT count(*) FROM agent_runs "
            "WHERE status IN ('executing', 'ready_to_execute', 'outcome_uncertain')"
        )
    ).scalar_one()
    if pending:
        raise RuntimeError(
            "Cannot downgrade while executing, recoverable, or uncertain runs exist; "
            "reconcile them first."
        )
    uncertain_executions = bind.execute(
        sa.text("SELECT count(*) FROM agent_executions WHERE status = 'uncertain'")
    ).scalar_one()
    if uncertain_executions:
        raise RuntimeError(
            "Cannot downgrade while uncertain execution outcomes exist; "
            "reconcile them first."
        )

    op.drop_constraint("ck_agent_executions_status", "agent_executions", type_="check")
    op.create_check_constraint(
        "ck_agent_executions_status",
        "agent_executions",
        "status IN ('succeeded', 'failed')",
    )
    op.drop_index("ix_agent_runs_status_lease", table_name="agent_runs")
    op.drop_constraint("uq_agent_runs_execution_token", "agent_runs", type_="unique")
    op.drop_column("agent_runs", "tool_invocation_started_at")
    op.drop_column("agent_runs", "execution_lease_expires_at")
    op.drop_column("agent_runs", "execution_token")
    op.drop_constraint("ck_agent_runs_status", "agent_runs", type_="check")
    op.create_check_constraint(
        "ck_agent_runs_status", "agent_runs", f"status IN ({OLD_RUN_STATES})"
    )
