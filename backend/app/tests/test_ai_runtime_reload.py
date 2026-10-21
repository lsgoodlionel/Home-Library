from __future__ import annotations

import asyncio
import threading
from collections.abc import Generator
from dataclasses import replace
from types import SimpleNamespace

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
from app.schemas.ai_setting import OllamaRuntimeStatus
from app.services.ai_health_status_cache import (
    AIHealthStatusCache,
    provider_health_cache,
    provider_model_cache,
)
from app.services.ai_providers import ollama as ollama_provider
from app.services.ai_providers.base import AIProviderRuntime, OllamaProviderRuntimeOptions
from app.services.ai_setting_service import OllamaRuntimeConfig, get_ollama_runtime_config
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
    provider_health_cache.invalidate_all()
    provider_model_cache.invalidate_all()
    yield
    ai_routes._health_status_cache.invalidate_all()
    provider_health_cache.invalidate_all()
    provider_model_cache.invalidate_all()
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
    def __init__(self, runtime, transport=None) -> None:
        del transport
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
    monkeypatch.setattr(ollama_provider, "OllamaClient", _HealthyClient)

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
    monkeypatch.setattr(ollama_provider, "OllamaClient", _HealthyClient)
    assert client.get("/api/ai/health?refresh=true", headers=admin_headers).status_code == 200
    original_runtime = get_ollama_runtime_config(db, admin)

    rejected = (
        _save_server_config(client, admin_headers, default_model="invalid model with spaces"),
        _save_server_config(client, admin_headers, admin_password="wrong-password"),
    )
    assert [response.status_code for response in rejected] == [422, 403]
    assert client.get("/api/ai/health", headers=admin_headers).json()["status"] == "available"

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
    assert client.get("/api/ai/health", headers=weak_key_headers).json()["status"] == "available"

    monkeypatch.setenv("APP_SECRET_KEY", _STRONG_APP_KEY)
    get_settings.cache_clear()

    def fail_database_write(*args, **kwargs):
        raise RuntimeError("synthetic database failure")

    monkeypatch.setattr(system_ai_routes, "update_server_ai_config", fail_database_write)
    database_failure = _save_server_config(client, admin_headers)
    assert database_failure.status_code == 500
    assert client.get("/api/ai/health", headers=admin_headers).json()["status"] == "available"
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
        def __init__(self, runtime, transport=None) -> None:
            super().__init__(runtime, transport=transport)
            seen_base_urls.append(runtime.base_url)

    monkeypatch.setattr(ai_routes, "OllamaClient", CapturingClient)
    monkeypatch.setattr(ollama_provider, "OllamaClient", CapturingClient)
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
    monkeypatch.setattr(ollama_provider, "OllamaClient", fail_if_constructed)
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


def test_health_refresh_uses_one_immutable_runtime_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_runtime = OllamaRuntimeConfig(
        enabled=True,
        base_url="https://old-runtime.example.test/ollama",
        trusted_base_url="https://old-runtime.example.test",
        default_model="old-model",
        connect_timeout_seconds=4,
        read_timeout_seconds=40,
        verify_tls=True,
        access_client_id="old-client-id-marker",
        access_client_secret="old-client-secret-marker",
    )
    new_runtime = replace(
        old_runtime,
        base_url="https://new-runtime.example.test/ollama",
        trusted_base_url="https://new-runtime.example.test",
        default_model="new-model",
        verify_tls=False,
        access_client_id="new-client-id-marker",
        access_client_secret="new-client-secret-marker",
    )
    new_reported_runtime = OllamaRuntimeStatus(
        enabled=True,
        base_url=new_runtime.base_url,
        default_model=new_runtime.default_model,
        connect_timeout_seconds=new_runtime.connect_timeout_seconds,
        read_timeout_seconds=new_runtime.read_timeout_seconds,
        verify_tls=new_runtime.verify_tls,
        access_configured=True,
        uses_access=True,
    )
    runtime_state = {"value": old_runtime}
    first_snapshot_captured = threading.Event()
    release_first_snapshot = threading.Event()
    former_second_read_called = threading.Event()
    probed_runtimes: list[OllamaRuntimeConfig] = []

    def resolve_probe_runtime(*args) -> AIProviderRuntime:
        del args
        snapshot = runtime_state["value"]
        first_snapshot_captured.set()
        assert release_first_snapshot.wait(timeout=2)
        return AIProviderRuntime(
            provider="ollama",
            enabled=snapshot.enabled,
            base_url=snapshot.base_url,
            default_model=snapshot.default_model,
            credential_state="configured",
            connect_timeout_seconds=snapshot.connect_timeout_seconds,
            read_timeout_seconds=snapshot.read_timeout_seconds,
            verify_tls=snapshot.verify_tls,
            ollama=OllamaProviderRuntimeOptions(
                trusted_base_url=snapshot.trusted_base_url,
                access_client_id=snapshot.access_client_id,
                access_client_secret=snapshot.access_client_secret,
                uses_access=True,
            ),
        )

    def resolve_reported_runtime(*args):
        del args
        former_second_read_called.set()
        return SimpleNamespace(ollama_runtime=new_reported_runtime)

    class CapturingClient(_HealthyClient):
        def __init__(self, runtime: OllamaRuntimeConfig) -> None:
            super().__init__(runtime)
            probed_runtimes.append(runtime)

    monkeypatch.setattr(
        ai_routes.runtime_service,
        "resolve_ai_provider_runtime",
        resolve_probe_runtime,
    )
    monkeypatch.setattr(ai_routes, "get_effective_ai_settings", resolve_reported_runtime)
    monkeypatch.setattr(ai_routes, "OllamaClient", CapturingClient)

    user_id = 41
    result: dict[str, AIHealthResponse] = {}
    failures: list[BaseException] = []

    def run_health_refresh() -> None:
        try:
            result["status"] = asyncio.run(
                ai_routes._check_ollama(object(), SimpleNamespace(id=user_id), generate=False)
            )
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(target=run_health_refresh)
    worker.start()
    assert first_snapshot_captured.wait(timeout=2)
    runtime_state["value"] = new_runtime
    release_first_snapshot.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert failures == []
    assert probed_runtimes == [old_runtime]
    assert not former_second_read_called.is_set()
    response = result["status"]
    assert response.ollama_runtime is not None
    assert response.ollama_runtime.base_url == old_runtime.base_url
    assert response.ollama_runtime.default_model == old_runtime.default_model
    assert response.ollama_runtime.verify_tls is old_runtime.verify_tls
    old_fingerprint = ai_routes._runtime_fingerprint(old_runtime)
    new_fingerprint = ai_routes._runtime_fingerprint(new_runtime)
    assert ai_routes._health_status_cache.get(user_id, old_fingerprint) is response
    assert ai_routes._health_status_cache.get(user_id, new_fingerprint).status == "unchecked"
    serialized = response.model_dump_json()
    assert "old-client-id-marker" not in serialized
    assert "old-client-secret-marker" not in serialized
    assert "old-client-id-marker" not in old_fingerprint
    assert "old-client-secret-marker" not in old_fingerprint


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
    monkeypatch.setattr(ollama_provider, "OllamaClient", FailingClient)
    ai_response = client.get("/api/ai/models", headers=admin_headers)
    health_response = client.get("/api/health")
    books_response = client.get("/api/books")

    assert ai_response.status_code == 502
    assert ai_response.json()["error"]["code"] == "AI_UPSTREAM_ERROR"
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    assert books_response.status_code == 200
    assert books_response.json()["total"] == 1
