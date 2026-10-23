"""persist validated customer-message extraction and draft provenance

Revision ID: f6b7d3e2a910
Revises: d1e6fa209c37
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6b7d3e2a910"
down_revision: Union[str, Sequence[str], None] = "d1e6fa209c37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column(
            "message_extraction_status",
            sa.String(length=20),
            server_default="not_performed",
            nullable=False,
        ),
    )
    op.add_column(
        "agent_runs", sa.Column("message_extraction_json", sa.Text(), nullable=True)
    )
    op.add_column(
        "agent_runs",
        sa.Column("message_extraction_error_code", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "agent_runs",
        sa.Column(
            "draft_status",
            sa.String(length=20),
            server_default="fallback",
            nullable=False,
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column(
            "draft_source",
            sa.String(length=20),
            server_default="deterministic",
            nullable=False,
        ),
    )
    op.add_column("agent_runs", sa.Column("draft_error_code", sa.String(length=80), nullable=True))
    # Historical runs have no stored customer message to extract from. Their drafts
    # were created deterministically by the existing workflow.
    op.execute(
        "UPDATE agent_runs SET message_extraction_error_code = 'source_message_not_stored' "
        "WHERE message_extraction_status = 'not_performed'"
    )
    op.create_check_constraint(
        "ck_agent_runs_message_extraction_status",
        "agent_runs",
        "message_extraction_status IN ('completed', 'not_performed', 'unavailable', 'failed')",
    )
    op.create_check_constraint(
        "ck_agent_runs_message_extraction_data",
        "agent_runs",
        "(message_extraction_status = 'completed' AND message_extraction_json IS NOT NULL) "
        "OR (message_extraction_status <> 'completed' AND message_extraction_json IS NULL)",
    )
    op.create_check_constraint(
        "ck_agent_runs_draft_status",
        "agent_runs",
        "draft_status IN ('generated', 'fallback')",
    )
    op.create_check_constraint(
        "ck_agent_runs_draft_source",
        "agent_runs",
        "draft_source IN ('llm', 'deterministic')",
    )
    op.create_check_constraint(
        "ck_agent_runs_draft_status_source",
        "agent_runs",
        "(draft_status = 'generated' AND draft_source = 'llm') OR "
        "(draft_status = 'fallback' AND draft_source = 'deterministic')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_agent_runs_draft_status_source", "agent_runs", type_="check")
    op.drop_constraint("ck_agent_runs_draft_source", "agent_runs", type_="check")
    op.drop_constraint("ck_agent_runs_draft_status", "agent_runs", type_="check")
    op.drop_constraint(
        "ck_agent_runs_message_extraction_data", "agent_runs", type_="check"
    )
    op.drop_constraint(
        "ck_agent_runs_message_extraction_status", "agent_runs", type_="check"
    )
    op.drop_column("agent_runs", "draft_error_code")
    op.drop_column("agent_runs", "draft_source")
    op.drop_column("agent_runs", "draft_status")
    op.drop_column("agent_runs", "message_extraction_error_code")
    op.drop_column("agent_runs", "message_extraction_json")
    op.drop_column("agent_runs", "message_extraction_status")
