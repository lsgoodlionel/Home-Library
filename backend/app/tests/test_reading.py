from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Book, ReadingNote
from app.tests.conftest import make_user


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _book(db: Session) -> Book:
    now = _now()
    book = Book(title="围城", author="钱锺书", status="available", read_status="unread", created_at=now, updated_at=now)
    db.add(book)
    db.commit()
    db.refresh(book)
    return book


def _note_payload(title: str = "第一章笔记") -> dict:
    return {
        "title": title,
        "content": "这是 **Markdown** 笔记内容。",
        "progress": 30,
        "rating": 4,
        "started_at": "2026-05-01",
    }


class TestGetBookNotes:
    def test_empty(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = _book(db)
        resp = client.get(f"/api/books/{book.id}/notes", headers=member_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_book_not_found(self, client: TestClient, member_headers: dict) -> None:
        resp = client.get("/api/books/99999/notes", headers=member_headers)
        assert resp.status_code == 404

    def test_no_auth(self, client: TestClient, db: Session) -> None:
        book = _book(db)
        resp = client.get(f"/api/books/{book.id}/notes")
        assert resp.status_code == 401


class TestCreateNote:
    def test_success(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = _book(db)
        resp = client.post(f"/api/books/{book.id}/notes", json=_note_payload(), headers=member_headers)
        assert resp.status_code == 201
        body = resp.json()
        assert body["book_id"] == book.id
        assert body["title"] == "第一章笔记"
        assert body["progress"] == 30
        assert body["rating"] == 4
        assert "user_id" in body

    def test_book_not_found(self, client: TestClient, member_headers: dict) -> None:
        resp = client.post("/api/books/99999/notes", json=_note_payload(), headers=member_headers)
        assert resp.status_code == 404

    def test_no_auth(self, client: TestClient, db: Session) -> None:
        book = _book(db)
        resp = client.post(f"/api/books/{book.id}/notes", json=_note_payload())
        assert resp.status_code == 401

    def test_progress_out_of_range(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = _book(db)
        bad = {**_note_payload(), "progress": 150}
        resp = client.post(f"/api/books/{book.id}/notes", json=bad, headers=member_headers)
        assert resp.status_code == 422

    def test_rating_out_of_range(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = _book(db)
        bad = {**_note_payload(), "rating": 6}
        resp = client.post(f"/api/books/{book.id}/notes", json=bad, headers=member_headers)
        assert resp.status_code == 422

    def test_multiple_notes_same_book(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = _book(db)
        client.post(f"/api/books/{book.id}/notes", json=_note_payload("笔记一"), headers=member_headers)
        client.post(f"/api/books/{book.id}/notes", json=_note_payload("笔记二"), headers=member_headers)
        resp = client.get(f"/api/books/{book.id}/notes", headers=member_headers)
        assert len(resp.json()) == 2


class TestUpdateNote:
    def test_owner_can_update(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = _book(db)
        note_id = client.post(f"/api/books/{book.id}/notes", json=_note_payload(), headers=member_headers).json()["id"]

        resp = client.patch(f"/api/notes/{note_id}", json={"title": "更新后标题", "progress": 60}, headers=member_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "更新后标题"
        assert body["progress"] == 60

    def test_other_user_cannot_update(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = _book(db)
        note_id = client.post(f"/api/books/{book.id}/notes", json=_note_payload(), headers=member_headers).json()["id"]

        other_user, _ = make_user(db, role="member")
        other_headers = {"Authorization": f"Bearer {create_access_token(other_user.id)}"}

        resp = client.patch(f"/api/notes/{note_id}", json={"title": "恶意修改"}, headers=other_headers)
        assert resp.status_code == 403

    def test_admin_can_update_any(self, client: TestClient, db: Session, member_headers: dict, admin_headers: dict) -> None:
        book = _book(db)
        note_id = client.post(f"/api/books/{book.id}/notes", json=_note_payload(), headers=member_headers).json()["id"]

        resp = client.patch(f"/api/notes/{note_id}", json={"title": "管理员修改"}, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["title"] == "管理员修改"

    def test_not_found(self, client: TestClient, member_headers: dict) -> None:
        resp = client.patch("/api/notes/99999", json={"title": "x"}, headers=member_headers)
        assert resp.status_code == 404

    def test_no_auth(self, client: TestClient) -> None:
        resp = client.patch("/api/notes/1", json={"title": "x"})
        assert resp.status_code == 401


class TestDeleteNote:
    def test_owner_can_delete(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = _book(db)
        note_id = client.post(f"/api/books/{book.id}/notes", json=_note_payload(), headers=member_headers).json()["id"]

        resp = client.delete(f"/api/notes/{note_id}", headers=member_headers)
        assert resp.status_code == 204
        assert client.get(f"/api/books/{book.id}/notes", headers=member_headers).json() == []

    def test_other_user_cannot_delete(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = _book(db)
        note_id = client.post(f"/api/books/{book.id}/notes", json=_note_payload(), headers=member_headers).json()["id"]

        other_user, _ = make_user(db, role="member")
        other_headers = {"Authorization": f"Bearer {create_access_token(other_user.id)}"}

        resp = client.delete(f"/api/notes/{note_id}", headers=other_headers)
        assert resp.status_code == 403

    def test_admin_can_delete_any(self, client: TestClient, db: Session, member_headers: dict, admin_headers: dict) -> None:
        book = _book(db)
        note_id = client.post(f"/api/books/{book.id}/notes", json=_note_payload(), headers=member_headers).json()["id"]

        resp = client.delete(f"/api/notes/{note_id}", headers=admin_headers)
        assert resp.status_code == 204

    def test_not_found(self, client: TestClient, member_headers: dict) -> None:
        resp = client.delete("/api/notes/99999", headers=member_headers)
        assert resp.status_code == 404

    def test_no_auth(self, client: TestClient) -> None:
        resp = client.delete("/api/notes/1")
        assert resp.status_code == 401


class TestUpdateReadStatus:
    def test_success(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = _book(db)
        resp = client.patch(f"/api/books/{book.id}/read-status", json={"read_status": "reading"}, headers=member_headers)
        assert resp.status_code == 200
        assert resp.json()["read_status"] == "reading"
        db.refresh(book)
        assert book.read_status == "reading"

    def test_all_valid_statuses(self, client: TestClient, db: Session, member_headers: dict) -> None:
        for status in ("unread", "reading", "read", "paused"):
            book = _book(db)
            resp = client.patch(f"/api/books/{book.id}/read-status", json={"read_status": status}, headers=member_headers)
            assert resp.status_code == 200
            assert resp.json()["read_status"] == status

    def test_book_not_found(self, client: TestClient, member_headers: dict) -> None:
        resp = client.patch("/api/books/99999/read-status", json={"read_status": "read"}, headers=member_headers)
        assert resp.status_code == 404

    def test_invalid_status(self, client: TestClient, db: Session, member_headers: dict) -> None:
        book = _book(db)
        resp = client.patch(f"/api/books/{book.id}/read-status", json={"read_status": "invalid"}, headers=member_headers)
        assert resp.status_code == 422

    def test_no_auth(self, client: TestClient, db: Session) -> None:
        book = _book(db)
        resp = client.patch(f"/api/books/{book.id}/read-status", json={"read_status": "read"})
        assert resp.status_code == 401
