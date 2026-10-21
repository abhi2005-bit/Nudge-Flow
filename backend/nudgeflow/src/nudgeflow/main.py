from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from nudgeflow.routers.auth import router as auth_router

from nudgeflow.config import settings
from nudgeflow.database import get_db
from nudgeflow.dependencies import get_current_user
from nudgeflow.models.contact import Contact
from nudgeflow.models.follow_up import FollowUp
from nudgeflow.models.user import User
from nudgeflow.schemas.contact import ContactCreate, ContactResponse, ContactUpdate
from nudgeflow.schemas.follow_up import (
    FollowUpCreate,
    FollowUpResponse,
    FollowUpUpdate,
)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
)
app.include_router(auth_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


def is_phone_number_conflict(exc: IntegrityError) -> bool:
    """Recognize only the phone uniqueness violation across supported drivers."""
    original = exc.orig
    constraint = getattr(getattr(original, "diag", None), "constraint_name", None)
    if constraint == "ix_contacts_phone_number":
        return True
    message = str(original).lower()
    return "contacts.phone_number" in message or "ix_contacts_phone_number" in message


def commit_changes(db: Session) -> None:
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def save_contact(db: Session, contact: Contact) -> Contact:
    db.add(contact)
    try:
        commit_changes(db)
        db.refresh(contact)
    except IntegrityError as exc:
        db.rollback()
        if is_phone_number_conflict(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A contact with this phone number already exists.",
            ) from exc
        raise
    return contact


def get_owned_contact(db: Session, contact_id: int, owner_id: int) -> Contact | None:
    statement = select(Contact).where(
        Contact.id == contact_id,
        Contact.owner_id == owner_id,
    )
    return db.scalar(statement)


def get_owned_follow_up(
    db: Session,
    follow_up_id: int,
    owner_id: int,
) -> FollowUp | None:
    statement = (
        select(FollowUp)
        .join(Contact, Contact.id == FollowUp.contact_id)
        .where(FollowUp.id == follow_up_id, Contact.owner_id == owner_id)
    )
    return db.scalar(statement)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Welcome to NudgeFlow!"}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/contacts", response_model=ContactResponse, status_code=201)
def create_contact(
    contact_data: ContactCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Contact:
    return save_contact(
        db,
        Contact(**contact_data.model_dump(), owner_id=current_user.id),
    )


@app.get("/contacts", response_model=list[ContactResponse])
def list_contacts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[Contact]:
    statement = (
        select(Contact)
        .where(Contact.owner_id == current_user.id)
        .order_by(Contact.id)
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


@app.get("/contacts/{contact_id}", response_model=ContactResponse)
def get_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Contact:
    contact = get_owned_contact(db, contact_id, current_user.id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found.")
    return contact


@app.put("/contacts/{contact_id}", response_model=ContactResponse)
def update_contact(
    contact_id: int,
    contact_data: ContactUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Contact:
    contact = get_owned_contact(db, contact_id, current_user.id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found.")
    updates = contact_data.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update.")
    for field, value in updates.items():
        setattr(contact, field, value)
    return save_contact(db, contact)


@app.delete("/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    contact = get_owned_contact(db, contact_id, current_user.id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found.")
    db.delete(contact)
    commit_changes(db)


@app.post("/follow-ups", response_model=FollowUpResponse, status_code=201)
def create_follow_up(
    follow_up_data: FollowUpCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FollowUp:
    contact = db.scalar(
        select(Contact.id).where(
            Contact.id == follow_up_data.contact_id,
            Contact.owner_id == current_user.id,
        )
    )
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found.")
    follow_up = FollowUp(**follow_up_data.model_dump())
    db.add(follow_up)
    commit_changes(db)
    db.refresh(follow_up)
    return follow_up


@app.get("/follow-ups", response_model=list[FollowUpResponse])
def list_follow_ups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[FollowUp]:
    statement = (
        select(FollowUp)
        .join(Contact, Contact.id == FollowUp.contact_id)
        .where(Contact.owner_id == current_user.id)
        .order_by(FollowUp.due_at, FollowUp.id)
    )
    return list(db.scalars(statement.offset(offset).limit(limit)).all())


@app.get("/follow-ups/{follow_up_id}", response_model=FollowUpResponse)
def get_follow_up(
    follow_up_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FollowUp:
    follow_up = get_owned_follow_up(db, follow_up_id, current_user.id)
    if follow_up is None:
        raise HTTPException(status_code=404, detail="Follow-up not found.")
    return follow_up


@app.patch("/follow-ups/{follow_up_id}", response_model=FollowUpResponse)
def update_follow_up(
    follow_up_id: int,
    follow_up_data: FollowUpUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FollowUp:
    follow_up = get_owned_follow_up(db, follow_up_id, current_user.id)
    if follow_up is None:
        raise HTTPException(status_code=404, detail="Follow-up not found.")
    updates = follow_up_data.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update.")
    for field, value in updates.items():
        setattr(follow_up, field, value.strip() if field == "notes" and value else value)
    commit_changes(db)
    db.refresh(follow_up)
    return follow_up


@app.delete("/follow-ups/{follow_up_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_follow_up(
    follow_up_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    follow_up = get_owned_follow_up(db, follow_up_id, current_user.id)
    if follow_up is None:
        raise HTTPException(status_code=404, detail="Follow-up not found.")
    db.delete(follow_up)
    commit_changes(db)
