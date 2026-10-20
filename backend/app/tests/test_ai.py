from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import AITask, Book
from app.models.user import User
from app.schemas.ai import AIHealthResponse
from app.services.ai_setting_service import get_effective_ai_settings, get_ollama_runtime_config
from app.services.ollama_client import (
    OllamaAccessDeniedError,
    OllamaClient,
    OllamaConnectTimeoutError,
    OllamaDisabledError,
    OllamaModelError,
    OllamaReadTimeoutError,
    OllamaResponseInvalidError,
    OllamaTunnelError,
    OllamaUpstreamError,
)


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
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    get_settings.cache_clear()
    _mock_async_ollama(monkeypatch, handler)


def _mock_async_ollama(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "app.api.routes.ai.OllamaClient",
        lambda runtime: OllamaClient(runtime, transport=transport),
    )


@pytest.fixture
def enabled_ollama_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_ollama_environment(monkeypatch)
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://ollama.example.test")
    monkeypatch.setenv("OLLAMA_DEFAULT_MODEL", "qwen3:8b")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def reset_ai_health_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.api.routes.ai._last_health_status",
        AIHealthResponse(),
    )


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


def test_ai_health_returns_unchecked_cache_without_refresh(
    client: TestClient,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def client_must_not_be_created(runtime):
        raise AssertionError("cached health read created an Ollama client")

    monkeypatch.setattr("app.api.routes.ai.OllamaClient", client_must_not_be_created)

    response = client.get("/api/ai/health", headers=member_headers)

    assert response.status_code == 200
    assert response.json() == {
        "status": "unchecked",
        "message": "尚未检查",
        "checked_at": None,
        "version": None,
        "installed_model_count": 0,
        "running_model_count": 0,
        "generated": False,
        "ollama_runtime": None,
    }


def test_ai_health_returns_sanitized_version_and_model_counts(
    client: TestClient,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    enabled_ollama_runtime: None,
) -> None:
    del enabled_ollama_runtime
    response_marker = "upstream-response-secret-marker"
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.6.2", "ignored": response_marker})
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={"models": [{"name": "qwen3:8b"}, {"name": "nomic-embed-text"}]},
            )
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "qwen3:8b"}]})
        raise AssertionError(f"unexpected path: {request.url.path}")

    _mock_async_ollama(monkeypatch, handler)

    response = client.get("/api/ai/health?refresh=true", headers=member_headers)
    requested_paths_after_refresh = requested_paths.copy()
    cached = client.get("/api/ai/health", headers=member_headers)

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "message": "AI 服务连接正常",
        "checked_at": response.json()["checked_at"],
        "version": "0.6.2",
        "installed_model_count": 2,
        "running_model_count": 1,
        "generated": False,
        "ollama_runtime": {
            "enabled": True,
            "base_url": "https://ollama.example.test",
            "default_model": "qwen3:8b",
            "connect_timeout_seconds": 20.0,
            "read_timeout_seconds": 180.0,
            "verify_tls": True,
            "access_configured": False,
            "uses_access": False,
        },
    }
    assert response.json()["checked_at"]
    assert cached.status_code == 200
    assert cached.json() == response.json()
    assert requested_paths_after_refresh == ["/api/version", "/api/tags", "/api/ps"]
    assert requested_paths == requested_paths_after_refresh
    assert response_marker not in response.text


def test_ai_health_requires_login(client: TestClient) -> None:
    response = client.get("/api/ai/health")

    assert response.status_code == 401


def test_member_cannot_run_ai_connection_test(
    client: TestClient,
    member_headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/ai/test-connection",
        headers=member_headers,
        json={"generate": False},
    )

    assert response.status_code == 403


def test_admin_connection_test_does_not_generate_by_default(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    enabled_ollama_runtime: None,
) -> None:
    del enabled_ollama_runtime
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.6.2"})
        if request.url.path in {"/api/tags", "/api/ps"}:
            return httpx.Response(200, json={"models": []})
        raise AssertionError(f"unexpected path: {request.url.path}")

    _mock_async_ollama(monkeypatch, handler)

    response = client.post(
        "/api/ai/test-connection",
        headers=admin_headers,
        json={},
    )

    assert response.status_code == 200
    assert response.json()["generated"] is False
    assert requested_paths == ["/api/version", "/api/tags", "/api/ps"]
    cached = client.get("/api/ai/health", headers=admin_headers)
    assert cached.json() == response.json()
    assert requested_paths == ["/api/version", "/api/tags", "/api/ps"]


def test_admin_generation_test_requires_explicit_true_and_uses_keep_alive_zero(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    enabled_ollama_runtime: None,
) -> None:
    del enabled_ollama_runtime
    generation_payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.6.2"})
        if request.url.path in {"/api/tags", "/api/ps"}:
            return httpx.Response(200, json={"models": []})
        if request.url.path == "/api/generate":
            generation_payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"response": '{"ok":true}'})
        raise AssertionError(f"unexpected path: {request.url.path}")

    _mock_async_ollama(monkeypatch, handler)

    disabled = client.post(
        "/api/ai/test-connection",
        headers=admin_headers,
        json={"generate": False},
    )
    enabled = client.post(
        "/api/ai/test-connection",
        headers=admin_headers,
        json={"generate": True},
    )

    assert disabled.status_code == 200
    assert disabled.json()["generated"] is False
    assert enabled.status_code == 200
    assert enabled.json()["generated"] is True
    assert generation_payloads == [
        {
            "model": "qwen3:8b",
            "prompt": "请回复 OK",
            "stream": False,
            "keep_alive": 0,
        }
    ]


@pytest.mark.parametrize("invalid_generate", ["true", "yes", 1])
def test_admin_connection_test_rejects_non_boolean_generate_without_request(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    invalid_generate: object,
) -> None:
    def client_must_not_be_created(runtime):
        raise AssertionError("invalid generate value created an Ollama client")

    monkeypatch.setattr("app.api.routes.ai.OllamaClient", client_must_not_be_created)

    response = client.post(
        "/api/ai/test-connection",
        headers=admin_headers,
        json={"generate": invalid_generate},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_admin_connection_failure_updates_health_cache(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    enabled_ollama_runtime: None,
) -> None:
    del enabled_ollama_runtime

    class FailingOllamaClient:
        async def version(self):
            raise OllamaTunnelError("safe", status_code=503)

    monkeypatch.setattr(
        "app.api.routes.ai.OllamaClient",
        lambda runtime: FailingOllamaClient(),
    )

    failed = client.post(
        "/api/ai/test-connection",
        headers=admin_headers,
        json={"generate": False},
    )
    cached = client.get("/api/ai/health", headers=admin_headers)

    assert failed.status_code == 503
    assert cached.status_code == 200
    assert cached.json()["status"] == "error"
    assert cached.json()["message"] == "Tunnel 或远程 Ollama Origin 不可用"
    assert cached.json()["checked_at"]


@pytest.mark.parametrize(
    ("error", "expected_code", "expected_status", "expected_message"),
    [
        pytest.param(
            OllamaDisabledError("safe"),
            "AI_SERVICE_DISABLED",
            503,
            "AI 服务尚未启用",
            id="disabled",
        ),
        pytest.param(
            OllamaAccessDeniedError("safe", status_code=403),
            "AI_ACCESS_DENIED",
            502,
            "Cloudflare Access 凭据缺失、无效或策略不允许",
            id="access_denied",
        ),
        pytest.param(
            OllamaTunnelError("safe", status_code=503),
            "AI_TUNNEL_UNAVAILABLE",
            503,
            "Tunnel 或远程 Ollama Origin 不可用",
            id="tunnel",
        ),
        pytest.param(
            OllamaConnectTimeoutError("safe"),
            "AI_CONNECT_TIMEOUT",
            504,
            "无法在限定时间内连接 AI 服务",
            id="connect_timeout",
        ),
        pytest.param(
            OllamaReadTimeoutError("safe"),
            "AI_RESPONSE_TIMEOUT",
            504,
            "模型启动或生成超时",
            id="read_timeout",
        ),
        pytest.param(
            OllamaModelError("safe", status_code=400),
            "AI_MODEL_ERROR",
            502,
            "模型配置或请求参数错误",
            id="model",
        ),
        pytest.param(
            OllamaUpstreamError("safe", status_code=500),
            "AI_UPSTREAM_ERROR",
            502,
            "上游 AI 服务异常",
            id="upstream",
        ),
        pytest.param(
            OllamaResponseInvalidError("safe"),
            "AI_RESPONSE_INVALID",
            502,
            "模型返回内容不能安全使用",
            id="response_invalid",
        ),
    ],
)
def test_health_failure_returns_chinese_classified_error_without_secret(
    client: TestClient,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_code: str,
    expected_status: int,
    expected_message: str,
) -> None:
    secret_marker = "access-secret-route-marker"
    _clear_ollama_environment(monkeypatch)
    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    monkeypatch.setenv("OLLAMA_BASE_URL", f"https://ollama.example.test/path?token={secret_marker}")
    monkeypatch.setenv("OLLAMA_CF_ACCESS_CLIENT_ID", "client-id-route-marker")
    monkeypatch.setenv("OLLAMA_CF_ACCESS_CLIENT_SECRET", secret_marker)
    get_settings.cache_clear()

    class FailingOllamaClient:
        async def version(self):
            raise error

    monkeypatch.setattr(
        "app.api.routes.ai.OllamaClient",
        lambda runtime: FailingOllamaClient(),
    )

    response = client.get("/api/ai/health?refresh=true", headers=member_headers)
    cached = client.get("/api/ai/health", headers=member_headers)
    get_settings.cache_clear()

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
    assert response.json()["error"]["message"] == expected_message
    assert response.json()["error"]["details"]["hostname"] == "ollama.example.test"
    assert response.json()["error"]["details"]["category"] == getattr(error, "category")
    assert cached.status_code == 200
    assert cached.json()["status"] == "error"
    assert cached.json()["message"] == expected_message
    assert cached.json()["checked_at"]
    assert secret_marker not in response.text
    assert secret_marker not in cached.text
    assert "client-id-route-marker" not in response.text


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


def test_ai_business_routes_use_account_runtime_and_default_model(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = client.put(
        "/api/ai/config",
        headers=admin_headers,
        json={
            "active_provider": "ollama",
            "default_model": "saved-default-model",
            "providers": [
                {
                    "provider": "ollama",
                    "enabled": True,
                    "base_url": "http://account-ollama.local:11434",
                    "default_model": "saved-default-model",
                    "note": "account runtime",
                }
            ],
        },
    )
    assert configured.status_code == 200

    generated_payloads = iter(
        [
            {
                "category_code": "C91",
                "category_name": "社会学",
                "confidence": 0.9,
                "tags": ["社会学"],
                "reason": "分类结果",
            },
            {"tags": ["社会学"], "reason": "标签结果"},
            {
                "recommended": {"publisher": "三联书店"},
                "source_summary": "候选来源",
                "confidence": 0.8,
                "reason": "内容结果",
            },
            {"summary": "整理后的简介", "author_intro": "作者简介"},
            {"is_duplicate": True, "confidence": 0.95, "reason": "书目信息一致"},
            {"keyword": "乡土", "tags": ["社会学"]},
        ]
    )
    requested_models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "account-ollama.local"
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "first-listed-model"}]})
        assert request.url.path == "/api/generate"
        body = json.loads(request.content)
        requested_models.append(body["model"])
        return httpx.Response(200, json=_generate_response(next(generated_payloads)))

    _mock_ollama(monkeypatch, handler)

    assert client.get("/api/ai/models", headers=admin_headers).status_code == 200
    responses = [
        client.post(
            "/api/ai/classify-book",
            headers=admin_headers,
            json={"title": "乡土中国", "author": "费孝通"},
        ),
        client.post(
            "/api/ai/generate-tags",
            headers=admin_headers,
            json={"title": "乡土中国", "summary": "社会学经典"},
        ),
        client.post(
            "/api/ai/recommend-book-content",
            headers=admin_headers,
            json={
                "current": {"title": "乡土中国"},
                "candidates": [{"source": "openlibrary", "publisher": "三联书店"}],
                "missing_fields": ["publisher"],
            },
        ),
        client.post(
            "/api/ai/summarize-book",
            headers=admin_headers,
            json={"title": "乡土中国", "raw_summary": "待整理简介"},
        ),
        client.post(
            "/api/ai/detect-duplicate",
            headers=admin_headers,
            json={"first": {"title": "乡土中国"}, "second": {"title": "乡土中国"}},
        ),
        client.post(
            "/api/ai/natural-search",
            headers=admin_headers,
            json={"query": "找乡土社会学图书"},
        ),
    ]

    assert [response.status_code for response in responses] == [200] * 6
    assert responses[0].json()["category_code"] == "C91"
    assert responses[1].json()["tags"] == ["社会学"]
    assert responses[2].json()["recommended"]["publisher"] == "三联书店"
    assert responses[3].json()["summary"] == "整理后的简介"
    assert responses[4].json()["is_duplicate"] is True
    assert responses[5].json()["keyword"] == "乡土"
    assert requested_models == ["saved-default-model"] * 6


def test_ai_task_input_truncates_long_summary_and_never_stores_headers(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_generate_response(
                {
                    "recommended": {"publisher": "人民出版社"},
                    "source_summary": "已核对",
                    "confidence": 0.8,
                    "reason": "候选信息一致",
                }
            ),
        )

    _mock_ollama(monkeypatch, handler)
    secret = "must-never-be-audited"
    response = client.post(
        "/api/ai/recommend-book-content",
        json={
            "current": {"title": "资本论", "summary": "长" * 5000},
            "candidates": [
                {
                    "source": "openlibrary",
                    "summary": "候选" * 1000,
                    "raw": {"headers": {"Authorization": secret}, "response": secret},
                }
            ],
            "missing_fields": [f"field-{index}" for index in range(30)],
        },
    )

    assert response.status_code == 200
    audit = json.loads(db.query(AITask).one().input_data)
    assert len(audit["current"]["summary"]) <= 512
    assert len(audit["candidates"][0]["summary"]) <= 512
    assert len(audit["missing_fields"]) == 20
    serialized = json.dumps(audit, ensure_ascii=False).lower()
    assert "headers" not in serialized
    assert "authorization" not in serialized
    assert secret not in serialized


def test_ai_failure_does_not_modify_book_or_block_non_ai_health(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    book = Book(title="资本论", author="马克思", summary="原始简介")
    db.add(book)
    db.commit()
    db.refresh(book)
    original = (book.title, book.author, book.summary, book.category_id)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "不是 JSON"})

    _mock_ollama(monkeypatch, handler)
    response = client.post(
        "/api/ai/classify-book",
        json={"title": book.title, "author": book.author, "summary": book.summary},
    )

    db.refresh(book)
    task = db.query(AITask).one()
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_RESPONSE_INVALID"
    assert (book.title, book.author, book.summary, book.category_id) == original
    assert task.status == "failed"
    assert task.error_message == "response_invalid"
    assert client.get("/api/health").json() == {"status": "ok"}


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
    assert response.json()["error"]["code"] == "AI_RESPONSE_INVALID"

    task = db.query(AITask).one()
    assert task.status == "failed"
    assert task.error_message == "response_invalid"


def test_ollama_unavailable_returns_clear_error(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _mock_ollama(monkeypatch, handler)

    response = client.get("/api/ai/models")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_UPSTREAM_ERROR"

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
    assert response.json()["error"]["code"] == "AI_RESPONSE_INVALID"
    assert db.query(AITask).one().status == "failed"
