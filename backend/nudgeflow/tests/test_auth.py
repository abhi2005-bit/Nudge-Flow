
from datetime import UTC, datetime, timedelta

import jwt

from nudgeflow.config import settings
from nudgeflow.tokens import ALGORITHM


def test_register_user_success(anonymous_client):
    response = anonymous_client.post(
        "/auth/register",
        json={
            "email": "owner@example.com",
            "password": "Example-Password-123!",
        },
    )

    assert response.status_code == 201

    data = response.json()
    assert data["email"] == "owner@example.com"
    assert "id" in data
    assert "created_at" in data
    assert "password" not in data
    assert "hashed_password" not in data


def test_register_user_duplicate_email(anonymous_client):
    payload = {
        "email": "owner@example.com",
        "password": "Example-Password-123!",
    }

    first_response = anonymous_client.post("/auth/register", json=payload)
    second_response = anonymous_client.post("/auth/register", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409


def test_register_user_invalid_email(anonymous_client):
    response = anonymous_client.post(
        "/auth/register",
        json={
            "email": "not-an-email",
            "password": "Example-Password-123!",
        },
    )

    assert response.status_code == 422


def test_register_user_short_password(anonymous_client):
    response = anonymous_client.post(
        "/auth/register",
        json={
            "email": "owner@example.com",
            "password": "short",
        },
    )

    assert response.status_code == 422


def test_login_success_returns_bearer_token(anonymous_client):
    payload = {"email": "login@example.com", "password": "Test-password-123!"}
    assert anonymous_client.post("/auth/register", json=payload).status_code == 201

    response = anonymous_client.post("/auth/login", json=payload)

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]


def test_login_uses_same_error_for_unknown_email_and_wrong_password(anonymous_client):
    payload = {"email": "login@example.com", "password": "Test-password-123!"}
    assert anonymous_client.post("/auth/register", json=payload).status_code == 201

    wrong_password = anonymous_client.post(
        "/auth/login",
        json={"email": payload["email"], "password": "Wrong-password-123!"},
    )
    unknown_email = anonymous_client.post(
        "/auth/login",
        json={"email": "unknown@example.com", "password": payload["password"]},
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.headers["www-authenticate"] == "Bearer"


def test_crm_routes_reject_missing_and_invalid_tokens(anonymous_client):
    assert anonymous_client.get("/contacts").status_code == 401
    assert anonymous_client.get(
        "/follow-ups", headers={"Authorization": "Bearer malformed"}
    ).status_code == 401
    assert anonymous_client.get(
        "/contacts", headers={"Authorization": "Basic abc"}
    ).status_code == 401


def test_crm_routes_reject_expired_tokens(anonymous_client):
    now = datetime.now(UTC)
    expired_token = jwt.encode(
        {
            "sub": "1",
            "iat": now - timedelta(minutes=10),
            "exp": now - timedelta(minutes=5),
        },
        settings.jwt_secret_key.get_secret_value(),
        algorithm=ALGORITHM,
    )
    response = anonymous_client.get(
        "/contacts",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401


def test_crm_routes_reject_token_for_deleted_or_unknown_user(anonymous_client):
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "999999999",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        settings.jwt_secret_key.get_secret_value(),
        algorithm=ALGORITHM,
    )
    response = anonymous_client.get(
        "/contacts", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
