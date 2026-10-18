
from sqlalchemy import text


def test_database_connection(test_engine):
    with test_engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1
