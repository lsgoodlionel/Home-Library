from __future__ import annotations

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
    # 1. 取所有分类（含层级关系）
    all_cats = db.query(Category).all()
    cat_by_id: dict[int, Category] = {c.id: c for c in all_cats}

    # 2. 直接分配到各分类的图书数（不含子分类）
    direct_rows = (
        db.query(Category.id, Category.code, Category.name, Category.sort_order, func.count(Book.id))
        .outerjoin(Book, Book.category_id == Category.id)
        .group_by(Category.id, Category.code, Category.name, Category.sort_order)
        .all()
    )
    direct_counts: dict[int, int] = {
        cat_id: int(count) for cat_id, _, _, _, count in direct_rows
    }

    # 3. 向上汇总：每本书的分类计入所有祖先分类
    def ancestors(cat_id: int) -> list[int]:
        """返回包含自身在内的所有祖先分类 id。"""
        result = []
        cid = cat_id
        seen: set[int] = set()
        while cid and cid not in seen:
            seen.add(cid)
            result.append(cid)
            cat = cat_by_id.get(cid)
            cid = cat.parent_id if cat else None
        return result

    rolled_counts: dict[int, int] = {}
    for cat_id, direct in direct_counts.items():
        if direct == 0:
            continue
        for ancestor_id in ancestors(cat_id):
            rolled_counts[ancestor_id] = rolled_counts.get(ancestor_id, 0) + direct

    # 4. 仅保留有书（含子分类汇总）的分类，按数量降序
    cat_info: dict[int, tuple[str, str, int]] = {
        cat_id: (code, name, sort_order)
        for cat_id, code, name, sort_order, _ in direct_rows
    }
    items = [
        DistributionItem(id=cat_id, code=cat_info[cat_id][0], name=cat_info[cat_id][1], count=count)
        for cat_id, count in sorted(rolled_counts.items(), key=lambda x: -x[1])
        if count > 0 and cat_id in cat_info
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
