from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session, joinedload

from app.core.errors import ApiError
from app.models.book import Book
from app.models.borrow_record import BorrowRecord
from app.schemas.borrow_record import BorrowRecordCreate, BorrowReturn


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def get_borrow_or_error(db: Session, record_id: int) -> BorrowRecord:
    record = (
        db.query(BorrowRecord)
        .options(joinedload(BorrowRecord.book))
        .filter(BorrowRecord.id == record_id)
        .first()
    )
    if record is None:
        raise ApiError("NOT_FOUND", "借阅记录不存在", status_code=404)
    return record


def _get_active_borrow_for_book(db: Session, book_id: int) -> Optional[BorrowRecord]:
    return (
        db.query(BorrowRecord)
        .filter(and_(BorrowRecord.book_id == book_id, BorrowRecord.status == "active"))
        .first()
    )


def create_borrow(
    db: Session,
    payload: BorrowRecordCreate,
    created_by: Optional[int] = None,
) -> BorrowRecord:
    book = db.get(Book, payload.book_id)
    if book is None:
        raise ApiError("NOT_FOUND", "图书不存在", status_code=404)

    if _get_active_borrow_for_book(db, payload.book_id):
        raise ApiError("CONFLICT", "该图书当前已借出，请先归还", status_code=409)

    now = _now()
    record = BorrowRecord(
        book_id=payload.book_id,
        borrower_name=payload.borrower_name,
        borrower_contact=payload.borrower_contact,
        borrowed_at=payload.borrowed_at,
        due_at=payload.due_at,
        status="active",
        note=payload.note,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )

    book.status = "borrowed"
    book.updated_at = now

    db.add(record)
    db.commit()
    db.refresh(record)
    # reload with book relationship
    return get_borrow_or_error(db, record.id)


def return_borrow(
    db: Session,
    record_id: int,
    payload: BorrowReturn,
) -> BorrowRecord:
    record = get_borrow_or_error(db, record_id)

    if record.status != "active":
        raise ApiError("CONFLICT", "该借阅记录已归还，无法重复归还", status_code=409)

    now = _now()
    record.returned_at = payload.returned_at
    record.status = "returned"
    record.updated_at = now
    if payload.note is not None:
        record.note = payload.note

    if record.book is not None:
        record.book.status = "available"
        record.book.updated_at = now

    db.commit()
    db.refresh(record)
    return record


def list_borrow_records(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    book_id: Optional[int] = None,
    status: Optional[str] = None,
    borrower_name: Optional[str] = None,
) -> tuple[list[BorrowRecord], int]:
    query = db.query(BorrowRecord).options(joinedload(BorrowRecord.book))

    if book_id is not None:
        query = query.filter(BorrowRecord.book_id == book_id)
    if status is not None:
        query = query.filter(BorrowRecord.status == status)
    if borrower_name is not None:
        query = query.filter(BorrowRecord.borrower_name.contains(borrower_name))

    total = query.count()
    items = (
        query.order_by(BorrowRecord.borrowed_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def list_active_borrows(
    db: Session,
    page: int = 1,
    page_size: int = 100,
) -> tuple[list[BorrowRecord], int]:
    query = (
        db.query(BorrowRecord)
        .options(joinedload(BorrowRecord.book))
        .filter(BorrowRecord.status == "active")
    )
    total = query.count()
    items = (
        query.order_by(BorrowRecord.borrowed_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total
