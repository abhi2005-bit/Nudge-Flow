from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from nudgeflow.schemas.contact import clean_required_text

FollowUpStatus = Literal["pending", "completed"]


def require_timezone(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone")
    return value.astimezone(timezone.utc)


class FollowUpCreate(BaseModel):
    """Fields required to create a follow-up."""

    contact_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)
    notes: str | None = None
    due_at: datetime
    status: FollowUpStatus = "pending"

    _clean_title = field_validator("title")(clean_required_text)
    _require_timezone = field_validator("due_at")(require_timezone)


class FollowUpUpdate(BaseModel):
    """Fields that can be changed on an existing follow-up."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = None
    due_at: datetime | None = None
    status: FollowUpStatus | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("must not be null")
        return clean_required_text(value)

    @field_validator("due_at")
    @classmethod
    def validate_due_at(cls, value: datetime | None) -> datetime:
        if value is None:
            raise ValueError("must not be null")
        return require_timezone(value)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: FollowUpStatus | None) -> FollowUpStatus:
        if value is None:
            raise ValueError("must not be null")
        return value


class FollowUpResponse(BaseModel):
    """Fields returned by the Follow-ups API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    contact_id: int
    title: str
    notes: str | None
    due_at: datetime
    status: FollowUpStatus
    created_at: datetime
