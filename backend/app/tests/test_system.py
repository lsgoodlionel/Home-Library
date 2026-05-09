from fastapi.testclient import TestClient
from types import SimpleNamespace

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version() -> None:
    response = client.get("/api/version")

    assert response.status_code == 200
    assert response.json() == {
        "app_name": "Home Library",
        "version": "0.1.0",
        "environment": "development",
    }


def test_upgrade_requires_admin(client: TestClient, member_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/upgrade",
        headers=member_headers,
        json={"upgrade_password": "secret"},
    )

    assert response.status_code == 403


def test_upgrade_disabled_without_server_config(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/upgrade",
        headers=admin_headers,
        json={"upgrade_password": "secret"},
    )

    assert response.status_code == 400


def test_upgrade_rejects_wrong_secondary_password(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch,
) -> None:
    from app.api.routes import system

    settings = SimpleNamespace(
        upgrade_password="server-secret",
        upgrade_command="echo ok",
        upgrade_workdir=".",
        upgrade_timeout_seconds=30,
    )
    monkeypatch.setattr(system, "get_settings", lambda: settings)

    response = client.post(
        "/api/upgrade",
        headers=admin_headers,
        json={"upgrade_password": "wrong"},
    )

    assert response.status_code == 403
