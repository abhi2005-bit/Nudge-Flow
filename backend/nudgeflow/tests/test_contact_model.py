
from nudgeflow.database import Base
from nudgeflow.models.contact import Contact


def test_contact_uses_contacts_table():
    assert Contact.__tablename__ == "contacts"
    assert "contacts" in Base.metadata.tables


def test_contact_has_expected_columns():
    expected_columns = {
        "id",
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


def test_contact_created_at_has_server_default():
    created_at_column = Contact.__table__.columns["created_at"]

    assert created_at_column.server_default is not None
