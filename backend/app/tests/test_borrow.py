"""Tests for borrow routes (Task I)."""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.book import Book
from app.models.borrow_record import BorrowRecord
from app.tests.conftest import make_user
from app.core.security import create_access_token


def make_book(db: Session, *, title: str = "Test Book", status: str = "available") -> Book:
    from datetime import datetime, timezone
    now = datetime.now(tz=timezone.utc)
    book = Book(
        title=title,
        status=status,
        read_status="unread",
        is_favorite=False,
        source="manual",
        created_at=now,
        updated_at=now,
    )
    db.add(book)
    db.commit()
    db.refresh(book)
    return book


def borrow_payload(book_id: int) -> dict:
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
        book = make_book(db)
        resp = client.post("/api/borrow", json=borrow_payload(book.id), headers=member_headers)
        assert resp.status_code == 201
        body = resp.json()
        assert body["book_id"] == book.id
        assert body["status"] == "active"
        assert body["borrower_name"] == "张三"
        assert body["book"]["id"] == book.id
        # book status should be updated
        db.refresh(book)
        assert book.status == "borrowed"

    def test_book_not_found(self, client: TestClient, db: Session, member_headers: dict) -> None:
        resp = client.post("/api/borrow", json=borrow_payload(99999), headers=member_headers)
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    def test_already_borrowed(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = make_book(db)
        client.post("/api/borrow", json=borrow_payload(book.id), headers=member_headers)
        resp = client.post("/api/borrow", json=borrow_payload(book.id), headers=member_headers)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"

    def test_no_auth(self, client: TestClient, db: Session) -> None:
        book = make_book(db)
        resp = client.post("/api/borrow", json=borrow_payload(book.id))
        assert resp.status_code == 401

    def test_minimal_payload(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = make_book(db)
        resp = client.post(
            "/api/borrow",
            json={"book_id": book.id, "borrower_name": "李四", "borrowed_at": "2026-05-03"},
            headers=member_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["due_at"] is None


class TestReturnBorrow:
    def test_success(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = make_book(db)
        create_resp = client.post("/api/borrow", json=borrow_payload(book.id), headers=member_headers)
        record_id = create_resp.json()["id"]

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
        book = make_book(db)
        create_resp = client.post("/api/borrow", json=borrow_payload(book.id), headers=member_headers)
        record_id = create_resp.json()["id"]
        client.post(f"/api/borrow/{record_id}/return", json={"returned_at": "2026-05-20"}, headers=member_headers)
        resp = client.post(f"/api/borrow/{record_id}/return", json={"returned_at": "2026-05-21"}, headers=member_headers)
        assert resp.status_code == 409

    def test_not_found(self, client: TestClient, db: Session, member_headers: dict) -> None:
        resp = client.post("/api/borrow/99999/return", json={"returned_at": "2026-05-20"}, headers=member_headers)
        assert resp.status_code == 404

    def test_no_auth(self, client: TestClient, db: Session) -> None:
        resp = client.post("/api/borrow/1/return", json={"returned_at": "2026-05-20"})
        assert resp.status_code == 401


class TestListBorrowRecords:
    def test_records_empty(self, client: TestClient, db: Session, member_headers: dict) -> None:
        resp = client.get("/api/borrow/records", headers=member_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_records_with_data(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book1 = make_book(db, title="Book A")
        book2 = make_book(db, title="Book B")
        client.post("/api/borrow", json=borrow_payload(book1.id), headers=member_headers)
        r2 = client.post("/api/borrow", json=borrow_payload(book2.id), headers=member_headers)
        record2_id = r2.json()["id"]
        client.post(f"/api/borrow/{record2_id}/return", json={"returned_at": "2026-05-10"}, headers=member_headers)

        resp = client.get("/api/borrow/records", headers=member_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_filter_by_status(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book1 = make_book(db, title="Book A")
        book2 = make_book(db, title="Book B")
        client.post("/api/borrow", json=borrow_payload(book1.id), headers=member_headers)
        r2 = client.post("/api/borrow", json=borrow_payload(book2.id), headers=member_headers)
        client.post(f"/api/borrow/{r2.json()['id']}/return", json={"returned_at": "2026-05-10"}, headers=member_headers)

        resp = client.get("/api/borrow/records?status=active", headers=member_headers)
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert all(i["status"] == "active" for i in items)

    def test_filter_by_book_id(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book1 = make_book(db, title="Book A")
        book2 = make_book(db, title="Book B")
        client.post("/api/borrow", json=borrow_payload(book1.id), headers=member_headers)
        client.post("/api/borrow", json=borrow_payload(book2.id), headers=member_headers)

        resp = client.get(f"/api/borrow/records?book_id={book1.id}", headers=member_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["book_id"] == book1.id

    def test_no_auth(self, client: TestClient) -> None:
        resp = client.get("/api/borrow/records")
        assert resp.status_code == 401


class TestListActiveBorrows:
    def test_active_empty(self, client: TestClient, db: Session, member_headers: dict) -> None:
        resp = client.get("/api/borrow/active", headers=member_headers)
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_active_excludes_returned(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book1 = make_book(db, title="Book A")
        book2 = make_book(db, title="Book B")
        client.post("/api/borrow", json=borrow_payload(book1.id), headers=member_headers)
        r2 = client.post("/api/borrow", json=borrow_payload(book2.id), headers=member_headers)
        client.post(f"/api/borrow/{r2.json()['id']}/return", json={"returned_at": "2026-05-10"}, headers=member_headers)

        resp = client.get("/api/borrow/active", headers=member_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["book_id"] == book1.id

    def test_no_auth(self, client: TestClient) -> None:
        resp = client.get("/api/borrow/active")
        assert resp.status_code == 401


class TestGetBorrowRecord:
    def test_get_single(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = make_book(db)
        create_resp = client.post("/api/borrow", json=borrow_payload(book.id), headers=member_headers)
        record_id = create_resp.json()["id"]

        resp = client.get(f"/api/borrow/{record_id}", headers=member_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == record_id

    def test_not_found(self, client: TestClient, member_headers: dict) -> None:
        resp = client.get("/api/borrow/99999", headers=member_headers)
        assert resp.status_code == 404
