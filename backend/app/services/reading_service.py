from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.core.errors import ApiError
from app.models import Book, ReadingNote
from app.models.user import User
from app.schemas.reading_note import ReadingNoteCreate, ReadingNoteUpdate, ReadStatusUpdate


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _load_query(db: Session):
    return db.query(ReadingNote).options(joinedload(ReadingNote.book))


def _ensure_book_exists(db: Session, book_id: int) -> Book:
    book = db.get(Book, book_id)
    if book is None:
        raise ApiError("BOOK_NOT_FOUND", "图书不存在", status_code=404)
    return book


def get_note_or_error(db: Session, note_id: int) -> ReadingNote:
    note = _load_query(db).filter(ReadingNote.id == note_id).first()
    if note is None:
        raise ApiError("NOT_FOUND", "阅读笔记不存在", status_code=404)
    return note


def _ensure_note_owner_or_admin(note: ReadingNote, user: User) -> None:
    if note.user_id != user.id and user.role != "admin":
        raise ApiError("FORBIDDEN", "不能修改或删除他人的阅读笔记", status_code=403)


def list_book_notes(db: Session, book_id: int) -> list[ReadingNote]:
    _ensure_book_exists(db, book_id)
    return (
        _load_query(db)
        .filter(ReadingNote.book_id == book_id)
        .order_by(ReadingNote.updated_at.desc(), ReadingNote.id.desc())
        .all()
    )


def create_note(db: Session, book_id: int, payload: ReadingNoteCreate, *, current_user: User) -> ReadingNote:
    _ensure_book_exists(db, book_id)
    now = _now()
    note = ReadingNote(
        book_id=book_id,
        user_id=current_user.id,
        **payload.model_dump(),
        created_at=now,
        updated_at=now,
    )
    db.add(note)
    db.commit()
    return get_note_or_error(db, note.id)


def update_note(db: Session, note_id: int, payload: ReadingNoteUpdate, *, current_user: User) -> ReadingNote:
    note = get_note_or_error(db, note_id)
    _ensure_note_owner_or_admin(note, current_user)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(note, field, value)
    note.updated_at = _now()
    db.commit()
    return get_note_or_error(db, note.id)


def delete_note(db: Session, note_id: int, *, current_user: User) -> None:
    note = get_note_or_error(db, note_id)
    _ensure_note_owner_or_admin(note, current_user)
    db.delete(note)
    db.commit()


def update_read_status(
    db: Session,
    book_id: int,
    payload: ReadStatusUpdate,
    *,
    current_user_id: int | None = None,
) -> Book:
    book = _ensure_book_exists(db, book_id)
    book.read_status = payload.read_status
    book.updated_by = current_user_id
    book.updated_at = _now()
    db.commit()
    db.refresh(book)
    return book
