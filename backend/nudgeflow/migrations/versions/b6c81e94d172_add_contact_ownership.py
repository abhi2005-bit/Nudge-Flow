"""add nullable contact ownership

Revision ID: b6c81e94d172
Revises: f30ae02c5926
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b6c81e94d172"
down_revision: Union[str, Sequence[str], None] = "f30ae02c5926"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Keep historical contacts unassigned until an explicit owner is chosen.
    op.add_column(
        "contacts",
        sa.Column("owner_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_contacts_owner_id_users",
        "contacts",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_contacts_owner_id", "contacts", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_contacts_owner_id", table_name="contacts")
    op.drop_constraint("fk_contacts_owner_id_users", "contacts", type_="foreignkey")
    op.drop_column("contacts", "owner_id")
