from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.book import Book
from app.models.reading_note import ReadingNote
from app.schemas.reading_note import ReadingNoteCreate, ReadingNoteUpdate


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _get_book_or_error(db: Session, book_id: int) -> Book:
    book = db.get(Book, book_id)
    if book is None:
        raise ApiError("NOT_FOUND", "图书不存在", status_code=404)
    return book


def get_note_or_error(db: Session, note_id: int) -> ReadingNote:
    note = db.get(ReadingNote, note_id)
    if note is None:
        raise ApiError("NOT_FOUND", "笔记不存在", status_code=404)
    return note


def get_book_notes(db: Session, book_id: int) -> list[ReadingNote]:
    _get_book_or_error(db, book_id)
    return (
        db.query(ReadingNote)
        .filter(ReadingNote.book_id == book_id)
        .order_by(ReadingNote.created_at.desc())
        .all()
    )


def create_note(
    db: Session,
    book_id: int,
    payload: ReadingNoteCreate,
    user_id: int,
) -> ReadingNote:
    _get_book_or_error(db, book_id)

    now = _now()
    note = ReadingNote(
        book_id=book_id,
        user_id=user_id,
        title=payload.title,
        content=payload.content,
        progress=payload.progress,
        rating=payload.rating,
        started_at=payload.started_at,
        finished_at=payload.finished_at,
        created_at=now,
        updated_at=now,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


def update_note(
    db: Session,
    note_id: int,
    payload: ReadingNoteUpdate,
    user_id: int,
    is_admin: bool = False,
) -> ReadingNote:
    note = get_note_or_error(db, note_id)

    if not is_admin and note.user_id != user_id:
        raise ApiError("FORBIDDEN", "无权修改此笔记", status_code=403)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(note, field, value)
    note.updated_at = _now()

    db.commit()
    db.refresh(note)
    return note


def delete_note(
    db: Session,
    note_id: int,
    user_id: int,
    is_admin: bool = False,
) -> None:
    note = get_note_or_error(db, note_id)

    if not is_admin and note.user_id != user_id:
        raise ApiError("FORBIDDEN", "无权删除此笔记", status_code=403)

    db.delete(note)
    db.commit()


def update_read_status(db: Session, book_id: int, read_status: str) -> Book:
    valid = {"unread", "reading", "read", "paused"}
    if read_status not in valid:
        raise ApiError("VALIDATION_ERROR", f"无效的阅读状态，允许值：{', '.join(sorted(valid))}", status_code=422)

    book = _get_book_or_error(db, book_id)
    book.read_status = read_status
    book.updated_at = _now()
    db.commit()
    db.refresh(book)
    return book
