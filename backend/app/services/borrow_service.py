from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.core.errors import ApiError
from app.models import Book, BorrowRecord
from app.schemas.borrow_record import BorrowRecordCreate, BorrowReturn


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _load_query(db: Session):
    return db.query(BorrowRecord).options(joinedload(BorrowRecord.book))


def _refresh_overdue_status(record: BorrowRecord) -> None:
    if record.returned_at is None and record.due_at is not None and record.due_at < date.today():
        record.status = "overdue"


def get_record_or_error(db: Session, record_id: int) -> BorrowRecord:
    record = _load_query(db).filter(BorrowRecord.id == record_id).first()
    if record is None:
        raise ApiError("NOT_FOUND", "借阅记录不存在", status_code=404)
    _refresh_overdue_status(record)
    return record


def _ensure_book_exists(db: Session, book_id: int) -> Book:
    book = db.get(Book, book_id)
    if book is None:
        raise ApiError("BOOK_NOT_FOUND", "图书不存在", status_code=404)
    return book


def _ensure_no_active_borrow(db: Session, book_id: int) -> None:
    existing = (
        db.query(BorrowRecord)
        .filter(
            BorrowRecord.book_id == book_id,
            BorrowRecord.returned_at.is_(None),
            BorrowRecord.status.in_(["active", "overdue"]),
        )
        .first()
    )
    if existing is not None:
        raise ApiError("CONFLICT", "该图书当前已有未归还借阅记录", status_code=409)


def create_borrow(db: Session, payload: BorrowRecordCreate, *, current_user_id: int | None = None) -> BorrowRecord:
    book = _ensure_book_exists(db, payload.book_id)
    _ensure_no_active_borrow(db, payload.book_id)

    now = _now()
    record = BorrowRecord(
        **payload.model_dump(),
        status="active",
        created_by=current_user_id,
        created_at=now,
        updated_at=now,
    )
    book.status = "borrowed"
    book.updated_by = current_user_id
    book.updated_at = now
    db.add(record)
    db.commit()
    return get_record_or_error(db, record.id)


def return_borrow(db: Session, record_id: int, payload: BorrowReturn, *, current_user_id: int | None = None) -> BorrowRecord:
    record = get_record_or_error(db, record_id)
    if record.returned_at is not None or record.status == "returned":
        raise ApiError("CONFLICT", "借阅记录已归还", status_code=409)

    now = _now()
    record.returned_at = payload.returned_at
    record.status = "returned"
    if payload.note is not None:
        record.note = payload.note
    record.updated_at = now

    book = _ensure_book_exists(db, record.book_id)
    book.status = "available"
    book.updated_by = current_user_id
    book.updated_at = now
    db.commit()
    return get_record_or_error(db, record.id)


def list_records(
    db: Session,
    *,
    book_id: int | None = None,
    status: str | None = None,
    borrower_name: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> tuple[list[BorrowRecord], int]:
    query = _load_query(db)
    if book_id is not None:
        query = query.filter(BorrowRecord.book_id == book_id)
    if status is not None:
        query = query.filter(BorrowRecord.status == status)
    if borrower_name:
        query = query.filter(BorrowRecord.borrower_name.ilike(f"%{borrower_name.strip()}%"))

    total = query.order_by(None).count()
    query = query.order_by(BorrowRecord.borrowed_at.desc(), BorrowRecord.id.desc())
    if page is not None and page_size is not None:
        query = query.offset((page - 1) * page_size).limit(page_size)
    records = query.all()
    for record in records:
        _refresh_overdue_status(record)
    if any(record.status == "overdue" for record in records):
        db.commit()
    return records, total


def list_active_records(db: Session) -> list[BorrowRecord]:
    records = (
        _load_query(db)
        .filter(
            BorrowRecord.returned_at.is_(None),
            BorrowRecord.status.in_(["active", "overdue"]),
        )
        .order_by(BorrowRecord.borrowed_at.desc(), BorrowRecord.id.desc())
        .all()
    )
    for record in records:
        _refresh_overdue_status(record)
    if any(record.status == "overdue" for record in records):
        db.commit()
    return records


def delete_record(db: Session, record_id: int) -> None:
    record = get_record_or_error(db, record_id)
    if record.returned_at is None and record.status in {"active", "overdue"}:
        raise ApiError("CONFLICT", "未归还借阅记录不能删除", status_code=409)
    db.delete(record)
    db.commit()
