from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Book, BorrowRecord


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _book(db: Session, title: str = "乡土中国") -> Book:
    now = _now()
    book = Book(title=title, author="费孝通", status="available", read_status="unread", created_at=now, updated_at=now)
    db.add(book)
    db.commit()
    db.refresh(book)
    return book


def _payload(book_id: int, borrower_name: str = "张三") -> dict:
    return {
        "book_id": book_id,
        "borrower_name": borrower_name,
        "borrower_contact": "13800000000",
        "borrowed_at": "2026-05-01",
        "due_at": "2026-06-01",
        "note": "线下借出",
    }


def test_borrow_requires_auth(client: TestClient, db: Session) -> None:
    book = _book(db)

    response = client.post("/api/borrow", json=_payload(book.id))

    assert response.status_code == 401


def test_create_borrow_marks_book_borrowed(client: TestClient, db: Session, member_headers: dict[str, str]) -> None:
    book = _book(db)

    response = client.post("/api/borrow", json=_payload(book.id), headers=member_headers)

    assert response.status_code == 201
    data = response.json()
    assert data["book_id"] == book.id
    assert data["book"]["title"] == book.title
    assert data["status"] == "active"
    db.refresh(book)
    assert book.status == "borrowed"


def test_create_borrow_conflicts_when_active_exists(client: TestClient, db: Session, member_headers: dict[str, str]) -> None:
    book = _book(db)
    assert client.post("/api/borrow", json=_payload(book.id), headers=member_headers).status_code == 201

    response = client.post("/api/borrow", json=_payload(book.id, "李四"), headers=member_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_return_borrow_marks_book_available(client: TestClient, db: Session, member_headers: dict[str, str]) -> None:
    book = _book(db)
    created = client.post("/api/borrow", json=_payload(book.id), headers=member_headers).json()

    response = client.post(
        f"/api/borrow/{created['id']}/return",
        json={"returned_at": "2026-05-10", "note": "已归还"},
        headers=member_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "returned"
    db.refresh(book)
    assert book.status == "available"


def test_return_borrow_twice_returns_conflict(client: TestClient, db: Session, member_headers: dict[str, str]) -> None:
    book = _book(db)
    created = client.post("/api/borrow", json=_payload(book.id), headers=member_headers).json()
    return_payload = {"returned_at": "2026-05-10", "note": "已归还"}

    first = client.post(f"/api/borrow/{created['id']}/return", json=return_payload, headers=member_headers)
    second = client.post(f"/api/borrow/{created['id']}/return", json=return_payload, headers=member_headers)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "CONFLICT"


def test_list_borrow_records_filters(client: TestClient, db: Session, member_headers: dict[str, str]) -> None:
    book_a = _book(db, "A")
    book_b = _book(db, "B")
    client.post("/api/borrow", json=_payload(book_a.id, "张三"), headers=member_headers)
    client.post("/api/borrow", json=_payload(book_b.id, "李四"), headers=member_headers)

    response = client.get("/api/borrow/records", params={"borrower_name": "张"}, headers=member_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["borrower_name"] == "张三"


def test_delete_active_borrow_is_rejected(client: TestClient, db: Session, member_headers: dict[str, str]) -> None:
    book = _book(db)
    created = client.post("/api/borrow", json=_payload(book.id), headers=member_headers).json()

    response = client.delete(f"/api/borrow/{created['id']}", headers=member_headers)

    assert response.status_code == 409


def test_delete_returned_borrow(client: TestClient, db: Session, member_headers: dict[str, str]) -> None:
    book = _book(db)
    record = BorrowRecord(
        book_id=book.id,
        borrower_name="张三",
        borrowed_at=date(2026, 5, 1),
        returned_at=date(2026, 5, 2),
        status="returned",
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(record)
    db.commit()

    response = client.delete(f"/api/borrow/{record.id}", headers=member_headers)

    assert response.status_code == 204
    assert db.get(BorrowRecord, record.id) is None
