"""persist advisory agent intent classification results

Revision ID: d1e6fa209c37
Revises: a73c9b14d520
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d1e6fa209c37"
down_revision: Union[str, Sequence[str], None] = "a73c9b14d520"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column(
            "intent_classification_status",
            sa.String(length=20),
            server_default="not_performed",
            nullable=False,
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column("intent_classification_reason", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "agent_runs", sa.Column("predicted_intent", sa.String(length=40), nullable=True)
    )
    op.add_column("agent_runs", sa.Column("intent_confidence", sa.Float(), nullable=True))
    op.add_column(
        "agent_runs",
        sa.Column("intent_classification_error_code", sa.String(length=80), nullable=True),
    )
    op.execute(
        "UPDATE agent_runs SET intent_classification_reason = 'missing_input' "
        "WHERE intent_classification_status = 'not_performed'"
    )
    op.create_check_constraint(
        "ck_agent_runs_intent_classification_status",
        "agent_runs",
        "intent_classification_status IN ('classified', 'not_performed', 'unavailable', 'error')",
    )
    op.create_check_constraint(
        "ck_agent_runs_predicted_intent",
        "agent_runs",
        "predicted_intent IS NULL OR predicted_intent IN "
        "('booking_enquiry', 'purchase_enquiry', 'service_enquiry', "
        "'complaint_support', 'cancellation', 'other_uncertain')",
    )
    op.create_check_constraint(
        "ck_agent_runs_intent_confidence",
        "agent_runs",
        "intent_confidence IS NULL OR (intent_confidence >= 0 AND intent_confidence <= 1)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_agent_runs_intent_confidence", "agent_runs", type_="check")
    op.drop_constraint("ck_agent_runs_predicted_intent", "agent_runs", type_="check")
    op.drop_constraint(
        "ck_agent_runs_intent_classification_status", "agent_runs", type_="check"
    )
    op.drop_column("agent_runs", "intent_classification_error_code")
    op.drop_column("agent_runs", "intent_confidence")
    op.drop_column("agent_runs", "predicted_intent")
    op.drop_column("agent_runs", "intent_classification_reason")
    op.drop_column("agent_runs", "intent_classification_status")
