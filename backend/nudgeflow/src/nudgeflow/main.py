
from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from nudgeflow.config import settings
from nudgeflow.database import get_db
from nudgeflow.models.contact import Contact
from nudgeflow.schemas.contact import (
    ContactCreate,
    ContactResponse,
    ContactUpdate,
)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
)


@app.get("/")
def root():
    return {"message": "Welcome to NudgeFlow!"}
@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/contacts",
    response_model=ContactResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_contact(
    contact_data: ContactCreate,
    db: Session = Depends(get_db),
) -> Contact:
    """Create and persist a new contact."""
    contact = Contact(
        name=contact_data.name.strip(),
        phone_number=contact_data.phone_number.strip(),
    )

    if not contact.name or not contact.phone_number:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Name and phone number cannot be blank.",
        )

    db.add(contact)

    try:
        db.commit()
        db.refresh(contact)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A contact with this phone number may already exist.",
        ) from exc

    return contact


@app.get("/contacts", response_model=list[ContactResponse])
def list_contacts(
    db: Session = Depends(get_db),
    String:str = None
) -> list[Contact]:
    """Return all contacts ordered by ID."""
    statement = select(Contact).order_by(Contact.id)
    return list(db.scalars(statement).all())


@app.get("/contacts/{contact_id}", response_model=ContactResponse)
def get_contact(
    contact_id: int,
    db: Session = Depends(get_db),
) -> Contact:
    """Return one contact by ID."""
    statement = select(Contact).where(Contact.id == contact_id)
    contact = db.scalar(statement)

    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found.",
        )

    return contact


@app.put("/contacts/{contact_id}", response_model=ContactResponse)
def update_contact(
    contact_id: int,
    contact_data: ContactUpdate,
    db: Session = Depends(get_db),
) -> Contact:
    contact = db.get(Contact, contact_id)

    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found.")

    updates = contact_data.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update.")

    for field, value in updates.items():
        setattr(contact, field, value.strip() if value else value)

    try:
        db.commit()
        db.refresh(contact)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Phone number already exists.",
        ) from exc

    return contact


@app.delete("/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact(
    contact_id: int,
    db: Session = Depends(get_db),
) -> None:
    """Delete an existing contact."""
    contact = db.get(Contact, contact_id)

    if contact is None:
        raise HTTPException(
            status_code=404,
            detail="Contact not found.",
        )

    db.delete(contact)
    db.commit()

