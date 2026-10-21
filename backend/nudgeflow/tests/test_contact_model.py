
from nudgeflow.database import Base
from nudgeflow.models.contact import Contact


def test_contact_uses_contacts_table():
    assert Contact.__tablename__ == "contacts"
    assert "contacts" in Base.metadata.tables


def test_contact_has_expected_columns():
    expected_columns = {
        "id",
        "owner_id",
        "name",
        "phone_number",
        "created_at",
    }

    assert set(Contact.__table__.columns.keys()) == expected_columns


def test_contact_id_is_primary_key():
    id_column = Contact.__table__.columns["id"]

    assert id_column.primary_key is True


def test_contact_required_fields():
    table = Contact.__table__

    assert table.columns["name"].nullable is False
    assert table.columns["phone_number"].nullable is False
    assert table.columns["created_at"].nullable is False


def test_contact_phone_number_is_unique():
    phone_column = Contact.__table__.columns["phone_number"]

    assert phone_column.unique is True


def test_contact_owner_is_optional_foreign_key_to_users():
    owner_column = Contact.__table__.columns["owner_id"]
    assert owner_column.nullable is True
    foreign_key = next(iter(owner_column.foreign_keys))
    assert foreign_key.target_fullname == "users.id"
    assert foreign_key.ondelete == "SET NULL"


def test_contact_created_at_has_server_default():
    created_at_column = Contact.__table__.columns["created_at"]

    assert created_at_column.server_default is not None
