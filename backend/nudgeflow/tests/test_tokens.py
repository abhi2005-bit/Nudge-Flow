from datetime import UTC, datetime, timedelta

import jwt
import pytest

from nudgeflow.config import settings
from nudgeflow.tokens import (
    ALGORITHM,
    create_access_token,
    decode_access_token,
)


def test_create_and_decode_access_token():
    token = create_access_token(user_id=123)

    payload = decode_access_token(token)

    assert payload["sub"] == "123"
    assert "iat" in payload
    assert "exp" in payload


def test_decode_token_with_invalid_signature():
    token = create_access_token(user_id=123)

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token + "invalid")


def test_decode_expired_token():
    now = datetime.now(UTC)
    expired_payload = {
        "sub": "123",
        "iat": now - timedelta(minutes=10),
        "exp": now - timedelta(minutes=5),
    }

    expired_token = jwt.encode(
        expired_payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=ALGORITHM,
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(expired_token)


def test_decode_rejects_non_user_subject():
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": "not-a-user-id", "iat": now, "exp": now + timedelta(minutes=5)},
        settings.jwt_secret_key.get_secret_value(),
        algorithm=ALGORITHM,
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)
