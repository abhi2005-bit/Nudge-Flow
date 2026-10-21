from datetime import datetime, timedelta, timezone
import uuid

from nudgeflow.models.contact import Contact
from nudgeflow.models.follow_up import FollowUp
from nudgeflow.models.tenant import Tenant
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


def test_tenant_ids_are_derived_from_authenticated_user(client, db_session):
    owner = db_session.query(User).filter_by(email="owner@example.com").one()
    other_headers = register_headers(client, "other-tenant@example.com")
    other = (
        db_session.query(User)
        .filter_by(email="other-tenant@example.com")
        .one()
    )
    assert owner.tenant_id != other.tenant_id

    contact_response = client.post(
        "/contacts",
        json={
            "name": "Server scoped contact",
            "phone_number": "+15550000111",
            "tenant_id": other.tenant_id,
        },
    )
    assert contact_response.status_code == 201, contact_response.text
    contact = db_session.get(Contact, contact_response.json()["id"])
    assert contact is not None
    assert contact.tenant_id == owner.tenant_id

    due_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    task_response = client.post(
        "/follow-ups",
        json={
            "contact_id": contact.id,
            "title": "Server scoped task",
            "due_at": due_at,
            "tenant_id": other.tenant_id,
        },
    )
    assert task_response.status_code == 201, task_response.text
    follow_up = db_session.get(FollowUp, task_response.json()["id"])
    assert follow_up is not None
    assert follow_up.tenant_id == owner.tenant_id


def test_member_can_access_records_in_their_business_tenant(client, db_session):
    owner = db_session.query(User).filter_by(email="owner@example.com").one()
    member = User(
        email="member@example.com",
        hashed_password=hash_password("Member-password-123!"),
        tenant_id=owner.tenant_id,
        tenant_role="member",
    )
    db_session.add(member)
    db_session.flush()
    member_headers = {
        "Authorization": f"Bearer {create_access_token(member.id)}"
    }

    contact = create_owned_contact(client)
    due_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    follow_up = client.post(
        "/follow-ups",
        json={"contact_id": contact["id"], "title": "Shared task", "due_at": due_at},
    ).json()

    assert client.get("/contacts", headers=member_headers).json() == [contact]
    assert client.get(
        f"/contacts/{contact['id']}", headers=member_headers
    ).status_code == 200
    assert client.get(
        f"/follow-ups/{follow_up['id']}", headers=member_headers
    ).status_code == 200


def test_same_phone_number_can_exist_in_different_tenants(client):
    phone_number = "+15550000112"
    first = client.post(
        "/contacts",
        json={"name": "First business", "phone_number": phone_number},
    )
    assert first.status_code == 201, first.text

    other_headers = register_headers(client, "another-business@example.com")
    second = client.post(
        "/contacts",
        json={"name": "Second business", "phone_number": phone_number},
        headers=other_headers,
    )
    assert second.status_code == 201, second.text
    assert second.json()["id"] != first.json()["id"]


def test_legacy_unassigned_records_are_preserved_but_not_exposed(
    db_session, anonymous_client
):
    quarantine = Tenant(name="Unassigned legacy records (quarantined)")
    user_tenant = Tenant(name="Legacy user's workspace")
    db_session.add_all([quarantine, user_tenant])
    db_session.flush()
    user = User(
        email="legacy-check@example.com",
        hashed_password=hash_password("Unused-password-123!"),
        tenant_id=user_tenant.id,
        tenant_role="owner",
    )
    db_session.add(user)
    db_session.flush()
    legacy_contact = Contact(
        name="Legacy contact",
        phone_number="+15550000090",
        owner_id=None,
        tenant_id=quarantine.id,
    )
    db_session.add(legacy_contact)
    db_session.flush()
    legacy_follow_up = FollowUp(
        contact_id=legacy_contact.id,
        tenant_id=quarantine.id,
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
