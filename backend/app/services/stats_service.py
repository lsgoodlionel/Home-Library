"""统计业务逻辑。所有查询使用聚合 SQL，避免 N+1。"""

from __future__ import annotations

from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.models.book import Book
from app.models.borrow_record import BorrowRecord
from app.models.category import Category
from app.models.location import Location
from app.schemas.stats import (
    ActiveBorrowItem,
    CategoryDistItem,
    LocationDistItem,
    OverviewStats,
    ReadingStats,
    RecentBookItem,
    TimelinePoint,
    TimelineStats,
)

_RECENT_LIMIT = 10


def get_overview(db: Session) -> OverviewStats:
    # 单次聚合查询各状态计数
    row = db.query(
        func.count(Book.id).label("total"),
        func.sum(case((Book.status == "available", 1), else_=0)).label("available"),
        func.sum(case((Book.status == "borrowed", 1), else_=0)).label("borrowed"),
        func.sum(case((Book.read_status == "read", 1), else_=0)).label("read"),
        func.sum(case((Book.read_status == "unread", 1), else_=0)).label("unread"),
        func.sum(case((Book.is_favorite == True, 1), else_=0)).label("favorite"),  # noqa: E712
    ).one()

    total = row.total or 0
    available = int(row.available or 0)
    borrowed = int(row.borrowed or 0)
    read = int(row.read or 0)
    unread = int(row.unread or 0)
    favorite = int(row.favorite or 0)

    recent_rows = (
        db.query(Book)
        .order_by(Book.created_at.desc())
        .limit(_RECENT_LIMIT)
        .all()
    )
    recent_books = [RecentBookItem.model_validate(b) for b in recent_rows]

    active_borrow_rows = (
        db.query(BorrowRecord, Book.title)
        .join(Book, BorrowRecord.book_id == Book.id)
        .filter(BorrowRecord.status == "active")
        .order_by(BorrowRecord.borrowed_at.desc())
        .all()
    )
    active_borrows = [
        ActiveBorrowItem(
            id=br.id,
            book_id=br.book_id,
            book_title=title,
            borrower_name=br.borrower_name,
            borrowed_at=str(br.borrowed_at),
            due_at=str(br.due_at) if br.due_at else None,
        )
        for br, title in active_borrow_rows
    ]

    return OverviewStats(
        total_books=total,
        available_books=available,
        borrowed_books=borrowed,
        read_books=read,
        unread_books=unread,
        favorite_books=favorite,
        recent_books=recent_books,
        active_borrows=active_borrows,
    )


def get_categories_dist(db: Session) -> list[CategoryDistItem]:
    # 已关联分类的图书，按分类聚合
    categorized = (
        db.query(
            Category.id.label("category_id"),
            Category.code.label("category_code"),
            Category.name.label("category_name"),
            func.count(Book.id).label("count"),
        )
        .join(Book, Book.category_id == Category.id)
        .group_by(Category.id, Category.code, Category.name)
        .order_by(func.count(Book.id).desc())
        .all()
    )

    # 未分类图书
    uncategorized_count = (
        db.query(func.count(Book.id))
        .filter(Book.category_id.is_(None))
        .scalar()
    ) or 0

    items = [
        CategoryDistItem(
            category_id=r.category_id,
            category_code=r.category_code,
            category_name=r.category_name,
            count=r.count,
        )
        for r in categorized
    ]

    if uncategorized_count > 0:
        items.append(
            CategoryDistItem(
                category_id=None,
                category_code=None,
                category_name="未分类",
                count=uncategorized_count,
            )
        )

    return items


def get_locations_dist(db: Session) -> list[LocationDistItem]:
    # 已关联位置的图书，按位置聚合
    located = (
        db.query(
            Location.id.label("location_id"),
            Location.full_path.label("full_path"),
            Location.room.label("room"),
            Location.shelf.label("shelf"),
            func.count(Book.id).label("count"),
        )
        .join(Book, Book.location_id == Location.id)
        .group_by(Location.id, Location.full_path, Location.room, Location.shelf)
        .order_by(func.count(Book.id).desc())
        .all()
    )

    unlocated_count = (
        db.query(func.count(Book.id))
        .filter(Book.location_id.is_(None))
        .scalar()
    ) or 0

    items = [
        LocationDistItem(
            location_id=r.location_id,
            full_path=r.full_path,
            room=r.room,
            shelf=r.shelf,
            count=r.count,
        )
        for r in located
    ]

    if unlocated_count > 0:
        items.append(
            LocationDistItem(
                location_id=None,
                full_path="未指定",
                room=None,
                shelf=None,
                count=unlocated_count,
            )
        )

    return items


def get_reading_stats(db: Session) -> ReadingStats:
    row = db.query(
        func.sum(case((Book.read_status == "unread", 1), else_=0)).label("unread"),
        func.sum(case((Book.read_status == "reading", 1), else_=0)).label("reading"),
        func.sum(case((Book.read_status == "read", 1), else_=0)).label("read"),
        func.sum(case((Book.read_status == "paused", 1), else_=0)).label("paused"),
    ).one()

    return ReadingStats(
        unread=int(row.unread or 0),
        reading=int(row.reading or 0),
        read=int(row.read or 0),
        paused=int(row.paused or 0),
    )


def get_timeline(db: Session, year: int | None = None) -> TimelineStats:
    # SQLite: strftime('%Y', created_at), strftime('%m', created_at)
    year_expr = func.strftime("%Y", Book.created_at).label("yr")
    month_expr = func.strftime("%m", Book.created_at).label("mo")

    q = db.query(year_expr, month_expr, func.count(Book.id).label("cnt"))

    if year is not None:
        q = q.filter(func.strftime("%Y", Book.created_at) == str(year))

    rows = (
        q.group_by("yr", "mo")
        .order_by("yr", "mo")
        .all()
    )

    points = [
        TimelinePoint(year=int(r.yr), month=int(r.mo), count=r.cnt)
        for r in rows
    ]

    return TimelineStats(points=points)
