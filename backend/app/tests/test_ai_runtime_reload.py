from __future__ import annotations

from collections.abc import Generator
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes import ai as ai_routes
from app.api.routes import system_ai_settings as system_ai_routes
from app.core.config import get_settings
from app.core.security import create_access_token
from app.models import AITask, Book, SystemAISetting, SystemConfigAudit
from app.models.user import User
from app.schemas.ai import (
    AIHealthResponse,
    OllamaModelsResponse,
    OllamaRunningModelsResponse,
    OllamaVersionResponse,
)
from app.services.ai_health_status_cache import AIHealthStatusCache
from app.services.ai_setting_service import get_ollama_runtime_config
from app.services.ollama_client import OllamaUpstreamError
from app.tests.conftest import make_user


_ADMIN_PASSWORD = "task-4-admin-password"
_UPGRADE_PASSWORD = "task-4-upgrade-password"
_STRONG_APP_KEY = "task-4-strong-application-key-value-000001"


@pytest.fixture(autouse=True)
def configured_ai_environment(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("APP_SECRET_KEY", _STRONG_APP_KEY)
    monkeypatch.setenv("UPGRADE_PASSWORD", _UPGRADE_PASSWORD)
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://environment.example.test")
    monkeypatch.setenv("OLLAMA_TRUSTED_BASE_URL", "https://environment.example.test")
    monkeypatch.setenv("OLLAMA_DEFAULT_MODEL", "environment-model")
    get_settings.cache_clear()
    ai_routes._health_status_cache.invalidate_all()
    yield
    ai_routes._health_status_cache.invalidate_all()
    get_settings.cache_clear()


def _headers_for(db: Session, *, role: str) -> tuple[dict[str, str], int]:
    user, _ = make_user(db, role=role, password=_ADMIN_PASSWORD)
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}, user.id


def _server_update(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "enabled": True,
        "default_base_url": "https://environment.example.test",
        "trusted_base_url": "https://environment.example.test",
        "default_model": "environment-model",
        "connect_timeout_seconds": 20.0,
        "read_timeout_seconds": 180.0,
        "verify_tls": True,
        "admin_password": _ADMIN_PASSWORD,
        "upgrade_password": _UPGRADE_PASSWORD,
        "clear_access_credentials": False,
        "confirm_insecure_tls": False,
    }
    payload.update(overrides)
    return payload


def _save_server_config(
    client: TestClient,
    headers: dict[str, str],
    **overrides: object,
):
    return client.put(
        "https://library.test/api/system/ai-config",
        headers=headers,
        json=_server_update(**overrides),
    )


class _HealthyClient:
    def __init__(self, runtime) -> None:
        self.runtime = runtime

    async def version(self) -> OllamaVersionResponse:
        return OllamaVersionResponse(version="0.6.2")

    async def list_models(self) -> OllamaModelsResponse:
        return OllamaModelsResponse(models=[])

    async def running_models(self) -> OllamaRunningModelsResponse:
        return OllamaRunningModelsResponse(models=[])


def test_server_save_invalidates_all_cached_health_states(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_headers, _ = _headers_for(db, role="admin")
    member_headers, _ = _headers_for(db, role="member")
    monkeypatch.setattr(ai_routes, "OllamaClient", _HealthyClient)

    assert client.get("/api/ai/health?refresh=true", headers=admin_headers).status_code == 200
    assert client.get("/api/ai/health?refresh=true", headers=member_headers).status_code == 200

    saved = _save_server_config(client, admin_headers)

    assert saved.status_code == 200
    assert client.get("/api/ai/health", headers=admin_headers).json()["status"] == "unchecked"
    assert client.get("/api/ai/health", headers=member_headers).json()["status"] == "unchecked"


def test_failed_server_mutations_preserve_runtime_and_health_cache(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_headers, admin_id = _headers_for(db, role="admin")
    admin = db.get(User, admin_id)
    assert admin is not None
    monkeypatch.setattr(ai_routes, "OllamaClient", _HealthyClient)
    assert client.get("/api/ai/health?refresh=true", headers=admin_headers).status_code == 200
    original_runtime = get_ollama_runtime_config(db, admin)

    rejected = (
        _save_server_config(client, admin_headers, default_model="invalid model with spaces"),
        _save_server_config(client, admin_headers, admin_password="wrong-password"),
    )
    assert [response.status_code for response in rejected] == [422, 403]
    assert client.get("/api/ai/health", headers=admin_headers).json()["status"] == "healthy"

    monkeypatch.setenv("APP_SECRET_KEY", "dev-secret-change-me-in-production")
    get_settings.cache_clear()
    weak_key_headers = {"Authorization": f"Bearer {create_access_token(admin.id)}"}
    encryption_failure = _save_server_config(
        client,
        weak_key_headers,
        access_client_id="synthetic-client-id",
        access_client_secret="synthetic-client-secret",
    )
    assert encryption_failure.status_code == 400
    assert client.get("/api/ai/health", headers=weak_key_headers).json()["status"] == "healthy"

    monkeypatch.setenv("APP_SECRET_KEY", _STRONG_APP_KEY)
    get_settings.cache_clear()

    def fail_database_write(*args, **kwargs):
        raise RuntimeError("synthetic database failure")

    monkeypatch.setattr(system_ai_routes, "update_server_ai_config", fail_database_write)
    database_failure = _save_server_config(client, admin_headers)
    assert database_failure.status_code == 500
    assert client.get("/api/ai/health", headers=admin_headers).json()["status"] == "healthy"
    assert get_ollama_runtime_config(db, admin) == original_runtime
    assert db.query(SystemAISetting).count() == 0
    assert db.query(SystemConfigAudit).count() == 0


def test_server_reset_changes_next_ai_request_without_process_restart(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_headers, _ = _headers_for(db, role="admin")
    seen_base_urls: list[str] = []

    class CapturingClient(_HealthyClient):
        def __init__(self, runtime) -> None:
            super().__init__(runtime)
            seen_base_urls.append(runtime.base_url)

    monkeypatch.setattr(ai_routes, "OllamaClient", CapturingClient)
    saved = _save_server_config(
        client,
        admin_headers,
        default_base_url="https://database.example.test/ollama",
        trusted_base_url="https://database.example.test",
        default_model="database-model",
    )
    assert saved.status_code == 200
    assert client.get("/api/ai/models", headers=admin_headers).status_code == 200

    reset = client.request(
        "DELETE",
        "https://library.test/api/system/ai-config",
        headers=admin_headers,
        json={
            "admin_password": _ADMIN_PASSWORD,
            "upgrade_password": _UPGRADE_PASSWORD,
            "confirm_reset": True,
        },
    )
    assert reset.status_code == 200
    assert client.get("/api/ai/models", headers=admin_headers).status_code == 200
    assert seen_base_urls == [
        "https://database.example.test/ollama",
        "https://environment.example.test",
    ]


def test_saved_disabled_state_prevents_ollama_client_construction(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_headers, _ = _headers_for(db, role="admin")
    saved = _save_server_config(client, admin_headers, enabled=False)
    assert saved.status_code == 200

    def fail_if_constructed(runtime):
        raise AssertionError(f"disabled runtime constructed client for {runtime.base_url}")

    monkeypatch.setattr(ai_routes, "OllamaClient", fail_if_constructed)
    responses = (
        client.get("/api/ai/health?refresh=true", headers=admin_headers),
        client.get("/api/ai/models", headers=admin_headers),
        client.post("/api/ai/classify-book", headers=admin_headers, json={"title": "乡土中国"}),
        client.post(
            "/api/ai/recommend-book-content",
            headers=admin_headers,
            json={"current": {"title": "乡土中国"}, "candidates": [], "missing_fields": []},
        ),
        client.post("/api/ai/natural-search", headers=admin_headers, json={"query": "乡土社会"}),
    )

    assert [response.status_code for response in responses] == [503] * 5
    assert [response.json()["error"]["code"] for response in responses] == [
        "AI_SERVICE_DISABLED"
    ] * 5
    assert [task.task_type for task in db.query(AITask).order_by(AITask.id)] == [
        "models",
        "classify_book",
        "recommend_book_content",
        "natural_search",
    ]
    assert {task.status for task in db.query(AITask)} == {"failed"}


def test_account_runtime_fingerprint_changes_when_server_security_config_changes(
    db: Session,
) -> None:
    _, user_id = _headers_for(db, role="member")
    user = db.get(User, user_id)
    assert user is not None
    runtime = get_ollama_runtime_config(db, user)
    changed = replace(
        runtime,
        verify_tls=False,
        access_client_id="task-4-client-id-marker",
        access_client_secret="task-4-client-secret-marker",
    )

    first = ai_routes._runtime_fingerprint(runtime)
    second = ai_routes._runtime_fingerprint(changed)

    assert first != second
    assert "task-4-client-id-marker" not in second
    assert "task-4-client-secret-marker" not in second
    cache = AIHealthStatusCache(max_entries=2)
    cache.put(user_id, first, AIHealthResponse(status="healthy"))
    assert cache.get(user_id, second).status == "unchecked"


def test_non_ai_health_and_book_api_survive_server_ai_failure(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_headers, _ = _headers_for(db, role="admin")
    book = Book(title="资本论", author="马克思")
    db.add(book)
    db.commit()

    class FailingClient(_HealthyClient):
        async def list_models(self) -> OllamaModelsResponse:
            raise OllamaUpstreamError("synthetic upstream failure", status_code=503)

    monkeypatch.setattr(ai_routes, "OllamaClient", FailingClient)
    ai_response = client.get("/api/ai/models", headers=admin_headers)
    health_response = client.get("/api/health")
    books_response = client.get("/api/books")

    assert ai_response.status_code == 502
    assert ai_response.json()["error"]["code"] == "AI_UPSTREAM_ERROR"
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    assert books_response.status_code == 200
    assert books_response.json()["total"] == 1
