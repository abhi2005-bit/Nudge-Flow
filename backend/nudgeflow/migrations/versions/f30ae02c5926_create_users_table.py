
"""create users table

Revision ID: f30ae02c5926
Revises: c724d8ea1290
Create Date: 2026-10-18 20:48:10.612413
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from nudgeflow.models.types import UTCDateTime


# revision identifiers, used by Alembic.
revision: str = "f30ae02c5926"
down_revision: Union[str, Sequence[str], None] = "c724d8ea1290"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the users table."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            UTCDateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_users_email"),
        "users",
        ["email"],
        unique=True,
    )


def downgrade() -> None:
    """Drop the users table."""
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
