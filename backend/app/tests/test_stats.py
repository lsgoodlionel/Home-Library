"""统计接口测试。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.main import app
from app.models.base import Base
from app.models.book import Book
from app.models.borrow_record import BorrowRecord
from app.models.category import Category
from app.models.location import Location


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


@pytest.fixture()
def db(tmp_path) -> Generator[Session, None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'stats_test.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _add_category(db: Session, code: str, name: str) -> Category:
    now = _now()
    cat = Category(code=code, name=name, is_system=False, created_at=now, updated_at=now)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def _add_location(db: Session, room: str, shelf: str) -> Location:
    now = _now()
    loc = Location(
        room=room,
        shelf=shelf,
        full_path=f"{room}/{shelf}",
        created_at=now,
        updated_at=now,
    )
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc


def _add_book(
    db: Session,
    title: str,
    *,
    status: str = "available",
    read_status: str = "unread",
    is_favorite: bool = False,
    category_id: int | None = None,
    location_id: int | None = None,
    created_at: datetime | None = None,
) -> Book:
    now = created_at or _now()
    book = Book(
        title=title,
        status=status,
        read_status=read_status,
        is_favorite=is_favorite,
        category_id=category_id,
        location_id=location_id,
        created_at=now,
        updated_at=now,
    )
    db.add(book)
    db.commit()
    db.refresh(book)
    return book


def _add_borrow(db: Session, book_id: int, borrower: str, *, status: str = "active") -> BorrowRecord:
    now = _now()
    br = BorrowRecord(
        book_id=book_id,
        borrower_name=borrower,
        borrowed_at=date.today(),
        status=status,
        created_at=now,
        updated_at=now,
    )
    db.add(br)
    db.commit()
    db.refresh(br)
    return br


# ---------------------------------------------------------------------------
# 空数据库
# ---------------------------------------------------------------------------

class TestEmptyDatabase:
    def test_overview_empty(self, client: TestClient) -> None:
        r = client.get("/api/stats/overview")
        assert r.status_code == 200
        data = r.json()
        assert data["total_books"] == 0
        assert data["available_books"] == 0
        assert data["borrowed_books"] == 0
        assert data["read_books"] == 0
        assert data["unread_books"] == 0
        assert data["favorite_books"] == 0
        assert data["recent_books"] == []
        assert data["active_borrows"] == []

    def test_categories_empty(self, client: TestClient) -> None:
        r = client.get("/api/stats/categories")
        assert r.status_code == 200
        assert r.json() == []

    def test_locations_empty(self, client: TestClient) -> None:
        r = client.get("/api/stats/locations")
        assert r.status_code == 200
        assert r.json() == []

    def test_reading_empty(self, client: TestClient) -> None:
        r = client.get("/api/stats/reading")
        assert r.status_code == 200
        data = r.json()
        assert data == {"unread": 0, "reading": 0, "read": 0, "paused": 0}

    def test_timeline_empty(self, client: TestClient) -> None:
        r = client.get("/api/stats/timeline")
        assert r.status_code == 200
        assert r.json() == {"points": []}


# ---------------------------------------------------------------------------
# 总览
# ---------------------------------------------------------------------------

class TestOverview:
    def test_counts(self, client: TestClient, db: Session) -> None:
        _add_book(db, "书A", status="available", read_status="unread")
        _add_book(db, "书B", status="borrowed", read_status="read")
        _add_book(db, "书C", status="available", read_status="read", is_favorite=True)

        r = client.get("/api/stats/overview")
        assert r.status_code == 200
        data = r.json()
        assert data["total_books"] == 3
        assert data["available_books"] == 2
        assert data["borrowed_books"] == 1
        assert data["read_books"] == 2
        assert data["unread_books"] == 1
        assert data["favorite_books"] == 1

    def test_recent_books_order(self, client: TestClient, db: Session) -> None:
        t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 1, tzinfo=timezone.utc)
        _add_book(db, "旧书", created_at=t1)
        _add_book(db, "新书", created_at=t2)

        data = client.get("/api/stats/overview").json()
        titles = [b["title"] for b in data["recent_books"]]
        assert titles[0] == "新书"
        assert titles[1] == "旧书"

    def test_recent_books_limit(self, client: TestClient, db: Session) -> None:
        for i in range(15):
            _add_book(db, f"书{i}")
        data = client.get("/api/stats/overview").json()
        assert len(data["recent_books"]) <= 10


# ---------------------------------------------------------------------------
# 当前借出
# ---------------------------------------------------------------------------

class TestActiveBorrows:
    def test_active_borrows(self, client: TestClient, db: Session) -> None:
        book = _add_book(db, "测试书", status="borrowed")
        _add_borrow(db, book.id, "张三", status="active")

        data = client.get("/api/stats/overview").json()
        assert len(data["active_borrows"]) == 1
        assert data["active_borrows"][0]["book_title"] == "测试书"
        assert data["active_borrows"][0]["borrower_name"] == "张三"

    def test_returned_borrow_not_in_active(self, client: TestClient, db: Session) -> None:
        book = _add_book(db, "归还书")
        _add_borrow(db, book.id, "李四", status="returned")

        data = client.get("/api/stats/overview").json()
        assert data["active_borrows"] == []


# ---------------------------------------------------------------------------
# 分类分布
# ---------------------------------------------------------------------------

class TestCategoriesDistribution:
    def test_multiple_categories(self, client: TestClient, db: Session) -> None:
        lit = _add_category(db, "I", "文学")
        sci = _add_category(db, "T9", "计算机")
        _add_book(db, "文学书1", category_id=lit.id)
        _add_book(db, "文学书2", category_id=lit.id)
        _add_book(db, "计算机书", category_id=sci.id)

        r = client.get("/api/stats/categories")
        assert r.status_code == 200
        items = r.json()
        counts = {item["category_code"]: item["count"] for item in items}
        assert counts["I"] == 2
        assert counts["T9"] == 1

    def test_uncategorized_books(self, client: TestClient, db: Session) -> None:
        _add_book(db, "无分类书")

        items = client.get("/api/stats/categories").json()
        uncategorized = [i for i in items if i["category_id"] is None]
        assert len(uncategorized) == 1
        assert uncategorized[0]["category_name"] == "未分类"
        assert uncategorized[0]["count"] == 1

    def test_no_uncategorized_entry_when_all_categorized(self, client: TestClient, db: Session) -> None:
        cat = _add_category(db, "B", "哲学")
        _add_book(db, "哲学书", category_id=cat.id)

        items = client.get("/api/stats/categories").json()
        assert all(i["category_id"] is not None for i in items)


# ---------------------------------------------------------------------------
# 位置分布
# ---------------------------------------------------------------------------

class TestLocationsDistribution:
    def test_multiple_locations(self, client: TestClient, db: Session) -> None:
        study = _add_location(db, "书房", "A架")
        living = _add_location(db, "客厅", "电视柜")
        _add_book(db, "书1", location_id=study.id)
        _add_book(db, "书2", location_id=study.id)
        _add_book(db, "书3", location_id=living.id)

        r = client.get("/api/stats/locations")
        assert r.status_code == 200
        items = r.json()
        counts = {item["full_path"]: item["count"] for item in items}
        assert counts["书房/A架"] == 2
        assert counts["客厅/电视柜"] == 1

    def test_unlocated_books(self, client: TestClient, db: Session) -> None:
        _add_book(db, "无位置书")

        items = client.get("/api/stats/locations").json()
        unlocated = [i for i in items if i["location_id"] is None]
        assert len(unlocated) == 1
        assert unlocated[0]["full_path"] == "未指定"
        assert unlocated[0]["count"] == 1


# ---------------------------------------------------------------------------
# 阅读状态
# ---------------------------------------------------------------------------

class TestReadingStats:
    def test_reading_status_distribution(self, client: TestClient, db: Session) -> None:
        _add_book(db, "未读书1", read_status="unread")
        _add_book(db, "未读书2", read_status="unread")
        _add_book(db, "阅读中书", read_status="reading")
        _add_book(db, "已读书", read_status="read")
        _add_book(db, "暂停书", read_status="paused")

        r = client.get("/api/stats/reading")
        assert r.status_code == 200
        data = r.json()
        assert data["unread"] == 2
        assert data["reading"] == 1
        assert data["read"] == 1
        assert data["paused"] == 1


# ---------------------------------------------------------------------------
# 时间趋势
# ---------------------------------------------------------------------------

class TestTimeline:
    def test_timeline_groups_by_month(self, client: TestClient, db: Session) -> None:
        _add_book(db, "一月书", created_at=datetime(2026, 1, 15, tzinfo=timezone.utc))
        _add_book(db, "一月书2", created_at=datetime(2026, 1, 20, tzinfo=timezone.utc))
        _add_book(db, "三月书", created_at=datetime(2026, 3, 5, tzinfo=timezone.utc))

        r = client.get("/api/stats/timeline")
        assert r.status_code == 200
        points = r.json()["points"]
        by_month = {(p["year"], p["month"]): p["count"] for p in points}
        assert by_month[(2026, 1)] == 2
        assert by_month[(2026, 3)] == 1

    def test_timeline_year_filter(self, client: TestClient, db: Session) -> None:
        _add_book(db, "2025书", created_at=datetime(2025, 6, 1, tzinfo=timezone.utc))
        _add_book(db, "2026书", created_at=datetime(2026, 2, 1, tzinfo=timezone.utc))

        r = client.get("/api/stats/timeline?year=2026")
        assert r.status_code == 200
        points = r.json()["points"]
        assert all(p["year"] == 2026 for p in points)
        assert len(points) == 1

    def test_timeline_sorted_ascending(self, client: TestClient, db: Session) -> None:
        _add_book(db, "后书", created_at=datetime(2026, 5, 1, tzinfo=timezone.utc))
        _add_book(db, "前书", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))

        points = client.get("/api/stats/timeline").json()["points"]
        months = [(p["year"], p["month"]) for p in points]
        assert months == sorted(months)
