from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def clean_required_text(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


class ContactCreate(BaseModel):
    """Fields accepted when creating a contact."""

    name: str = Field(min_length=1, max_length=150)
    phone_number: str = Field(min_length=1, max_length=30)

    _clean_name = field_validator("name")(clean_required_text)
    _clean_phone = field_validator("phone_number")(clean_required_text)


class ContactUpdate(BaseModel):
    """Fields that can be updated for an existing contact."""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    phone_number: str | None = Field(default=None, min_length=1, max_length=30)

    @field_validator("name", "phone_number")
    @classmethod
    def validate_supplied_text(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("must not be null")
        return clean_required_text(value)


class ContactResponse(BaseModel):
    """Fields returned by the Contacts API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone_number: str
    created_at: datetime
