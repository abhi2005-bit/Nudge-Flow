
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ContactCreate(BaseModel):
    """Fields accepted when creating a contact."""

    name: str = Field(min_length=1, max_length=150)
    phone_number: str = Field(min_length=1, max_length=30)


class ContactResponse(BaseModel):
    """Fields returned by the Contacts API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone_number: str
    created_at: datetime

class ContactUpdate(BaseModel):
    """Fields that can be updated for an existing contact."""
    name: str | None = Field(default=None, min_length=1, max_length=150)
    phone_number: str | None = Field(default=None, min_length=1, max_length=30)
