
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from nudgeflow.schemas.user import TokenResponse, UserLogin
from nudgeflow.security import DUMMY_PASSWORD_HASH, verify_password
from nudgeflow.tokens import TokenConfigurationError, create_access_token

from nudgeflow.database import get_db
from nudgeflow.models.user import User
from nudgeflow.schemas.user import UserCreate, UserResponse
from nudgeflow.security import hash_password


router = APIRouter(prefix="/auth", tags=["Authentication"])


def _is_email_conflict(exc: IntegrityError) -> bool:
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if constraint == "ix_users_email":
        return True
    message = str(exc.orig).lower()
    return "users.email" in message or "ix_users_email" in message


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
) -> User:
    existing_user = db.scalar(
        select(User).where(func.lower(User.email) == user_data.email)
    )

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
    )

    db.add(user)

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        if _is_email_conflict(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            ) from exc
        raise

    return user

@router.post("/login", response_model=TokenResponse)
def login_user(
    credentials: UserLogin,
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = db.scalar(
        select(User).where(func.lower(User.email) == credentials.email)
    )

    password_matches = verify_password(
        credentials.password,
        user.hashed_password if user is not None else DUMMY_PASSWORD_HASH,
    )
    if user is None or not password_matches:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        token = create_access_token(user_id=user.id)
    except TokenConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured.",
        ) from exc

    return TokenResponse(access_token=token)
