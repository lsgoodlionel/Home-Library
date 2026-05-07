from __future__ import annotations

from datetime import date, datetime, timezone
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.main import app
from app.models import Base, BorrowRecord, Category, Location, ReadingNote, User


@pytest.fixture()
def db_session(tmp_path) -> Generator[Session, None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'books.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        now = datetime.now(tz=timezone.utc)
        category = Category(code="C91", name="社会学", is_system=True, created_at=now, updated_at=now)
        location = Location(
            room="书房",
            shelf="A 架",
            layer="第 2 层",
            position="右侧",
            full_path="书房 / A 架 / 第 2 层 / 右侧",
            created_at=now,
            updated_at=now,
        )
        db.add_all([category, location])
        db.commit()
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _create_book(client: TestClient, **overrides):
    payload = {
        "title": "乡土中国",
        "subtitle": "",
        "author": "费孝通",
        "translator": "",
        "publisher": "生活·读书·新知三联书店",
        "publish_year": 2013,
        "isbn": "978-7-108-04526-9",
        "language": "zh-CN",
        "pages": 120,
        "price_cents": 2800,
        "binding": "平装",
        "series": "",
        "cover_url": "",
        "summary": "经典社会学作品",
        "author_intro": "",
        "category_id": 1,
        "location_id": 1,
        "tag_names": ["社会学", "中国乡村"],
        "status": "available",
        "read_status": "read",
        "rating": 5,
        "is_favorite": True,
        "note": "",
    }
    payload.update(overrides)
    return client.post("/api/books", json=payload)


def test_create_and_get_book_with_tags(client: TestClient) -> None:
    response = _create_book(client)

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "乡土中国"
    assert data["isbn"] == "9787108045269"
    assert data["category"]["code"] == "C91"
    assert data["location"]["full_path"] == "书房 / A 架 / 第 2 层 / 右侧"
    assert [tag["name"] for tag in data["tags"]] == ["社会学", "中国乡村"]

    detail = client.get(f"/api/books/{data['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == data["id"]


def test_list_books_supports_search_filters_and_pagination(client: TestClient) -> None:
    _create_book(client)
    _create_book(
        client,
        title="经济学原理",
        author="曼昆",
        publisher="北京大学出版社",
        isbn="9787301256909",
        status="borrowed",
        read_status="unread",
        is_favorite=False,
        publish_year=2020,
        tag_names=["经济学"],
    )

    by_title = client.get("/api/books", params={"keyword": "乡土", "page": 1, "page_size": 1})
    assert by_title.status_code == 200
    assert by_title.json()["total"] == 1
    assert by_title.json()["items"][0]["title"] == "乡土中国"

    by_author = client.get("/api/books", params={"keyword": "曼昆"})
    assert by_author.json()["total"] == 1

    by_isbn = client.get("/api/books", params={"keyword": "9787301256909"})
    assert by_isbn.json()["total"] == 1

    filtered = client.get(
        "/api/books",
        params={
            "category_id": 1,
            "location_id": 1,
            "status": "available",
            "read_status": "read",
            "is_favorite": True,
            "publish_year_from": 2010,
            "publish_year_to": 2015,
        },
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["title"] == "乡土中国"


def test_update_book_replaces_tags(client: TestClient) -> None:
    created = _create_book(client).json()

    response = client.patch(
        f"/api/books/{created['id']}",
        json={"title": "乡土中国 修订版", "tag_names": ["社会学", "经典"]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "乡土中国 修订版"
    assert [tag["name"] for tag in data["tags"]] == ["社会学", "经典"]


def test_batch_update_books(client: TestClient) -> None:
    first = _create_book(client).json()
    second = _create_book(client, title="第二本书", isbn="9787100000000").json()

    response = client.post(
        "/api/books/batch-update",
        json={
            "book_ids": [first["id"], second["id"]],
            "updates": {"status": "pending", "category_id": None, "tag_names": ["待整理"]},
        },
    )

    assert response.status_code == 200
    assert response.json() == {"updated_count": 2}
    detail = client.get(f"/api/books/{first['id']}").json()
    assert detail["status"] == "pending"
    assert detail["category"] is None
    assert [tag["name"] for tag in detail["tags"]] == ["待整理"]


def test_delete_book_conflicts_when_active_borrow_exists(client: TestClient, db_session: Session) -> None:
    created = _create_book(client).json()
    db_session.add(
        BorrowRecord(
            book_id=created["id"],
            borrower_name="家庭成员",
            borrowed_at=date.today(),
            status="active",
            created_at=datetime.now(tz=timezone.utc),
            updated_at=datetime.now(tz=timezone.utc),
        )
    )
    db_session.commit()

    response = client.delete(f"/api/books/{created['id']}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_delete_book_without_active_borrow(client: TestClient) -> None:
    created = _create_book(client).json()

    response = client.delete(f"/api/books/{created['id']}")

    assert response.status_code == 204
    assert client.get(f"/api/books/{created['id']}").status_code == 404


def test_delete_book_removes_history_records(client: TestClient, db_session: Session) -> None:
    created = _create_book(client).json()
    user = User(username="note-user", password_hash="x", display_name="笔记用户", role="member", status="active")
    db_session.add(user)
    db_session.flush()
    db_session.add_all(
        [
            BorrowRecord(
                book_id=created["id"],
                borrower_name="家庭成员",
                borrowed_at=date.today(),
                returned_at=date.today(),
                status="returned",
                created_at=datetime.now(tz=timezone.utc),
                updated_at=datetime.now(tz=timezone.utc),
            ),
            ReadingNote(
                book_id=created["id"],
                user_id=user.id,
                title="读书笔记",
                content="已归档",
                created_at=datetime.now(tz=timezone.utc),
                updated_at=datetime.now(tz=timezone.utc),
            ),
        ]
    )
    db_session.commit()

    response = client.delete(f"/api/books/{created['id']}")

    assert response.status_code == 204
    assert db_session.query(BorrowRecord).filter_by(book_id=created["id"]).count() == 0
    assert db_session.query(ReadingNote).filter_by(book_id=created["id"]).count() == 0
