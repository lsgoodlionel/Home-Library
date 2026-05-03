from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.book import BookResponse
from app.schemas.reading_note import (
    ReadingNoteCreate,
    ReadingNoteResponse,
    ReadingNoteUpdate,
    ReadStatusUpdate,
)
from app.services import book_service, reading_service

router = APIRouter(tags=["reading"])


@router.get("/books/{book_id}/notes", response_model=list[ReadingNoteResponse])
def list_book_notes(
    book_id: int,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> list[object]:
    return reading_service.list_book_notes(db, book_id)


@router.post("/books/{book_id}/notes", response_model=ReadingNoteResponse, status_code=status.HTTP_201_CREATED)
def create_book_note(
    book_id: int,
    payload: ReadingNoteCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> object:
    return reading_service.create_note(db, book_id, payload, current_user=current_user)


@router.patch("/notes/{note_id}", response_model=ReadingNoteResponse)
def update_note(
    note_id: int,
    payload: ReadingNoteUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> object:
    return reading_service.update_note(db, note_id, payload, current_user=current_user)


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    note_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Response:
    reading_service.delete_note(db, note_id, current_user=current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/books/{book_id}/read-status", response_model=BookResponse)
def update_read_status(
    book_id: int,
    payload: ReadStatusUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    book = reading_service.update_read_status(db, book_id, payload, current_user_id=current_user.id)
    return book_service.book_to_response(book)
