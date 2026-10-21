"""add business tenants and tenant-scoped CRM records

Revision ID: 64a2cdd93a10
Revises: b6c81e94d172
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "64a2cdd93a10"
down_revision: Union[str, Sequence[str], None] = "b6c81e94d172"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column("users", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("tenant_role", sa.String(20), nullable=True))
    op.add_column("contacts", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.add_column("follow_ups", sa.Column("tenant_id", sa.Integer(), nullable=True))

    bind = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("tenant_id", sa.Integer()),
        sa.column("tenant_role", sa.String(20)),
    )
    contacts = sa.table(
        "contacts",
        sa.column("id", sa.Integer()),
        sa.column("owner_id", sa.Integer()),
        sa.column("tenant_id", sa.Integer()),
    )
    follow_ups = sa.table(
        "follow_ups",
        sa.column("contact_id", sa.Integer()),
        sa.column("tenant_id", sa.Integer()),
    )
    tenants = sa.table(
        "tenants",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.String(120)),
    )

    # Existing accounts get their own workspace. There was no invitation or
    # shared-workspace flow before this migration, so no membership is inferred.
    user_ids = bind.execute(sa.select(users.c.id).order_by(users.c.id)).scalars()
    for user_id in user_ids:
        tenant_id = bind.execute(
            tenants.insert()
            .values(name=f"Business workspace {user_id}")
            .returning(tenants.c.id)
        ).scalar_one()
        bind.execute(
            users.update()
            .where(users.c.id == user_id)
            .values(tenant_id=tenant_id, tenant_role="owner")
        )
        bind.execute(
            contacts.update()
            .where(contacts.c.owner_id == user_id)
            .values(tenant_id=tenant_id)
        )

    # Ownerless contacts have no reliable tenant assignment. Keep them intact
    # in an isolated quarantine workspace with no users attached to it.
    has_unassigned_contacts = bind.execute(
        sa.select(contacts.c.id)
        .where(contacts.c.tenant_id.is_(None))
        .limit(1)
    ).first()
    if has_unassigned_contacts:
        quarantine_id = bind.execute(
            tenants.insert()
            .values(name="Unassigned legacy records (quarantined)")
            .returning(tenants.c.id)
        ).scalar_one()
        bind.execute(
            contacts.update()
            .where(contacts.c.tenant_id.is_(None))
            .values(tenant_id=quarantine_id)
        )

    # Tasks inherit exactly the tenant of their existing contact.
    bind.execute(
        follow_ups.update().values(
            tenant_id=(
                sa.select(contacts.c.tenant_id)
                .where(contacts.c.id == follow_ups.c.contact_id)
                .scalar_subquery()
            )
        )
    )

    if bind.execute(
        sa.select(contacts.c.id).where(contacts.c.tenant_id.is_(None)).limit(1)
    ).first():
        raise RuntimeError("A contact could not be assigned to a tenant.")
    if bind.execute(
        sa.select(follow_ups.c.contact_id)
        .where(follow_ups.c.tenant_id.is_(None))
        .limit(1)
    ).first():
        raise RuntimeError("A follow-up could not inherit its contact tenant.")

    op.alter_column("users", "tenant_id", nullable=False)
    op.alter_column(
        "users",
        "tenant_role",
        nullable=False,
        server_default="owner",
    )
    op.alter_column("contacts", "tenant_id", nullable=False)
    op.alter_column("follow_ups", "tenant_id", nullable=False)

    op.create_check_constraint(
        "ck_users_tenant_role",
        "users",
        "tenant_role IN ('owner', 'member')",
    )
    op.create_foreign_key(
        "fk_users_tenant_id_tenants",
        "users",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_contacts_tenant_id_tenants",
        "contacts",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_follow_ups_tenant_id_tenants",
        "follow_ups",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_unique_constraint(
        "uq_contacts_tenant_id_id",
        "contacts",
        ["tenant_id", "id"],
    )
    op.create_foreign_key(
        "fk_follow_ups_tenant_contact",
        "follow_ups",
        "contacts",
        ["tenant_id", "contact_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )

    # Phone uniqueness is tenant-scoped so one business cannot learn whether
    # another tenant already has a contact with that number.
    op.drop_index("ix_contacts_phone_number", table_name="contacts")
    op.create_unique_constraint(
        "uq_contacts_tenant_phone",
        "contacts",
        ["tenant_id", "phone_number"],
    )

    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.create_index("ix_contacts_tenant_id", "contacts", ["tenant_id"])
    op.create_index("ix_follow_ups_tenant_id", "follow_ups", ["tenant_id"])


def downgrade() -> None:
    bind = op.get_bind()
    contacts = sa.table(
        "contacts",
        sa.column("phone_number", sa.String(30)),
    )
    duplicate_phone = bind.execute(
        sa.select(contacts.c.phone_number)
        .group_by(contacts.c.phone_number)
        .having(sa.func.count() > 1)
        .limit(1)
    ).first()
    if duplicate_phone:
        raise RuntimeError(
            "Cannot downgrade tenant-scoped phone uniqueness while duplicate "
            "phone numbers exist across tenants. Resolve duplicates first."
        )

    op.drop_index("ix_follow_ups_tenant_id", table_name="follow_ups")
    op.drop_index("ix_contacts_tenant_id", table_name="contacts")
    op.drop_index("ix_users_tenant_id", table_name="users")

    op.drop_constraint(
        "fk_follow_ups_tenant_contact", "follow_ups", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_follow_ups_tenant_id_tenants", "follow_ups", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_contacts_tenant_id_tenants", "contacts", type_="foreignkey"
    )
    op.drop_constraint("fk_users_tenant_id_tenants", "users", type_="foreignkey")
    op.drop_constraint("ck_users_tenant_role", "users", type_="check")
    op.drop_constraint("uq_contacts_tenant_phone", "contacts", type_="unique")
    op.drop_constraint("uq_contacts_tenant_id_id", "contacts", type_="unique")

    op.create_index(
        "ix_contacts_phone_number",
        "contacts",
        ["phone_number"],
        unique=True,
    )
    op.drop_column("follow_ups", "tenant_id")
    op.drop_column("contacts", "tenant_id")
    op.drop_column("users", "tenant_role")
    op.drop_column("users", "tenant_id")
    op.drop_table("tenants")
