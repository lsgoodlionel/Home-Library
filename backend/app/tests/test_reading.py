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


def _note_payload(title: str = "第一章") -> dict:
    return {
        "title": title,
        "content": "读书笔记",
        "progress": 20,
        "rating": 4,
        "started_at": "2026-05-01",
        "finished_at": None,
    }


def test_notes_require_auth(client: TestClient, db: Session) -> None:
    book = _book(db)

    response = client.get(f"/api/books/{book.id}/notes")

    assert response.status_code == 401


def test_create_and_list_book_notes(client: TestClient, db: Session, member_headers: dict[str, str]) -> None:
    book = _book(db)

    created = client.post(f"/api/books/{book.id}/notes", json=_note_payload(), headers=member_headers)
    listed = client.get(f"/api/books/{book.id}/notes", headers=member_headers)

    assert created.status_code == 201
    assert created.json()["book"]["title"] == book.title
    assert listed.status_code == 200
    assert listed.json()[0]["title"] == "第一章"


def test_note_owner_can_update(client: TestClient, db: Session) -> None:
    user, _ = make_user(db)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
    book = _book(db)
    note_id = client.post(f"/api/books/{book.id}/notes", json=_note_payload(), headers=headers).json()["id"]

    response = client.patch(f"/api/notes/{note_id}", json={"title": "第二章", "progress": 50}, headers=headers)

    assert response.status_code == 200
    assert response.json()["title"] == "第二章"
    assert response.json()["progress"] == 50


def test_non_owner_cannot_update_note(client: TestClient, db: Session) -> None:
    owner, _ = make_user(db)
    other, _ = make_user(db)
    book = _book(db)
    note = ReadingNote(
        book_id=book.id,
        user_id=owner.id,
        title="私有笔记",
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(note)
    db.commit()

    response = client.patch(
        f"/api/notes/{note.id}",
        json={"title": "试图修改"},
        headers={"Authorization": f"Bearer {create_access_token(other.id)}"},
    )

    assert response.status_code == 403


def test_non_owner_cannot_delete_note(client: TestClient, db: Session) -> None:
    owner, _ = make_user(db)
    other, _ = make_user(db)
    book = _book(db)
    note = ReadingNote(
        book_id=book.id,
        user_id=owner.id,
        title="私有笔记",
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(note)
    db.commit()

    response = client.delete(
        f"/api/notes/{note.id}",
        headers={"Authorization": f"Bearer {create_access_token(other.id)}"},
    )

    assert response.status_code == 403
    assert db.get(ReadingNote, note.id) is not None


def test_list_notes_for_missing_book_returns_404(client: TestClient, member_headers: dict[str, str]) -> None:
    response = client.get("/api/books/99999/notes", headers=member_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BOOK_NOT_FOUND"


def test_admin_can_delete_any_note(client: TestClient, db: Session, admin_headers: dict[str, str]) -> None:
    owner, _ = make_user(db)
    book = _book(db)
    note = ReadingNote(
        book_id=book.id,
        user_id=owner.id,
        title="可由管理员删除",
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(note)
    db.commit()

    response = client.delete(f"/api/notes/{note.id}", headers=admin_headers)

    assert response.status_code == 204
    assert db.get(ReadingNote, note.id) is None


def test_update_read_status(client: TestClient, db: Session, member_headers: dict[str, str]) -> None:
    book = _book(db)

    response = client.patch(
        f"/api/books/{book.id}/read-status",
        json={"read_status": "read"},
        headers=member_headers,
    )

    assert response.status_code == 200
    assert response.json()["read_status"] == "read"
    db.refresh(book)
    assert book.read_status == "read"
