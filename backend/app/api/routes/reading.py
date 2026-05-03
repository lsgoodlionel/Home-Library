from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.reading_note import (
    ReadingNoteCreate,
    ReadingNoteResponse,
    ReadingNoteUpdate,
    ReadStatusUpdate,
)
from app.services import reading_service

router = APIRouter(tags=["reading"])

CurrentUser = Annotated[User, Depends(get_current_user)]
DB = Annotated[Session, Depends(get_db)]


@router.get("/books/{book_id}/notes", response_model=list[ReadingNoteResponse])
def get_book_notes(
    book_id: int,
    db: DB,
    _: CurrentUser,
) -> list[ReadingNoteResponse]:
    return reading_service.get_book_notes(db, book_id)


@router.post(
    "/books/{book_id}/notes",
    response_model=ReadingNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_note(
    book_id: int,
    payload: ReadingNoteCreate,
    db: DB,
    current_user: CurrentUser,
) -> ReadingNoteResponse:
    return reading_service.create_note(db, book_id, payload, user_id=current_user.id)


@router.patch("/notes/{note_id}", response_model=ReadingNoteResponse)
def update_note(
    note_id: int,
    payload: ReadingNoteUpdate,
    db: DB,
    current_user: CurrentUser,
) -> ReadingNoteResponse:
    is_admin = current_user.role == "admin"
    return reading_service.update_note(db, note_id, payload, user_id=current_user.id, is_admin=is_admin)


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    note_id: int,
    db: DB,
    current_user: CurrentUser,
) -> Response:
    is_admin = current_user.role == "admin"
    reading_service.delete_note(db, note_id, user_id=current_user.id, is_admin=is_admin)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/books/{book_id}/read-status")
def update_read_status(
    book_id: int,
    payload: ReadStatusUpdate,
    db: DB,
    _: CurrentUser,
) -> dict:
    book = reading_service.update_read_status(db, book_id, payload.read_status)
    return {"id": book.id, "read_status": book.read_status}
