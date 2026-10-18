
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FollowUpCreate(BaseModel):
    """Fields required to create a follow-up."""

    contact_id: int
    title: str = Field(min_length=1, max_length=200)
    notes: str | None = None
    due_at: datetime


class FollowUpResponse(BaseModel):
    """Fields returned by the FollowUps API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    contact_id: int
    title: str
    notes: str | None
    due_at: datetime
    status: str
    created_at: datetime
