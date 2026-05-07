from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.errors import ApiError
from app.models import Book, BookTag, BorrowRecord, Category, Location, ReadingNote, Tag
from app.schemas.book import BookBatchUpdate, BookCreate, BookUpdate


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _clean_isbn(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = "".join(char for char in value if char.isdigit() or char.upper() == "X")
    return cleaned or None


def _normalize_tag_names(tag_names: list[str] | None) -> list[str]:
    if not tag_names:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for name in tag_names:
        clean_name = name.strip()
        if clean_name and clean_name not in seen:
            normalized.append(clean_name)
            seen.add(clean_name)
    return normalized


def _load_book_query(db: Session):
    return db.query(Book).options(
        joinedload(Book.category),
        joinedload(Book.location),
        selectinload(Book.book_tags).joinedload(BookTag.tag),
    )


def _ensure_category_exists(db: Session, category_id: int | None) -> None:
    if category_id is not None and db.get(Category, category_id) is None:
        raise ApiError("NOT_FOUND", "分类不存在", status_code=404)


def _ensure_location_exists(db: Session, location_id: int | None) -> None:
    if location_id is not None and db.get(Location, location_id) is None:
        raise ApiError("NOT_FOUND", "位置不存在", status_code=404)


def get_book_or_error(db: Session, book_id: int) -> Book:
    book = _load_book_query(db).filter(Book.id == book_id).first()
    if book is None:
        raise ApiError("BOOK_NOT_FOUND", "图书不存在", status_code=404)
    return book


def list_books(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    category_id: int | None = None,
    location_id: int | None = None,
    status: str | None = None,
    read_status: str | None = None,
    is_favorite: bool | None = None,
    publish_year_from: int | None = None,
    publish_year_to: int | None = None,
) -> tuple[list[Book], int]:
    query = _load_book_query(db)

    if keyword:
        pattern = f"%{keyword.strip()}%"
        query = query.filter(
            or_(
                Book.title.ilike(pattern),
                Book.author.ilike(pattern),
                Book.isbn.ilike(pattern),
                Book.publisher.ilike(pattern),
            )
        )
    if category_id is not None:
        query = query.filter(Book.category_id == category_id)
    if location_id is not None:
        query = query.filter(Book.location_id == location_id)
    if status is not None:
        query = query.filter(Book.status == status)
    if read_status is not None:
        query = query.filter(Book.read_status == read_status)
    if is_favorite is not None:
        query = query.filter(Book.is_favorite == is_favorite)
    if publish_year_from is not None:
        query = query.filter(Book.publish_year >= publish_year_from)
    if publish_year_to is not None:
        query = query.filter(Book.publish_year <= publish_year_to)

    total = query.order_by(None).count()
    items = (
        query.order_by(Book.updated_at.desc(), Book.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def _set_book_tags(db: Session, book: Book, tag_names: list[str] | None) -> None:
    normalized_names = _normalize_tag_names(tag_names)

    if not normalized_names:
        book.book_tags = []
        return

    existing_tags = db.query(Tag).filter(Tag.name.in_(normalized_names)).all()
    tags_by_name = {tag.name: tag for tag in existing_tags}

    now = _now()
    for name in normalized_names:
        if name not in tags_by_name:
            tag = Tag(name=name, created_at=now)
            db.add(tag)
            db.flush()
            tags_by_name[name] = tag

    book.book_tags = [BookTag(book=book, tag=tags_by_name[name]) for name in normalized_names]


def create_book(db: Session, payload: BookCreate, *, current_user_id: int | None = None) -> Book:
    data = payload.model_dump(exclude={"tag_names"})
    _ensure_category_exists(db, data.get("category_id"))
    _ensure_location_exists(db, data.get("location_id"))

    now = _now()
    original_isbn = data.get("original_isbn") or data.get("isbn")
    data["isbn"] = _clean_isbn(data.get("isbn"))
    data["original_isbn"] = original_isbn
    book = Book(
        **data,
        created_by=current_user_id,
        updated_by=current_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(book)
    db.flush()
    _set_book_tags(db, book, payload.tag_names)
    db.commit()
    return get_book_or_error(db, book.id)


def update_book(
    db: Session,
    book_id: int,
    payload: BookUpdate,
    *,
    current_user_id: int | None = None,
) -> Book:
    book = get_book_or_error(db, book_id)
    data = payload.model_dump(exclude_unset=True, exclude={"tag_names"})

    if "category_id" in data:
        _ensure_category_exists(db, data["category_id"])
    if "location_id" in data:
        _ensure_location_exists(db, data["location_id"])
    if "isbn" in data:
        data["original_isbn"] = data["isbn"]
        data["isbn"] = _clean_isbn(data["isbn"])

    for field, value in data.items():
        setattr(book, field, value)

    if payload.tag_names is not None:
        _set_book_tags(db, book, payload.tag_names)

    book.updated_by = current_user_id
    book.updated_at = _now()
    db.commit()
    return get_book_or_error(db, book.id)


def delete_book(db: Session, book_id: int) -> None:
    book = get_book_or_error(db, book_id)
    active_borrow = (
        db.query(BorrowRecord)
        .filter(
            BorrowRecord.book_id == book_id,
            BorrowRecord.returned_at.is_(None),
            BorrowRecord.status != "returned",
        )
        .first()
    )
    if active_borrow is not None:
        raise ApiError("CONFLICT", "图书存在未归还借阅记录，不能删除", status_code=409)

    db.query(ReadingNote).filter(ReadingNote.book_id == book_id).delete(synchronize_session=False)
    db.query(BorrowRecord).filter(BorrowRecord.book_id == book_id).delete(synchronize_session=False)
    db.delete(book)
    db.commit()


def batch_update_books(
    db: Session,
    payload: BookBatchUpdate,
    *,
    current_user_id: int | None = None,
) -> dict[str, Any]:
    update_data = payload.updates.model_dump(exclude_unset=True)
    if not update_data:
        raise ApiError("VALIDATION_ERROR", "updates 不能为空", status_code=422)

    if "category_id" in update_data:
        _ensure_category_exists(db, update_data["category_id"])
    if "location_id" in update_data:
        _ensure_location_exists(db, update_data["location_id"])

    books = _load_book_query(db).filter(Book.id.in_(payload.book_ids)).all()
    found_ids = {book.id for book in books}
    missing_ids = [book_id for book_id in payload.book_ids if book_id not in found_ids]
    if missing_ids:
        raise ApiError("BOOK_NOT_FOUND", "部分图书不存在", status_code=404, details={"book_ids": missing_ids})

    tag_names = update_data.pop("tag_names", None)
    now = _now()
    for book in books:
        for field, value in update_data.items():
            setattr(book, field, value)
        if tag_names is not None:
            _set_book_tags(db, book, tag_names)
        book.updated_by = current_user_id
        book.updated_at = now

    db.commit()
    return {"updated_count": len(books)}


def book_to_response(book: Book) -> dict[str, Any]:
    return {
        "id": book.id,
        "title": book.title,
        "subtitle": book.subtitle,
        "author": book.author,
        "translator": book.translator,
        "publisher": book.publisher,
        "publish_year": book.publish_year,
        "isbn": book.isbn,
        "original_isbn": book.original_isbn,
        "language": book.language,
        "pages": book.pages,
        "price_cents": book.price_cents,
        "binding": book.binding,
        "series": book.series,
        "cover_url": book.cover_url,
        "summary": book.summary,
        "author_intro": book.author_intro,
        "category_id": book.category_id,
        "location_id": book.location_id,
        "status": book.status,
        "read_status": book.read_status,
        "rating": book.rating,
        "is_favorite": book.is_favorite,
        "source": book.source,
        "note": book.note,
        "category": book.category,
        "location": book.location,
        "tags": [book_tag.tag for book_tag in book.book_tags],
        "created_by": book.created_by,
        "updated_by": book.updated_by,
        "created_at": book.created_at,
        "updated_at": book.updated_at,
    }
