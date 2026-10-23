"""Opt-in integration test for the complete schema chain on disposable PostgreSQL."""

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
LATEST_REVISION = "f6b7d3e2a910"
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
        assert {"agent_runs", "agent_executions", "agent_audit_events"}.issubset(
            set(inspector.get_table_names())
        )
        run_columns = {column["name"] for column in inspector.get_columns("agent_runs")}
        assert {
            "execution_token",
            "execution_lease_expires_at",
            "tool_invocation_started_at",
            "intent_classification_status",
            "intent_classification_reason",
            "predicted_intent",
            "intent_confidence",
            "intent_classification_error_code",
            "message_extraction_status",
            "message_extraction_json",
            "message_extraction_error_code",
            "draft_status",
            "draft_source",
            "draft_error_code",
        }.issubset(run_columns)
        run_checks = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("agent_runs")
        }
        assert {
            "ck_agent_runs_intent_classification_status",
            "ck_agent_runs_predicted_intent",
            "ck_agent_runs_intent_confidence",
            "ck_agent_runs_message_extraction_status",
            "ck_agent_runs_message_extraction_data",
            "ck_agent_runs_draft_status",
            "ck_agent_runs_draft_source",
            "ck_agent_runs_draft_status_source",
        }.issubset(run_checks)
        assert not any(
            "intent" in (index["name"] or "")
            for index in inspector.get_indexes("agent_runs")
        )
        assert any(
            constraint["name"] == "uq_agent_runs_execution_token"
            for constraint in inspector.get_unique_constraints("agent_runs")
        )
        assert any(
            constraint["name"] == "uq_agent_executions_tenant_run"
            for constraint in inspector.get_unique_constraints("agent_executions")
        )
        assert any(
            index["name"] == "ix_agent_runs_status_lease"
            for index in inspector.get_indexes("agent_runs")
        )
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
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == LATEST_REVISION

        # Exercise the extraction/draft migration's own downgrade and re-upgrade.
        command.downgrade(config, "d1e6fa209c37")
        downgraded_columns = {
            column["name"] for column in inspect(engine).get_columns("agent_runs")
        }
        assert not {
            "message_extraction_status",
            "message_extraction_json",
            "message_extraction_error_code",
            "draft_status",
            "draft_source",
            "draft_error_code",
        }.intersection(downgraded_columns)
        assert "intent_classification_status" in downgraded_columns
        assert not {
            "ck_agent_runs_message_extraction_status",
            "ck_agent_runs_message_extraction_data",
            "ck_agent_runs_draft_status",
            "ck_agent_runs_draft_source",
            "ck_agent_runs_draft_status_source",
        }.intersection(
            constraint["name"]
            for constraint in inspect(engine).get_check_constraints("agent_runs")
        )
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == LATEST_REVISION

        # Exercise the classification migration's own downgrade and re-upgrade.
        command.downgrade(config, "a73c9b14d520")
        downgraded_columns = {
            column["name"] for column in inspect(engine).get_columns("agent_runs")
        }
        assert "intent_classification_status" not in downgraded_columns
        assert not {
            "ck_agent_runs_intent_classification_status",
            "ck_agent_runs_predicted_intent",
            "ck_agent_runs_intent_confidence",
        }.intersection(
            constraint["name"]
            for constraint in inspect(engine).get_check_constraints("agent_runs")
        )
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == LATEST_REVISION

        # Rewind both agent revisions, then simulate a run left in the old
        # executing state before recovery and classification markers existed.
        command.downgrade(config, "8b37f4c1a9d2")
        with engine.begin() as connection:
            tenant_id = connection.scalar(
                text("INSERT INTO tenants (name) VALUES ('Recovery migration test') RETURNING id")
            )
            contact_id = connection.scalar(
                text(
                    "INSERT INTO contacts (tenant_id, name, phone_number) "
                    "VALUES (:tenant_id, 'Recovery contact', '+15550101003') RETURNING id"
                ),
                {"tenant_id": tenant_id},
            )
            follow_up_id = connection.scalar(
                text(
                    "INSERT INTO follow_ups (tenant_id, contact_id, title, due_at) "
                    "VALUES (:tenant_id, :contact_id, 'Recovery task', :due_at) RETURNING id"
                ),
                {
                    "tenant_id": tenant_id,
                    "contact_id": contact_id,
                    "due_at": datetime.now(timezone.utc),
                },
            )
            old_updated_at = datetime.now(timezone.utc)
            old_run_id = connection.scalar(
                text(
                    "INSERT INTO agent_runs "
                    "(tenant_id, follow_up_id, intended_action, tool_name, proposed_message, "
                    "status, approval_decision, updated_at) "
                    "VALUES (:tenant_id, :follow_up_id, 'send_follow_up_message', "
                    "'mock_messaging', 'draft', 'executing', 'approved', :updated_at) RETURNING id"
                ),
                {
                    "tenant_id": tenant_id,
                    "follow_up_id": follow_up_id,
                    "updated_at": old_updated_at,
                },
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            marker = connection.scalar(
                text(
                    "SELECT tool_invocation_started_at FROM agent_runs WHERE id = :run_id"
                ),
                {"run_id": old_run_id},
            )
            assert marker is not None
            assert marker.astimezone(timezone.utc) == old_updated_at.astimezone(
                timezone.utc
            )
            classification = connection.execute(
                text(
                    "SELECT intent_classification_status, intent_classification_reason, "
                    "predicted_intent, intent_confidence "
                    "FROM agent_runs WHERE id = :run_id"
                ),
                {"run_id": old_run_id},
            ).one()
            assert tuple(classification) == (
                "not_performed",
                "missing_input",
                None,
                None,
            )
            extraction_and_draft = connection.execute(
                text(
                    "SELECT message_extraction_status, message_extraction_json, "
                    "message_extraction_error_code, draft_status, draft_source "
                    "FROM agent_runs WHERE id = :run_id"
                ),
                {"run_id": old_run_id},
            ).one()
            assert tuple(extraction_and_draft) == (
                "not_performed",
                None,
                "source_message_not_stored",
                "fallback",
                "deterministic",
            )
        # Remove only this fixture row from the disposable DB so the migration's
        # downgrade guard can also verify a safe rollback path.
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM agent_runs WHERE id = :run_id"),
                {"run_id": old_run_id},
            )

        # Rewind through the new agent revisions to the tenant migration parent,
        # then reproduce its exact legacy schema and seed owned/unowned records.
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

        # The complete revision chain must leave the disposable DB at the latest head.
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == LATEST_REVISION

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
