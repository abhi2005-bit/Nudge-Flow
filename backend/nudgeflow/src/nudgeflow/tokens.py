from datetime import UTC, datetime, timedelta

import jwt

from nudgeflow.config import settings


ALGORITHM = "HS256"


class TokenConfigurationError(RuntimeError):
    """Raised when signing cannot proceed because the JWT secret is unsafe."""


def _jwt_secret() -> str:
    secret = settings.jwt_secret_key.get_secret_value()
    if len(secret) < 32 or secret.lower().startswith(("replace-", "change-me")):
        raise TokenConfigurationError("JWT signing is not configured safely.")
    return secret


def create_access_token(user_id: int) -> str:
    """Create a signed JWT for an authenticated user."""
    if user_id <= 0:
        raise ValueError("user_id must be a positive integer")

    now = datetime.now(UTC)
    expires_at = now + timedelta(
        minutes=settings.access_token_expire_minutes
    )

    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": expires_at,
    }

    return jwt.encode(payload, _jwt_secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, object]:
    """Verify a JWT and return its payload."""
    payload = jwt.decode(
        token,
        _jwt_secret(),
        algorithms=[ALGORITHM],
        options={"require": ["sub", "iat", "exp"]},
    )

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.isdecimal() or int(subject) <= 0:
        raise jwt.InvalidTokenError("Invalid subject claim.")
    return payload
