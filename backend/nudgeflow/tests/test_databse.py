
from sqlalchemy import text

from nudgeflow.database import engine


def test_database_connection():
    with engine.connect() as connection:
        result = connection.execute(
            text("SELECT current_database(), current_user")
        ).one()

    assert result.current_database == "nudgeflow"
    assert result.current_user == "postgres"
