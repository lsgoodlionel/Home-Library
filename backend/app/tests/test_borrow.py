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


def _borrow_payload(book_id: int) -> dict:
    return {
        "book_id": book_id,
        "borrower_name": "张三",
        "borrower_contact": "13800138000",
        "borrowed_at": "2026-05-03",
        "due_at": "2026-06-03",
        "note": "请小心保管",
    }


class TestCreateBorrow:
    def test_success(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = _book(db)
        resp = client.post("/api/borrow", json=_borrow_payload(book.id), headers=member_headers)
        assert resp.status_code == 201
        body = resp.json()
        assert body["book_id"] == book.id
        assert body["status"] == "active"
        assert body["borrower_name"] == "张三"
        assert body["book"]["id"] == book.id
        db.refresh(book)
        assert book.status == "borrowed"

    def test_book_not_found(self, client: TestClient, member_headers: dict) -> None:
        resp = client.post("/api/borrow", json=_borrow_payload(99999), headers=member_headers)
        assert resp.status_code == 404

    def test_already_borrowed(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = _book(db)
        client.post("/api/borrow", json=_borrow_payload(book.id), headers=member_headers)
        resp = client.post("/api/borrow", json=_borrow_payload(book.id), headers=member_headers)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"

    def test_no_auth(self, client: TestClient, db: Session) -> None:
        book = _book(db)
        resp = client.post("/api/borrow", json=_borrow_payload(book.id))
        assert resp.status_code == 401

    def test_minimal_payload(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = _book(db)
        resp = client.post(
            "/api/borrow",
            json={"book_id": book.id, "borrower_name": "李四", "borrowed_at": "2026-05-03"},
            headers=member_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["due_at"] is None


class TestReturnBorrow:
    def test_success(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = _book(db)
        record_id = client.post("/api/borrow", json=_borrow_payload(book.id), headers=member_headers).json()["id"]

        resp = client.post(
            f"/api/borrow/{record_id}/return",
            json={"returned_at": "2026-05-20"},
            headers=member_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "returned"
        assert body["returned_at"] == "2026-05-20"
        db.refresh(book)
        assert book.status == "available"

    def test_already_returned(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = _book(db)
        record_id = client.post("/api/borrow", json=_borrow_payload(book.id), headers=member_headers).json()["id"]
        client.post(f"/api/borrow/{record_id}/return", json={"returned_at": "2026-05-20"}, headers=member_headers)
        resp = client.post(f"/api/borrow/{record_id}/return", json={"returned_at": "2026-05-21"}, headers=member_headers)
        assert resp.status_code == 409

    def test_not_found(self, client: TestClient, member_headers: dict) -> None:
        resp = client.post("/api/borrow/99999/return", json={"returned_at": "2026-05-20"}, headers=member_headers)
        assert resp.status_code == 404

    def test_no_auth(self, client: TestClient) -> None:
        resp = client.post("/api/borrow/1/return", json={"returned_at": "2026-05-20"})
        assert resp.status_code == 401


class TestListBorrowRecords:
    def test_records_empty(self, client: TestClient, db: Session, member_headers: dict) -> None:
        resp = client.get("/api/borrow/records", headers=member_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_records_with_data(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book1 = _book(db, "Book A")
        book2 = _book(db, "Book B")
        client.post("/api/borrow", json=_borrow_payload(book1.id), headers=member_headers)
        r2_id = client.post("/api/borrow", json=_borrow_payload(book2.id), headers=member_headers).json()["id"]
        client.post(f"/api/borrow/{r2_id}/return", json={"returned_at": "2026-05-10"}, headers=member_headers)

        resp = client.get("/api/borrow/records", headers=member_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_filter_by_status(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book1 = _book(db, "Book A")
        book2 = _book(db, "Book B")
        client.post("/api/borrow", json=_borrow_payload(book1.id), headers=member_headers)
        r2_id = client.post("/api/borrow", json=_borrow_payload(book2.id), headers=member_headers).json()["id"]
        client.post(f"/api/borrow/{r2_id}/return", json={"returned_at": "2026-05-10"}, headers=member_headers)

        resp = client.get("/api/borrow/records?status=active", headers=member_headers)
        assert resp.status_code == 200
        assert all(i["status"] == "active" for i in resp.json())

    def test_filter_by_book_id(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book1 = _book(db, "Book A")
        book2 = _book(db, "Book B")
        client.post("/api/borrow", json=_borrow_payload(book1.id), headers=member_headers)
        client.post("/api/borrow", json=_borrow_payload(book2.id), headers=member_headers)

        resp = client.get(f"/api/borrow/records?book_id={book1.id}", headers=member_headers)
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["book_id"] == book1.id

    def test_no_auth(self, client: TestClient) -> None:
        resp = client.get("/api/borrow/records")
        assert resp.status_code == 401


class TestListBorrowRecordsPage:
    def test_paginated(self, client: TestClient, db: Session, member_headers: dict) -> None:
        for i in range(3):
            book = _book(db, f"Book {i}")
            client.post("/api/borrow", json=_borrow_payload(book.id), headers=member_headers)

        resp = client.get("/api/borrow/records/page?page=1&page_size=2", headers=member_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert len(body["items"]) == 2
        assert body["page"] == 1
        assert body["page_size"] == 2

    def test_no_auth(self, client: TestClient) -> None:
        resp = client.get("/api/borrow/records/page")
        assert resp.status_code == 401


class TestListActiveBorrows:
    def test_active_empty(self, client: TestClient, db: Session, member_headers: dict) -> None:
        resp = client.get("/api/borrow/active", headers=member_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_active_excludes_returned(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book1 = _book(db, "Book A")
        book2 = _book(db, "Book B")
        client.post("/api/borrow", json=_borrow_payload(book1.id), headers=member_headers)
        r2_id = client.post("/api/borrow", json=_borrow_payload(book2.id), headers=member_headers).json()["id"]
        client.post(f"/api/borrow/{r2_id}/return", json={"returned_at": "2026-05-10"}, headers=member_headers)

        resp = client.get("/api/borrow/active", headers=member_headers)
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["book_id"] == book1.id

    def test_no_auth(self, client: TestClient) -> None:
        resp = client.get("/api/borrow/active")
        assert resp.status_code == 401


class TestGetBorrowRecord:
    def test_get_single(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = _book(db)
        record_id = client.post("/api/borrow", json=_borrow_payload(book.id), headers=member_headers).json()["id"]

        resp = client.get(f"/api/borrow/{record_id}", headers=member_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == record_id

    def test_not_found(self, client: TestClient, member_headers: dict) -> None:
        resp = client.get("/api/borrow/99999", headers=member_headers)
        assert resp.status_code == 404

    def test_no_auth(self, client: TestClient) -> None:
        resp = client.get("/api/borrow/1")
        assert resp.status_code == 401


class TestDeleteBorrowRecord:
    def test_cannot_delete_active(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = _book(db)
        record_id = client.post("/api/borrow", json=_borrow_payload(book.id), headers=member_headers).json()["id"]
        resp = client.delete(f"/api/borrow/{record_id}", headers=member_headers)
        assert resp.status_code == 409

    def test_can_delete_returned(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = _book(db)
        record_id = client.post("/api/borrow", json=_borrow_payload(book.id), headers=member_headers).json()["id"]
        client.post(f"/api/borrow/{record_id}/return", json={"returned_at": "2026-05-10"}, headers=member_headers)
        resp = client.delete(f"/api/borrow/{record_id}", headers=member_headers)
        assert resp.status_code == 204

    def test_no_auth(self, client: TestClient) -> None:
        resp = client.delete("/api/borrow/1")
        assert resp.status_code == 401
