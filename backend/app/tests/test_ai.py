from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import AITask
from app.models.user import User
from app.services.ai_setting_service import get_effective_ai_settings, get_ollama_runtime_config


OLLAMA_ENVIRONMENT_VARIABLES = (
    "HOME_LIBRARY_OLLAMA_ENABLED",
    "OLLAMA_ENABLED",
    "HOME_LIBRARY_OLLAMA_BASE_URL",
    "OLLAMA_BASE_URL",
    "HOME_LIBRARY_OLLAMA_DEFAULT_MODEL",
    "OLLAMA_DEFAULT_MODEL",
    "HOME_LIBRARY_OLLAMA_CONNECT_TIMEOUT_SECONDS",
    "OLLAMA_CONNECT_TIMEOUT_SECONDS",
    "HOME_LIBRARY_OLLAMA_READ_TIMEOUT_SECONDS",
    "OLLAMA_READ_TIMEOUT_SECONDS",
    "HOME_LIBRARY_OLLAMA_TIMEOUT_SECONDS",
    "OLLAMA_TIMEOUT_SECONDS",
    "HOME_LIBRARY_OLLAMA_VERIFY_TLS",
    "OLLAMA_VERIFY_TLS",
    "HOME_LIBRARY_OLLAMA_CF_ACCESS_CLIENT_ID",
    "OLLAMA_CF_ACCESS_CLIENT_ID",
    "HOME_LIBRARY_OLLAMA_CF_ACCESS_CLIENT_SECRET",
    "OLLAMA_CF_ACCESS_CLIENT_SECRET",
)


def _clear_ollama_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in OLLAMA_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()


def _mock_ollama(monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]) -> None:
    real_client = httpx.Client
    transport = httpx.MockTransport(handler)

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("app.services.ollama_service.httpx.Client", client_factory)


def _generate_response(payload: dict) -> dict:
    return {"response": json.dumps(payload, ensure_ascii=False)}


def _classify_payload() -> dict:
    return {
        "title": "乡土中国",
        "author": "费孝通",
        "publisher": "三联书店",
        "summary": "社会学经典作品",
        "model": "qwen2.5",
    }


def test_ollama_runtime_defaults_to_remote_disabled_configuration(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_ollama_environment(monkeypatch)

    runtime = get_ollama_runtime_config(db, None)
    get_settings.cache_clear()

    assert runtime.enabled is False
    assert runtime.base_url == "https://openclaw.lsgood.cn"
    assert runtime.trusted_base_url == "https://openclaw.lsgood.cn"
    assert runtime.default_model == "qwen3.5:4b"
    assert runtime.connect_timeout_seconds == 20.0
    assert runtime.read_timeout_seconds == 180.0
    assert runtime.verify_tls is True
    assert runtime.access_client_id == ""
    assert runtime.access_client_secret == ""


def test_ollama_runtime_uses_saved_account_url_without_access_headers(
    client: TestClient,
    db: Session,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_ollama_environment(monkeypatch)
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    monkeypatch.setenv("OLLAMA_CF_ACCESS_CLIENT_ID", "runtime-client-id")
    monkeypatch.setenv("OLLAMA_CF_ACCESS_CLIENT_SECRET", "runtime-client-secret")

    response = client.put(
        "/api/ai/config",
        headers=admin_headers,
        json={
            "active_provider": "ollama",
            "default_model": "saved-model",
            "providers": [
                {
                    "provider": "ollama",
                    "enabled": True,
                    "base_url": "http://remote-ollama.local:11434",
                    "default_model": "saved-model",
                    "note": "account ollama",
                }
            ],
        },
    )
    user = db.query(User).one()
    runtime = get_ollama_runtime_config(db, user)
    get_settings.cache_clear()

    assert response.status_code == 200
    assert runtime.base_url == "http://remote-ollama.local:11434"
    assert runtime.default_model == "saved-model"
    assert response.json()["ollama_runtime"]["uses_access"] is False


def test_ai_config_exposes_access_status_without_credentials(
    client: TestClient,
    db: Session,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_ollama_environment(monkeypatch)
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    monkeypatch.setenv("OLLAMA_CF_ACCESS_CLIENT_ID", "client-id-test-only")
    monkeypatch.setenv("OLLAMA_CF_ACCESS_CLIENT_SECRET", "client-secret-test-only")

    response = client.get("/api/ai/config", headers=admin_headers)
    get_settings.cache_clear()

    assert response.status_code == 200
    runtime = response.json()["ollama_runtime"]
    assert runtime == {
        "enabled": True,
        "base_url": "https://openclaw.lsgood.cn",
        "default_model": "qwen3.5:4b",
        "connect_timeout_seconds": 20.0,
        "read_timeout_seconds": 180.0,
        "verify_tls": True,
        "access_configured": True,
        "uses_access": True,
    }
    serialized = response.text
    assert "access_client_id" not in serialized
    assert "access_client_secret" not in serialized
    assert "client-id-test-only" not in serialized
    assert "client-secret-test-only" not in serialized

    monkeypatch.setenv("OLLAMA_BASE_URL", "https://user@openclaw.lsgood.cn")
    get_settings.cache_clear()
    invalid_origin = get_effective_ai_settings(db, None)
    get_settings.cache_clear()

    assert invalid_origin.ollama_runtime.uses_access is False


def test_legacy_timeout_is_read_timeout_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_ollama_environment(monkeypatch)
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "75")

    settings = Settings(_env_file=None)

    assert settings.ollama_read_timeout_seconds == 75.0


def test_models_reads_ollama_tags(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "qwen2.5", "size": 123}]})

    _mock_ollama(monkeypatch, handler)

    response = client.get("/api/ai/models")

    assert response.status_code == 200
    assert response.json()["models"][0]["name"] == "qwen2.5"


def test_ai_config_is_persisted_per_account(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get("/api/ai/config", headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["active_provider"] == "ollama"
    assert any(provider["provider"] == "openai" for provider in data["providers"])

    updated = client.put(
        "/api/ai/config",
        headers=admin_headers,
        json={
            "active_provider": "ollama",
            "default_model": "remote-qwen",
            "providers": [
                {
                    "provider": "ollama",
                    "enabled": True,
                    "base_url": "http://192.168.1.10:11434",
                    "default_model": "remote-qwen",
                    "note": "remote ollama",
                },
                {
                    "provider": "openai",
                    "enabled": True,
                    "base_url": "https://api.openai.com/v1",
                    "api_key": "sk-test",
                    "default_model": "gpt-test",
                    "note": "openai placeholder",
                },
            ],
        },
    )

    assert updated.status_code == 200
    saved = updated.json()
    assert saved["default_model"] == "remote-qwen"
    ollama = next(provider for provider in saved["providers"] if provider["provider"] == "ollama")
    assert ollama["base_url"] == "http://192.168.1.10:11434"
    openai = next(provider for provider in saved["providers"] if provider["provider"] == "openai")
    assert openai["api_key"] == ""
    assert openai["has_api_key"] is True


def test_models_use_account_ollama_base_url(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client.put(
        "/api/ai/config",
        headers=admin_headers,
        json={
            "active_provider": "ollama",
            "default_model": "remote-qwen",
            "providers": [
                {
                    "provider": "ollama",
                    "enabled": True,
                    "base_url": "http://remote-ollama.local:11434",
                    "default_model": "remote-qwen",
                    "note": "remote ollama",
                }
            ],
        },
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith("http://remote-ollama.local:11434")
        return httpx.Response(200, json={"models": [{"name": "remote-qwen"}]})

    _mock_ollama(monkeypatch, handler)

    response = client.get("/api/ai/models", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["models"][0]["name"] == "remote-qwen"


def test_models_fallback_to_docker_host_for_localhost_ollama(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client.put(
        "/api/ai/config",
        headers=admin_headers,
        json={
            "active_provider": "ollama",
            "default_model": "local-qwen",
            "providers": [
                {
                    "provider": "ollama",
                    "enabled": True,
                    "base_url": "http://localhost:11434",
                    "default_model": "local-qwen",
                    "note": "local ollama",
                }
            ],
        },
    )

    requested_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(request.url.host or "")
        if request.url.host == "localhost":
            raise httpx.ConnectError("connection refused", request=request)
        assert request.url.host == "host.docker.internal"
        return httpx.Response(200, json={"models": [{"name": "local-qwen"}]})

    _mock_ollama(monkeypatch, handler)

    response = client.get("/api/ai/models", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["models"][0]["name"] == "local-qwen"
    assert requested_hosts == ["localhost", "host.docker.internal"]


def test_classify_book_accepts_valid_model_json(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/generate"
        return httpx.Response(
            200,
            json=_generate_response(
                {
                    "category_code": "C91",
                    "category_name": "社会学",
                    "confidence": 0.86,
                    "tags": ["社会学", "中国乡村"],
                    "reason": "该书讨论乡村社会结构。",
                }
            ),
        )

    _mock_ollama(monkeypatch, handler)

    response = client.post("/api/ai/classify-book", json=_classify_payload())

    assert response.status_code == 200
    data = response.json()
    assert data["category_code"] == "C91"
    assert data["model"] == "qwen2.5"

    task = db.query(AITask).one()
    assert task.task_type == "classify_book"
    assert task.status == "success"
    assert json.loads(task.output_data or "{}")["category_code"] == "C91"


def test_classify_book_rejects_invalid_model_json(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "不是 JSON"})

    _mock_ollama(monkeypatch, handler)

    response = client.post("/api/ai/classify-book", json=_classify_payload())

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "EXTERNAL_SERVICE_ERROR"

    task = db.query(AITask).one()
    assert task.status == "failed"
    assert "JSON" in (task.error_message or "")


def test_ollama_unavailable_returns_clear_error(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _mock_ollama(monkeypatch, handler)

    response = client.get("/api/ai/models")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AI_SERVICE_UNAVAILABLE"

    task = db.query(AITask).one()
    assert task.task_type == "models"
    assert task.status == "failed"


def test_generate_tags_records_success(client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_generate_response({"tags": ["社会学", "经典", "乡村"], "reason": "主题明确"}),
        )

    _mock_ollama(monkeypatch, handler)

    response = client.post(
        "/api/ai/generate-tags",
        json={"title": "乡土中国", "summary": "社会学经典", "model": "qwen2.5"},
    )

    assert response.status_code == 200
    assert response.json()["tags"] == ["社会学", "经典", "乡村"]
    assert db.query(AITask).one().status == "success"


def test_recommend_book_content_records_success(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_generate_response(
                {
                    "recommended": {
                        "publisher": "人民出版社",
                        "publish_year": 2004,
                        "summary": "马克思主义政治经济学经典著作。",
                    },
                    "source_summary": "根据外部候选整理。",
                    "confidence": 0.82,
                    "reason": "出版社与年份来自候选数据。",
                }
            ),
        )

    _mock_ollama(monkeypatch, handler)

    response = client.post(
        "/api/ai/recommend-book-content",
        json={
            "current": {"title": "资本论", "author": "马克思"},
            "candidates": [
                {
                    "source": "openlibrary",
                    "title": "资本论",
                    "author": "马克思",
                    "publisher": "人民出版社",
                    "publish_year": 2004,
                }
            ],
            "missing_fields": ["publisher", "publish_year", "summary"],
            "model": "qwen2.5",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["recommended"]["publisher"] == "人民出版社"
    assert data["model"] == "qwen2.5"
    task = db.query(AITask).one()
    assert task.task_type == "recommend_book_content"
    assert task.status == "success"


def test_natural_search_records_failure_on_schema_error(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_generate_response({"publish_year_from": 2020, "publish_year_to": 2010}))

    _mock_ollama(monkeypatch, handler)

    response = client.post("/api/ai/natural-search", json={"query": "找 2010 年前后的书"})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "EXTERNAL_SERVICE_ERROR"
    assert db.query(AITask).one().status == "failed"
