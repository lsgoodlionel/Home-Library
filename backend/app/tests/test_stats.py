from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Book, BorrowRecord, Category, Location


def _dt(year: int, month: int, day: int = 1) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def _seed_refs(db: Session) -> tuple[Category, Location]:
    category = Category(code="I247", name="中国小说", sort_order=1, created_at=_dt(2026, 1), updated_at=_dt(2026, 1))
    location = Location(
        room="书房",
        shelf="A 架",
        layer="1 层",
        position=None,
        full_path="书房 / A 架 / 1 层",
        sort_order=1,
        created_at=_dt(2026, 1),
        updated_at=_dt(2026, 1),
    )
    db.add_all([category, location])
    db.commit()
    db.refresh(category)
    db.refresh(location)
    return category, location


def _book(
    db: Session,
    title: str,
    *,
    category_id: int | None = None,
    location_id: int | None = None,
    status: str = "available",
    read_status: str = "unread",
    is_favorite: bool = False,
    created_at: datetime | None = None,
) -> Book:
    created = created_at or _dt(2026, 5)
    book = Book(
        title=title,
        author="作者",
        category_id=category_id,
        location_id=location_id,
        status=status,
        read_status=read_status,
        is_favorite=is_favorite,
        created_at=created,
        updated_at=created,
    )
    db.add(book)
    db.commit()
    db.refresh(book)
    return book


def test_stats_empty_database(client: TestClient) -> None:
    overview = client.get("/api/stats/overview")
    categories = client.get("/api/stats/categories")
    locations = client.get("/api/stats/locations")
    reading = client.get("/api/stats/reading")
    timeline = client.get("/api/stats/timeline")

    assert overview.status_code == 200
    assert overview.json()["total_books"] == 0
    assert overview.json()["recent_books"] == []
    assert categories.json() == []
    assert locations.json() == []
    assert reading.json() == {"unread": 0, "reading": 0, "read": 0, "paused": 0}
    assert timeline.json() == []


def test_overview_counts_and_summaries(client: TestClient, db: Session) -> None:
    category, location = _seed_refs(db)
    borrowed = _book(
        db,
        "借出的书",
        category_id=category.id,
        location_id=location.id,
        status="borrowed",
        read_status="read",
        is_favorite=True,
        created_at=_dt(2026, 5, 2),
    )
    _book(db, "未读的书", read_status="unread", created_at=_dt(2026, 5, 1))
    db.add(
        BorrowRecord(
            book_id=borrowed.id,
            borrower_name="张三",
            borrowed_at=date(2026, 5, 3),
            due_at=date(2026, 6, 3),
            status="active",
            created_at=_dt(2026, 5, 3),
            updated_at=_dt(2026, 5, 3),
        )
    )
    db.commit()

    response = client.get("/api/stats/overview")

    assert response.status_code == 200
    data = response.json()
    assert data["total_books"] == 2
    assert data["available_books"] == 1
    assert data["borrowed_books"] == 1
    assert data["read_books"] == 1
    assert data["unread_books"] == 1
    assert data["favorite_books"] == 1
    assert data["recent_books"][0]["title"] == "借出的书"
    assert data["recent_books"][0]["category_name"] == "中国小说"
    assert data["active_borrows"][0]["book_title"] == "借出的书"


def test_category_distribution_includes_uncategorized(client: TestClient, db: Session) -> None:
    category, _location = _seed_refs(db)
    _book(db, "有分类", category_id=category.id)
    _book(db, "无分类")

    response = client.get("/api/stats/categories")

    assert response.status_code == 200
    items = {item["name"]: item["count"] for item in response.json()}
    assert items["中国小说"] == 1
    assert items["未分类"] == 1


def test_category_distribution_does_not_roll_child_counts_to_parent(
    client: TestClient, db: Session
) -> None:
    parent, _location = _seed_refs(db)
    child = Category(
        code="I2475",
        name="当代小说",
        parent_id=parent.id,
        sort_order=1,
        is_system=True,
        created_at=_dt(2026, 1),
        updated_at=_dt(2026, 1),
    )
    db.add(child)
    db.commit()
    db.refresh(child)
    _book(db, "父类图书", category_id=parent.id)
    _book(db, "子类图书", category_id=child.id)

    response = client.get("/api/stats/categories")

    assert response.status_code == 200
    items = {item["name"]: item["count"] for item in response.json()}
    assert items["中国小说"] == 1
    assert items["当代小说"] == 1
    assert sum(items.values()) == 2


def test_location_distribution_includes_unspecified(client: TestClient, db: Session) -> None:
    _category, location = _seed_refs(db)
    _book(db, "有位置", location_id=location.id)
    _book(db, "无位置")

    response = client.get("/api/stats/locations")

    assert response.status_code == 200
    items = {item["name"]: item["count"] for item in response.json()}
    assert items["书房 / A 架 / 1 层"] == 1
    assert items["未指定"] == 1


def test_reading_stats_four_states(client: TestClient, db: Session) -> None:
    _book(db, "未读", read_status="unread")
    _book(db, "阅读中", read_status="reading")
    _book(db, "已读", read_status="read")
    _book(db, "暂停", read_status="paused")

    response = client.get("/api/stats/reading")

    assert response.status_code == 200
    assert response.json() == {"unread": 1, "reading": 1, "read": 1, "paused": 1}


def test_timeline_groups_by_month_and_filters_year(client: TestClient, db: Session) -> None:
    _book(db, "2025", created_at=_dt(2025, 12))
    _book(db, "2026-01 A", created_at=_dt(2026, 1))
    _book(db, "2026-01 B", created_at=_dt(2026, 1, 2))
    _book(db, "2026-02", created_at=_dt(2026, 2))

    all_response = client.get("/api/stats/timeline")
    year_response = client.get("/api/stats/timeline", params={"year": 2026})

    assert all_response.status_code == 200
    assert all_response.json() == [
        {"period": "2025-12", "count": 1},
        {"period": "2026-01", "count": 2},
        {"period": "2026-02", "count": 1},
    ]
    assert year_response.status_code == 200
    assert year_response.json() == [
        {"period": "2026-01", "count": 2},
        {"period": "2026-02", "count": 1},
    ]
