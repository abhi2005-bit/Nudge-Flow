
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from nudgeflow.database import engine, get_db
from nudgeflow.main import app


@pytest.fixture
def client():
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        session.close()
        transaction.rollback()
        connection.close()


def unique_phone_number():
    return f"+91{uuid.uuid4().int % 10**10:010d}"


def test_get_contact_by_id(client):
    phone_number = unique_phone_number()

    create_response = client.post(
        "/contacts",
        json={
            "name": "Get Contact Test",
            "phone_number": phone_number,
        },
    )
    assert create_response.status_code == 201, create_response.text

    contact_id = create_response.json()["id"]
    response = client.get(f"/contacts/{contact_id}")

    assert response.status_code == 200, response.text
    assert response.json()["id"] == contact_id
    assert response.json()["name"] == "Get Contact Test"
    assert response.json()["phone_number"] == phone_number


def test_get_contact_not_found(client):
    response = client.get("/contacts/999999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Contact not found."


def test_update_contact_name(client):
    phone_number = unique_phone_number()

    create_response = client.post(
        "/contacts",
        json={
            "name": "Original Name",
            "phone_number": phone_number,
        },
    )
    assert create_response.status_code == 201, create_response.text

    contact_id = create_response.json()["id"]
    response = client.put(
        f"/contacts/{contact_id}",
        json={"name": "Updated Name"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Updated Name"
    assert response.json()["phone_number"] == phone_number


def test_update_contact_not_found(client):
    response = client.put(
        "/contacts/999999999",
        json={"name": "Updated Name"},
    )

    assert response.status_code == 404, response.text


def test_update_contact_rejects_empty_body(client):
    response = client.put("/contacts/1", json={})

    assert response.status_code == 422


def test_delete_contact(client):
    phone_number = unique_phone_number()

    create_response = client.post(
        "/contacts",
        json={
            "name": "Contact To Delete",
            "phone_number": phone_number,
        },
    )
    assert create_response.status_code == 201

    contact_id = create_response.json()["id"]
    response = client.delete(f"/contacts/{contact_id}")

    assert response.status_code == 204

    get_response = client.get(f"/contacts/{contact_id}")
    assert get_response.status_code == 404


def test_delete_contact_not_found(client):
    response = client.delete("/contacts/999999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Contact not found."
