"""Opt-in integration test for the tenant migration on a disposable PostgreSQL DB."""

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from nudgeflow.config import settings


MIGRATION_TEST_URL = os.environ.get("NUDGEFLOW_MIGRATION_TEST_URL")
TENANT_REVISION = "64a2cdd93a10"
PRE_TENANT_REVISION = "b6c81e94d172"


@pytest.mark.skipif(
    not MIGRATION_TEST_URL,
    reason="set NUDGEFLOW_MIGRATION_TEST_URL to a disposable empty PostgreSQL database",
)
def test_empty_upgrade_and_legacy_backfill_on_disposable_postgres(monkeypatch):
    url = make_url(MIGRATION_TEST_URL)
    if not url.drivername.startswith("postgresql"):
        pytest.fail("migration integration URL must use PostgreSQL")
    if url.host not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("migration integration URL must target a loopback host")
    if not (url.database or "").startswith("nudgeflow_test_"):
        pytest.fail("database name must start with nudgeflow_test_")

    monkeypatch.setattr(settings, "database_url", url.render_as_string(hide_password=False))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    engine = create_engine(url)
    try:
        if inspect(engine).get_table_names():
            pytest.fail("migration integration database must be empty before this test")

        # Exercise the complete chain starting from no application tables.
        command.upgrade(config, "head")
        inspector = inspect(engine)
        assert inspector.get_table_names()
        assert {"tenant_id", "tenant_role"}.issubset(
            {column["name"] for column in inspector.get_columns("users")}
        )
        assert "tenant_id" in {
            column["name"] for column in inspector.get_columns("contacts")
        }
        assert "tenant_id" in {
            column["name"] for column in inspector.get_columns("follow_ups")
        }
        assert any(
            foreign_key["constrained_columns"] == ["tenant_id"]
            and foreign_key["referred_table"] == "tenants"
            for foreign_key in inspector.get_foreign_keys("contacts")
        )
        assert any(
            foreign_key["constrained_columns"] == ["tenant_id", "contact_id"]
            and foreign_key["referred_table"] == "contacts"
            and foreign_key["referred_columns"] == ["tenant_id", "id"]
            for foreign_key in inspector.get_foreign_keys("follow_ups")
        )
        assert any(
            constraint["name"] == "uq_contacts_tenant_phone"
            for constraint in inspector.get_unique_constraints("contacts")
        )
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == TENANT_REVISION

        # Rewind only the tenant revision, reproduce its exact parent schema,
        # and seed one owned plus one ownerless contact and their tasks.
        command.downgrade(config, PRE_TENANT_REVISION)
        with engine.begin() as connection:
            user_id = connection.scalar(
                text(
                    "INSERT INTO users (email, hashed_password) "
                    "VALUES ('migration-owner@example.test', 'not-a-real-hash') "
                    "RETURNING id"
                )
            )
            owned_contact_id = connection.scalar(
                text(
                    "INSERT INTO contacts (name, phone_number, owner_id) "
                    "VALUES ('Owned legacy', '+15550101001', :owner_id) "
                    "RETURNING id"
                ),
                {"owner_id": user_id},
            )
            unassigned_contact_id = connection.scalar(
                text(
                    "INSERT INTO contacts (name, phone_number, owner_id) "
                    "VALUES ('Unassigned legacy', '+15550101002', NULL) "
                    "RETURNING id"
                )
            )
            owned_task_id = connection.scalar(
                text(
                    "INSERT INTO follow_ups (contact_id, title, due_at) "
                    "VALUES (:contact_id, 'Owned legacy task', :due_at) "
                    "RETURNING id"
                ),
                {
                    "contact_id": owned_contact_id,
                    "due_at": datetime.now(timezone.utc),
                },
            )
            unassigned_task_id = connection.scalar(
                text(
                    "INSERT INTO follow_ups (contact_id, title, due_at) "
                    "VALUES (:contact_id, 'Unassigned legacy task', :due_at) "
                    "RETURNING id"
                ),
                {
                    "contact_id": unassigned_contact_id,
                    "due_at": datetime.now(timezone.utc),
                },
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            user_tenant_id = connection.scalar(
                text("SELECT tenant_id FROM users WHERE id = :id"), {"id": user_id}
            )
            assert connection.scalar(
                text("SELECT tenant_role FROM users WHERE id = :id"), {"id": user_id}
            ) == "owner"
            owned_tenant_id = connection.scalar(
                text("SELECT tenant_id FROM contacts WHERE id = :id"),
                {"id": owned_contact_id},
            )
            quarantine_tenant_id = connection.scalar(
                text("SELECT tenant_id FROM contacts WHERE id = :id"),
                {"id": unassigned_contact_id},
            )
            assert owned_tenant_id == user_tenant_id
            assert quarantine_tenant_id != user_tenant_id
            assert connection.scalar(
                text("SELECT tenant_id FROM follow_ups WHERE id = :id"),
                {"id": owned_task_id},
            ) == owned_tenant_id
            assert connection.scalar(
                text("SELECT tenant_id FROM follow_ups WHERE id = :id"),
                {"id": unassigned_task_id},
            ) == quarantine_tenant_id
            assert connection.scalar(
                text("SELECT count(*) FROM users WHERE tenant_id = :id"),
                {"id": quarantine_tenant_id},
            ) == 0

        # PostgreSQL itself must reject a task whose tenant and contact disagree.
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO follow_ups "
                        "(tenant_id, contact_id, title, due_at) "
                        "VALUES (:tenant_id, :contact_id, 'Cross-tenant task', :due_at)"
                    ),
                    {
                        "tenant_id": user_tenant_id,
                        "contact_id": unassigned_contact_id,
                        "due_at": datetime.now(timezone.utc),
                    },
                )
    finally:
        engine.dispose()
