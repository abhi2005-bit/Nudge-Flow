import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from nudgeflow.database import Base, get_db
from nudgeflow.config import settings
from nudgeflow.main import app
from nudgeflow.models import Contact, FollowUp  # noqa: F401


@pytest.fixture(autouse=True)
def test_jwt_secret(monkeypatch):
    monkeypatch.setattr(
        settings,
        "jwt_secret_key",
        SecretStr("local-test-secret-that-is-at-least-32-characters"),
    )
    monkeypatch.setattr(settings, "whatsapp_enabled", False)


@pytest.fixture
def test_engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def db_session(test_engine):
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def anonymous_client(db_session):
    def override_get_db():
        yield db_session

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


@pytest.fixture
def client(anonymous_client):
    registration = anonymous_client.post(
        "/auth/register",
        json={"email": "owner@example.com", "password": "Test-password-123!"},
    )
    assert registration.status_code == 201, registration.text
    login = anonymous_client.post(
        "/auth/login",
        json={"email": "owner@example.com", "password": "Test-password-123!"},
    )
    assert login.status_code == 200, login.text
    anonymous_client.headers.update(
        {"Authorization": f"Bearer {login.json()['access_token']}"}
    )
    return anonymous_client
