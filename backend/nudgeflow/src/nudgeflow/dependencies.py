import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from nudgeflow.database import get_db
from nudgeflow.models.user import User
from nudgeflow.tokens import TokenConfigurationError, decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Validate a bearer token and load the user it represents."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    try:
        claims = decode_access_token(credentials.credentials)
    except TokenConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured.",
        ) from exc
    except (jwt.PyJWTError, TypeError, ValueError) as exc:
        raise _unauthorized() from exc

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.isdecimal():
        raise _unauthorized()

    user = db.get(User, int(subject))
    if user is None:
        raise _unauthorized()
    return user
