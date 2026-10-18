import uuid


def phone() -> str:
    return f"+91{uuid.uuid4().int % 10**10:010d}"


def create_contact(client, name="Test Contact", phone_number=None):
    return client.post(
        "/contacts",
        json={"name": name, "phone_number": phone_number or phone()},
    )


def test_create_and_retrieve_contact(client):
    created = create_contact(client, "  Asha Rao  ")
    assert created.status_code == 201, created.text
    result = client.get(f"/contacts/{created.json()['id']}")
    assert result.status_code == 200
    assert result.json()["name"] == "Asha Rao"


def test_list_contacts(client):
    create_contact(client, "One")
    create_contact(client, "Two")
    response = client.get("/contacts")
    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["One", "Two"]


def test_contact_list_pagination(client):
    create_contact(client, "One")
    create_contact(client, "Two")
    assert len(client.get("/contacts?limit=1&offset=1").json()) == 1


def test_partial_update_preserves_omitted_fields(client):
    created = create_contact(client, "Before")
    body = created.json()
    updated = client.put(f"/contacts/{body['id']}", json={"name": "After"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "After"
    assert updated.json()["phone_number"] == body["phone_number"]


def test_missing_contact_returns_404(client):
    assert client.get("/contacts/999999999").status_code == 404
    assert client.put("/contacts/999999999", json={"name": "New"}).status_code == 404
    assert client.delete("/contacts/999999999").status_code == 404


def test_duplicate_phone_returns_409(client):
    number = phone()
    assert create_contact(client, "First", number).status_code == 201
    duplicate = create_contact(client, "Second", number)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "A contact with this phone number already exists."


def test_contact_rejects_blank_fields(client):
    for body in (
        {"name": "   ", "phone_number": phone()},
        {"name": "Valid", "phone_number": "  "},
    ):
        assert client.post("/contacts", json=body).status_code == 422


def test_contact_update_rejects_empty_and_blank_fields(client):
    created = create_contact(client)
    contact_id = created.json()["id"]
    assert client.put(f"/contacts/{contact_id}", json={}).status_code == 422
    assert client.put(f"/contacts/{contact_id}", json={"name": "  "}).status_code == 422


def test_delete_contact_cascades_follow_ups(client):
    contact = create_contact(client).json()
    from datetime import datetime, timedelta, timezone

    follow_up = client.post(
        "/follow-ups",
        json={
            "contact_id": contact["id"],
            "title": "Call",
            "due_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
    ).json()
    assert client.delete(f"/contacts/{contact['id']}").status_code == 204
    assert client.get(f"/follow-ups/{follow_up['id']}").status_code == 404


def test_delete_contact(client):
    contact = create_contact(client).json()
    assert client.delete(f"/contacts/{contact['id']}").status_code == 204
    assert client.get(f"/contacts/{contact['id']}").status_code == 404
