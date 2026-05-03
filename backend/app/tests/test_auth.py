from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.tests.conftest import make_user


class TestLogin:
    def test_success(self, client: TestClient, db: Session) -> None:
        user, password = make_user(db, role="member")
        resp = client.post("/api/auth/login", json={"username": user.username, "password": password})
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] > 0
        assert body["user"]["id"] == user.id
        assert body["user"]["username"] == user.username
        assert body["user"]["role"] == user.role

    def test_login_token_can_fetch_current_user(self, client: TestClient, db: Session) -> None:
        user, password = make_user(db, role="member")

        login = client.post("/api/auth/login", json={"username": user.username, "password": password})
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})

        assert me.status_code == 200
        assert me.json()["id"] == user.id
        assert me.json()["username"] == user.username

    def test_wrong_password(self, client: TestClient, db: Session) -> None:
        user, _ = make_user(db)
        resp = client.post("/api/auth/login", json={"username": user.username, "password": "wrongpass"})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"

    def test_unknown_user(self, client: TestClient) -> None:
        resp = client.post("/api/auth/login", json={"username": "nobody", "password": "pass"})
        assert resp.status_code == 401

    def test_disabled_user(self, client: TestClient, db: Session) -> None:
        user, password = make_user(db, status="disabled")
        resp = client.post("/api/auth/login", json={"username": user.username, "password": password})
        assert resp.status_code == 401

    def test_missing_fields(self, client: TestClient) -> None:
        resp = client.post("/api/auth/login", json={"username": "admin"})
        assert resp.status_code == 422


class TestLogout:
    def test_logout(self, client: TestClient) -> None:
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


class TestMe:
    def test_me_authenticated(self, client: TestClient, db: Session, admin_headers: dict) -> None:
        resp = client.get("/api/auth/me", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "id" in body
        assert "username" in body
        assert "role" in body
        assert "status" in body
        assert "password_hash" not in body

    def test_me_no_token(self, client: TestClient) -> None:
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_invalid_token(self, client: TestClient) -> None:
        resp = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
        assert resp.status_code == 401

    def test_me_disabled_user(self, client: TestClient, db: Session) -> None:
        from app.core.security import create_access_token
        user, _ = make_user(db, status="disabled")
        token = create_access_token(user.id)
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_last_login_updated_after_login(self, client: TestClient, db: Session) -> None:
        user, password = make_user(db)
        assert user.last_login_at is None
        client.post("/api/auth/login", json={"username": user.username, "password": password})
        db.refresh(user)
        assert user.last_login_at is not None
