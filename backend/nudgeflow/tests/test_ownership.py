from datetime import datetime, timedelta, timezone
import uuid

from nudgeflow.models.contact import Contact
from nudgeflow.models.follow_up import FollowUp
from nudgeflow.models.user import User
from nudgeflow.security import hash_password
from nudgeflow.tokens import create_access_token


def register_headers(client, email: str) -> dict[str, str]:
    payload = {"email": email, "password": "Test-password-123!"}
    registered = client.post("/auth/register", json=payload)
    assert registered.status_code == 201, registered.text
    logged_in = client.post("/auth/login", json=payload)
    assert logged_in.status_code == 200, logged_in.text
    return {"Authorization": f"Bearer {logged_in.json()['access_token']}"}


def create_owned_contact(client) -> dict:
    response = client.post(
        "/contacts",
        json={
            "name": "Owner A contact",
            "phone_number": f"+91{uuid.uuid4().int % 10**10:010d}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_contact_records_are_isolated_between_users(client):
    contact = create_owned_contact(client)
    other_user_headers = register_headers(client, "other@example.com")

    assert client.get("/contacts", headers=other_user_headers).json() == []
    assert client.get(
        f"/contacts/{contact['id']}", headers=other_user_headers
    ).status_code == 404
    assert client.put(
        f"/contacts/{contact['id']}",
        json={"name": "Taken over"},
        headers=other_user_headers,
    ).status_code == 404
    assert client.delete(
        f"/contacts/{contact['id']}", headers=other_user_headers
    ).status_code == 404

    assert client.get(f"/contacts/{contact['id']}").status_code == 200
    assert client.get(f"/contacts/{contact['id']}").json()["name"] == "Owner A contact"


def test_email_identity_is_case_insensitive(client):
    response = client.post(
        "/auth/register",
        json={"email": "OWNER@example.COM", "password": "Test-password-123!"},
    )
    assert response.status_code == 409


def test_follow_ups_inherit_contact_ownership(client):
    contact = create_owned_contact(client)
    due_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    created = client.post(
        "/follow-ups",
        json={"contact_id": contact["id"], "title": "Call", "due_at": due_at},
    )
    assert created.status_code == 201, created.text
    follow_up_id = created.json()["id"]
    other_user_headers = register_headers(client, "other@example.com")

    assert client.get("/follow-ups", headers=other_user_headers).json() == []
    assert client.get(
        f"/follow-ups/{follow_up_id}", headers=other_user_headers
    ).status_code == 404
    assert client.patch(
        f"/follow-ups/{follow_up_id}",
        json={"status": "completed"},
        headers=other_user_headers,
    ).status_code == 404
    assert client.delete(
        f"/follow-ups/{follow_up_id}", headers=other_user_headers
    ).status_code == 404
    assert client.post(
        "/follow-ups",
        json={"contact_id": contact["id"], "title": "Intrude", "due_at": due_at},
        headers=other_user_headers,
    ).status_code == 404

    assert client.get(f"/follow-ups/{follow_up_id}").status_code == 200


def test_legacy_unassigned_records_are_preserved_but_not_exposed(
    db_session, anonymous_client
):
    user = User(
        email="legacy-check@example.com",
        hashed_password=hash_password("Unused-password-123!"),
    )
    db_session.add(user)
    db_session.flush()
    legacy_contact = Contact(
        name="Legacy contact",
        phone_number="+15550000090",
        owner_id=None,
    )
    db_session.add(legacy_contact)
    db_session.flush()
    legacy_follow_up = FollowUp(
        contact_id=legacy_contact.id,
        title="Legacy follow-up",
        due_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db_session.add(legacy_follow_up)
    db_session.commit()
    user_id = user.id
    contact_id = legacy_contact.id
    follow_up_id = legacy_follow_up.id

    token = create_access_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}
    assert anonymous_client.get("/contacts", headers=headers).json() == []
    assert anonymous_client.get("/follow-ups", headers=headers).json() == []
    assert anonymous_client.get(f"/contacts/{contact_id}", headers=headers).status_code == 404
    assert anonymous_client.get(
        f"/follow-ups/{follow_up_id}", headers=headers
    ).status_code == 404
