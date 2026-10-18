"""limit follow-up status values

Revision ID: c724d8ea1290
Revises: 93c2db250efb
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c724d8ea1290"
down_revision: Union[str, Sequence[str], None] = "93c2db250efb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_follow_ups_status",
        "follow_ups",
        "status IN ('pending', 'completed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_follow_ups_status", "follow_ups", type_="check")
