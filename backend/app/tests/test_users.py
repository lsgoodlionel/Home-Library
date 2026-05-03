from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.tests.conftest import make_user


class TestListUsers:
    def test_admin_can_list(self, client: TestClient, db: Session, admin_headers: dict) -> None:
        make_user(db)
        resp = client.get("/api/users", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body
        assert "page_size" in body
        assert body["total"] >= 1

    def test_member_cannot_list(self, client: TestClient, member_headers: dict) -> None:
        resp = client.get("/api/users", headers=member_headers)
        assert resp.status_code == 403

    def test_unauthenticated_cannot_list(self, client: TestClient) -> None:
        resp = client.get("/api/users")
        assert resp.status_code == 401

    def test_pagination(self, client: TestClient, db: Session, admin_headers: dict) -> None:
        resp = client.get("/api/users?page=1&page_size=2", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) <= 2
        assert body["page"] == 1
        assert body["page_size"] == 2

    def test_filter_by_role(self, client: TestClient, db: Session, admin_headers: dict) -> None:
        make_user(db, role="admin")
        resp = client.get("/api/users?role=admin", headers=admin_headers)
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["role"] == "admin"

    def test_no_password_in_response(self, client: TestClient, db: Session, admin_headers: dict) -> None:
        make_user(db)
        resp = client.get("/api/users", headers=admin_headers)
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert "password" not in item
            assert "password_hash" not in item


class TestCreateUser:
    def test_admin_creates_user(self, client: TestClient, admin_headers: dict) -> None:
        resp = client.post(
            "/api/users",
            json={
                "username": "newuser_abc",
                "password": "securepass",
                "display_name": "New User",
                "role": "member",
                "status": "active",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["username"] == "newuser_abc"
        assert body["role"] == "member"
        assert "password" not in body
        assert "password_hash" not in body

    def test_duplicate_username_rejected(self, client: TestClient, db: Session, admin_headers: dict) -> None:
        user, _ = make_user(db)
        resp = client.post(
            "/api/users",
            json={
                "username": user.username,
                "password": "securepass",
                "display_name": "Dup",
                "role": "member",
                "status": "active",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 409

    def test_short_password_rejected(self, client: TestClient, admin_headers: dict) -> None:
        resp = client.post(
            "/api/users",
            json={
                "username": "shortpw_user",
                "password": "ab",
                "display_name": "Short",
                "role": "member",
                "status": "active",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_member_cannot_create(self, client: TestClient, member_headers: dict) -> None:
        resp = client.post(
            "/api/users",
            json={
                "username": "blocked_user",
                "password": "securepass",
                "display_name": "Blocked",
                "role": "member",
                "status": "active",
            },
            headers=member_headers,
        )
        assert resp.status_code == 403


class TestUpdateUser:
    def test_admin_updates_display_name(self, client: TestClient, db: Session, admin_headers: dict) -> None:
        user, _ = make_user(db)
        resp = client.patch(
            f"/api/users/{user.id}",
            json={"display_name": "Updated Name"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Updated Name"

    def test_admin_changes_role(self, client: TestClient, db: Session, admin_headers: dict) -> None:
        user, _ = make_user(db, role="member")
        resp = client.patch(
            f"/api/users/{user.id}",
            json={"role": "guest"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "guest"

    def test_not_found(self, client: TestClient, admin_headers: dict) -> None:
        resp = client.patch("/api/users/999999", json={"display_name": "x"}, headers=admin_headers)
        assert resp.status_code == 404

    def test_member_cannot_update(self, client: TestClient, db: Session, member_headers: dict) -> None:
        user, _ = make_user(db)
        resp = client.patch(f"/api/users/{user.id}", json={"display_name": "x"}, headers=member_headers)
        assert resp.status_code == 403


class TestDeleteUser:
    def test_delete_disables_user(self, client: TestClient, db: Session, admin_headers: dict) -> None:
        user, _ = make_user(db, status="active")
        resp = client.delete(f"/api/users/{user.id}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "disabled"
        db.refresh(user)
        assert user.status == "disabled"

    def test_not_found(self, client: TestClient, admin_headers: dict) -> None:
        resp = client.delete("/api/users/999999", headers=admin_headers)
        assert resp.status_code == 404

    def test_member_cannot_delete(self, client: TestClient, db: Session, member_headers: dict) -> None:
        user, _ = make_user(db)
        resp = client.delete(f"/api/users/{user.id}", headers=member_headers)
        assert resp.status_code == 403
