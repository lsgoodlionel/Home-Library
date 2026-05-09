from __future__ import annotations

import re
from collections import Counter

from sqlalchemy import case, extract, func
from sqlalchemy.orm import Session, joinedload

from app.models import Book, BorrowRecord, Category, Location
from app.schemas.stats import (
    ActiveBorrowSummary,
    DistributionItem,
    ReadingStats,
    StatBookSummary,
    StatsOverview,
    TimelinePoint,
)

_AUTHOR_UNKNOWN = "作者未记录"
_AUTHOR_SPLIT_RE = re.compile(r"\s*(?:,|，|、|;|；|/|／|&|\band\b)\s*", re.IGNORECASE)


def _split_author_names(author: str | None) -> list[str]:
    if not author or not author.strip():
        return [_AUTHOR_UNKNOWN]
    names = [name.strip() for name in _AUTHOR_SPLIT_RE.split(author) if name.strip()]
    return names or [_AUTHOR_UNKNOWN]


def get_overview(db: Session) -> StatsOverview:
    counts = db.query(
        func.count(Book.id).label("total_books"),
        func.coalesce(func.sum(case((Book.status == "available", 1), else_=0)), 0).label("available_books"),
        func.coalesce(func.sum(case((Book.status == "borrowed", 1), else_=0)), 0).label("borrowed_books"),
        func.coalesce(func.sum(case((Book.read_status == "read", 1), else_=0)), 0).label("read_books"),
        func.coalesce(func.sum(case((Book.read_status == "unread", 1), else_=0)), 0).label("unread_books"),
        func.coalesce(func.sum(case((Book.is_favorite.is_(True), 1), else_=0)), 0).label("favorite_books"),
    ).one()

    recent_books = (
        db.query(Book)
        .options(joinedload(Book.category), joinedload(Book.location))
        .order_by(Book.created_at.desc(), Book.id.desc())
        .limit(8)
        .all()
    )
    active_borrows = (
        db.query(BorrowRecord)
        .join(Book, BorrowRecord.book_id == Book.id)
        .options(joinedload(BorrowRecord.book))
        .filter(
            BorrowRecord.returned_at.is_(None),
            BorrowRecord.status.in_(["active", "overdue"]),
        )
        .order_by(BorrowRecord.borrowed_at.desc(), BorrowRecord.id.desc())
        .limit(8)
        .all()
    )

    return StatsOverview(
        total_books=int(counts.total_books or 0),
        available_books=int(counts.available_books or 0),
        borrowed_books=int(counts.borrowed_books or 0),
        read_books=int(counts.read_books or 0),
        unread_books=int(counts.unread_books or 0),
        favorite_books=int(counts.favorite_books or 0),
        recent_books=[
            StatBookSummary(
                id=book.id,
                title=book.title,
                author=book.author,
                category_name=book.category.name if book.category else None,
                location_path=book.location.full_path if book.location else None,
                created_at=book.created_at,
            )
            for book in recent_books
        ],
        active_borrows=[
            ActiveBorrowSummary(
                id=record.id,
                book_id=record.book_id,
                book_title=record.book.title if record.book else "",
                borrower_name=record.borrower_name,
                borrowed_at=record.borrowed_at,
                due_at=record.due_at,
            )
            for record in active_borrows
        ],
    )


def get_category_distribution(db: Session) -> list[DistributionItem]:
    rows = (
        db.query(Category.id, Category.code, Category.name, Category.sort_order, func.count(Book.id))
        .outerjoin(Book, Book.category_id == Category.id)
        .group_by(Category.id, Category.code, Category.name, Category.sort_order)
        .having(func.count(Book.id) > 0)
        .order_by(func.count(Book.id).desc(), Category.sort_order.asc(), Category.id.asc())
        .all()
    )
    items = [
        DistributionItem(id=cat_id, code=code, name=name, count=int(count))
        for cat_id, code, name, _sort_order, count in rows
    ]

    uncategorized = db.query(func.count(Book.id)).filter(Book.category_id.is_(None)).scalar() or 0
    if uncategorized:
        items.append(DistributionItem(name="未分类", count=int(uncategorized)))
    return items


def get_location_distribution(db: Session) -> list[DistributionItem]:
    rows = (
        db.query(Location.id, Location.full_path, func.count(Book.id))
        .outerjoin(Book, Book.location_id == Location.id)
        .group_by(Location.id, Location.full_path, Location.sort_order)
        .having(func.count(Book.id) > 0)
        .order_by(func.count(Book.id).desc(), Location.sort_order.asc(), Location.id.asc())
        .all()
    )
    items = [
        DistributionItem(id=location_id, name=full_path, count=int(count))
        for location_id, full_path, count in rows
    ]
    unspecified = db.query(func.count(Book.id)).filter(Book.location_id.is_(None)).scalar() or 0
    if unspecified:
        items.append(DistributionItem(name="未指定", count=int(unspecified)))
    return items


def get_author_distribution(db: Session, *, limit: int = 10) -> list[DistributionItem]:
    counter: Counter[str] = Counter()
    for author, in db.query(Book.author).all():
        counter.update(set(_split_author_names(author)))

    ranked = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return [
        DistributionItem(name=name, count=int(count))
        for name, count in ranked[:limit]
    ]


def get_reading_stats(db: Session) -> ReadingStats:
    rows = db.query(Book.read_status, func.count(Book.id)).group_by(Book.read_status).all()
    counts = {status: int(count) for status, count in rows}
    return ReadingStats(
        unread=counts.get("unread", 0),
        reading=counts.get("reading", 0),
        read=counts.get("read", 0),
        paused=counts.get("paused", 0),
    )


def get_timeline(db: Session, *, year: int | None = None) -> list[TimelinePoint]:
    query = db.query(
        extract("year", Book.created_at).label("year"),
        extract("month", Book.created_at).label("month"),
        func.count(Book.id).label("count"),
    )
    if year is not None:
        query = query.filter(extract("year", Book.created_at) == year)

    rows = (
        query.group_by("year", "month")
        .order_by("year", "month")
        .all()
    )
    return [
        TimelinePoint(period=f"{int(row.year):04d}-{int(row.month):02d}", count=int(row.count))
        for row in rows
        if row.year is not None and row.month is not None
    ]
