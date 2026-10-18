from datetime import datetime, timedelta, timezone
import uuid


def create_contact(client):
    response = client.post(
        "/contacts",
        json={"name": "Follow-up Contact", "phone_number": f"+91{uuid.uuid4().int % 10**10:010d}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_follow_up(client, contact_id, **overrides):
    body = {
        "contact_id": contact_id,
        "title": "Call customer",
        "notes": "Discuss quotation",
        "due_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    }
    body.update(overrides)
    return client.post("/follow-ups", json=body)


def test_create_list_and_retrieve_follow_up(client):
    contact = create_contact(client)
    created = create_follow_up(client, contact["id"])
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "pending"
    follow_up_id = created.json()["id"]
    assert client.get(f"/follow-ups/{follow_up_id}").json()["title"] == "Call customer"
    listed = client.get("/follow-ups")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [follow_up_id]


def test_follow_up_listing_is_ordered_and_paginated(client):
    contact = create_contact(client)
    first_due = datetime.now(timezone.utc) + timedelta(days=2)
    later_due = first_due + timedelta(days=1)
    first = create_follow_up(client, contact["id"], due_at=first_due.isoformat()).json()
    second = create_follow_up(client, contact["id"], due_at=later_due.isoformat()).json()
    assert [x["id"] for x in client.get("/follow-ups").json()] == [first["id"], second["id"]]
    assert len(client.get("/follow-ups?limit=1").json()) == 1


def test_invalid_contact_returns_404(client):
    response = create_follow_up(client, 999999999)
    assert response.status_code == 404
    assert response.json()["detail"] == "Contact not found."


def test_partial_update_complete_and_reschedule(client):
    contact = create_contact(client)
    created = create_follow_up(client, contact["id"]).json()
    rescheduled = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    response = client.patch(
        f"/follow-ups/{created['id']}",
        json={"status": "completed", "due_at": rescheduled},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    assert response.json()["title"] == "Call customer"
    assert datetime.fromisoformat(response.json()["due_at"]) == datetime.fromisoformat(rescheduled)


def test_follow_up_update_rejects_invalid_or_empty_data(client):
    contact = create_contact(client)
    created = create_follow_up(client, contact["id"]).json()
    follow_up_id = created["id"]
    assert client.patch(f"/follow-ups/{follow_up_id}", json={}).status_code == 422
    assert client.patch(f"/follow-ups/{follow_up_id}", json={"status": "unknown"}).status_code == 422
    assert client.patch(f"/follow-ups/{follow_up_id}", json={"title": "  "}).status_code == 422
    assert client.patch(f"/follow-ups/{follow_up_id}", json={"due_at": "2026-10-19T12:00:00"}).status_code == 422


def test_follow_up_creation_rejects_invalid_fields(client):
    contact = create_contact(client)
    assert create_follow_up(client, contact["id"], title=" ").status_code == 422
    assert create_follow_up(client, contact["id"], status="cancelled").status_code == 422


def test_missing_follow_up_returns_404(client):
    assert client.get("/follow-ups/999999999").status_code == 404
    assert client.patch("/follow-ups/999999999", json={"status": "completed"}).status_code == 404
    assert client.delete("/follow-ups/999999999").status_code == 404


def test_delete_follow_up(client):
    contact = create_contact(client)
    follow_up = create_follow_up(client, contact["id"]).json()
    assert client.delete(f"/follow-ups/{follow_up['id']}").status_code == 204
    assert client.get(f"/follow-ups/{follow_up['id']}").status_code == 404
