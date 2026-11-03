"""Tenant-safe WhatsApp sender identity helpers."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from nudgeflow.models.contact import Contact

_E164_DIGITS = re.compile(r"^[1-9][0-9]{7,14}$")


def normalize_whatsapp_phone_number(value: object) -> str | None:
    """Return canonical E.164 or None without guessing a country code."""
    if not isinstance(value, str):
        return None
    digits = value.strip()
    if digits.startswith("+"):
        digits = digits[1:]
    if not _E164_DIGITS.fullmatch(digits):
        return None
    return f"+{digits}"


def resolve_tenant_contact(
    db: Session, *, tenant_id: int, sender_phone_number: str
) -> Contact | None:
    """Resolve only an unambiguous pre-existing contact inside one tenant."""
    matches = [
        contact
        for contact in db.scalars(
            select(Contact).where(Contact.tenant_id == tenant_id)
        )
        if normalize_whatsapp_phone_number(contact.phone_number) == sender_phone_number
    ]
    return matches[0] if len(matches) == 1 else None
