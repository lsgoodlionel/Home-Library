from __future__ import annotations

import json
import logging
import asyncio
import threading
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import AITask
from app.services.ai_health_status_cache import provider_health_cache, provider_model_cache
from app.services.ai_provider_runtime import provider_runtime_fingerprint
from app.services.ai_providers.base import (
    AIProviderAuthenticationError,
    AIProviderConnectTimeoutError,
    AIProviderDisabledError,
    AIProviderHealth,
    AIProviderInvalidConfigurationError,
    AIProviderInvalidResponseError,
    AIProviderModel,
    AIProviderModelError,
    AIProviderModelList,
    AIProviderQuotaError,
    AIProviderRateLimitError,
    AIProviderReadTimeoutError,
    AIProviderRuntime,
    AIProviderUpstreamError,
)


def _runtime(
    *,
    provider: str = "openai",
    base_url: str = "https://api.example.test/v1",
    model: str = "saved-model",
    credential: str = "saved-key-sensitive-marker",
) -> AIProviderRuntime:
    return AIProviderRuntime(
        provider=provider,
        enabled=True,
        base_url=base_url,
        default_model=model,
        credential_state="configured",
        credential=credential,
    )


class _Client:
    def __init__(
        self,
        runtime: AIProviderRuntime,
        *,
        failure: Exception | None = None,
    ) -> None:
        self.runtime = runtime
        self.failure = failure
        self.model_calls = 0

    async def test_connection(self) -> AIProviderHealth:
        if self.failure is not None:
            raise self.failure
        return AIProviderHealth(
            provider=self.runtime.provider,
            status="available",
            message="连接正常",
            checked_at=datetime(2026, 10, 21, tzinfo=UTC),
            effective_model=self.runtime.default_model,
            safe_base_url=self.runtime.base_url,
            credential_state=self.runtime.credential_state,
            details={"region": "cn-safe"},
        )

    async def list_models(self) -> AIProviderModelList:
        if self.failure is not None:
            raise self.failure
        self.model_calls += 1
        return AIProviderModelList(
            capability="supported",
            models=(
                AIProviderModel(
                    provider=self.runtime.provider,
                    id="model-a",
                    name="Model A",
                ),
            ),
        )

    async def generate_text(self, prompt: str, model: str | None = None) -> str:
        if self.failure is not None:
            raise self.failure
        assert prompt == "请仅回复：连接测试成功"
        assert model == self.runtime.default_model
        return "连接测试成功"


@pytest.fixture(autouse=True)
def _reset_provider_model_cache() -> None:
    provider_health_cache.invalidate_all()
    provider_model_cache.invalidate_all()


def _install_operation_runtime(monkeypatch: pytest.MonkeyPatch, resolve: Any) -> None:
    def operation(db: Session, user: object, provider: str, **draft: Any) -> AIProviderRuntime:
        saved = resolve(db, user)
        if saved.provider != provider:
            raise AIProviderInvalidConfigurationError()
        credential = draft.get("credential")
        if credential is None or not credential.get_secret_value():
            credential = saved.credential
        elif provider == "ollama":
            raise AIProviderInvalidConfigurationError()
        return replace(saved, base_url=draft.get("base_url") or saved.base_url,
                       default_model=draft.get("model") or saved.default_model,
                       credential=credential,
                       credential_state="configured" if credential is not None else saved.credential_state)

    monkeypatch.setattr("app.services.ai_provider_runtime.resolve_ai_provider_operation_runtime", operation)


def _install_runtime(
    monkeypatch: pytest.MonkeyPatch,
    runtime: AIProviderRuntime,
    *,
    failure: Exception | None = None,
) -> tuple[list[AIProviderRuntime], list[_Client]]:
    created_runtimes: list[AIProviderRuntime] = []
    clients: list[_Client] = []

    def resolve(db: Session, user: object) -> AIProviderRuntime:
        del db, user
        return runtime

    def create(candidate: AIProviderRuntime) -> _Client:
        created_runtimes.append(candidate)
        client = _Client(candidate, failure=failure)
        clients.append(client)
        return client

    monkeypatch.setattr(
        "app.services.ai_provider_runtime.resolve_ai_provider_runtime",
        resolve,
    )
    _install_operation_runtime(monkeypatch, resolve)
    monkeypatch.setattr(
        "app.services.ai_provider_runtime.create_ai_provider_client",
        create,
    )
    return created_runtimes, clients


@pytest.mark.parametrize("headers_fixture", ["member_headers", "admin_headers"])
def test_connection_accepts_saved_config_for_member_and_admin(
    client: TestClient,
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    headers_fixture: str,
) -> None:
    runtime = _runtime()
    _install_runtime(monkeypatch, runtime)

    response = client.post(
        "/api/ai/providers/openai/test",
        headers=request.getfixturevalue(headers_fixture),
        json={},
    )

    assert response.status_code == 200
    assert response.json() == {
        "provider": "openai",
        "status": "available",
        "message": "连接正常",
        "checked_at": "2026-10-21T00:00:00Z",
        "effective_model": "saved-model",
        "safe_base_url": "https://api.example.test/v1",
        "credential_state": "configured",
        "models": [],
        "details": {"region": "cn-safe"},
    }


def test_connection_provider_operations_require_login(client: TestClient) -> None:
    for operation in ("test", "models", "generate-test"):
        response = client.post(f"/api/ai/providers/openai/{operation}", json={})
        assert response.status_code == 401


def test_connection_unsaved_draft_replaces_address_model_and_key_without_persisting(
    client: TestClient,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved = _runtime()
    created, _ = _install_runtime(monkeypatch, saved)
    replacement_key = "draft-key-sensitive-marker"

    response = client.post(
        "/api/ai/providers/openai/test",
        headers=member_headers,
        json={
            "provider": "openai",
            "base_url": "https://draft.example.test/v1",
            "model": "draft-model",
            "api_key": replacement_key,
        },
    )

    assert response.status_code == 200
    assert created[0].base_url == "https://draft.example.test/v1"
    assert created[0].default_model == "draft-model"
    assert created[0].get_credential_value() == replacement_key
    assert replacement_key not in response.text


def test_connection_empty_draft_key_preserves_saved_key(
    client: TestClient,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved = _runtime()
    created, _ = _install_runtime(monkeypatch, saved)

    response = client.post(
        "/api/ai/providers/openai/test",
        headers=member_headers,
        json={"provider": "openai", "api_key": "", "model": "draft-model"},
    )

    assert response.status_code == 200
    assert created[0].get_credential_value() == saved.get_credential_value()
    assert created[0].default_model == "draft-model"
    assert saved.get_credential_value() not in response.text


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"provider": "gemini"},
        {"provider": "openai"},
    ],
)
def test_connection_provider_path_and_current_or_draft_selection_mismatch_fails_closed(
    client: TestClient,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, str],
) -> None:
    current = _runtime(provider="gemini") if payload != {"provider": "gemini"} else _runtime()
    created, _ = _install_runtime(monkeypatch, current)

    response = client.post(
        "/api/ai/providers/openai/test",
        headers=member_headers,
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "AI_CONFIG_INVALID",
        "message": "AI 服务配置无效",
        "details": {"category": "invalid_configuration"},
    }
    assert created == []


def test_connection_account_ai_off_fails_without_creating_client(
    client: TestClient,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def disabled(db: Session, user: object) -> AIProviderRuntime:
        del db, user
        raise AIProviderDisabledError()

    _install_operation_runtime(monkeypatch, disabled)

    created: list[object] = []
    monkeypatch.setattr(
        "app.services.ai_provider_runtime.resolve_ai_provider_runtime",
        disabled,
    )
    monkeypatch.setattr(
        "app.services.ai_provider_runtime.create_ai_provider_client",
        lambda runtime: created.append(runtime),
    )

    response = client.post(
        "/api/ai/providers/openai/models",
        headers=member_headers,
        json={},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AI_SERVICE_DISABLED"
    assert created == []


def test_provider_models_uses_runtime_scoped_cache(
    client: TestClient,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    _, clients = _install_runtime(monkeypatch, runtime)

    first = client.post(
        "/api/ai/providers/openai/models",
        headers=member_headers,
        json={},
    )
    second = client.post(
        "/api/ai/providers/openai/models",
        headers=member_headers,
        json={},
    )

    assert first.status_code == second.status_code == 200
    assert first.json()["models"] == [
        {"provider": "openai", "id": "model-a", "name": "Model A"}
    ]
    assert first.json()["details"] == {"model_list_capability": "supported"}
    assert len(clients) == 1
    assert clients[0].model_calls == 1
    assert provider_model_cache.get(
        1,
        "openai",
        provider_runtime_fingerprint(runtime),
    ) is not None


def test_draft_replacement_key_models_do_not_populate_saved_cache(
    client: TestClient,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved = _runtime()
    created: list[AIProviderRuntime] = []

    class CredentialAwareClient(_Client):
        async def list_models(self) -> AIProviderModelList:
            self.model_calls += 1
            credential = self.runtime.get_credential_value()
            label = "Draft" if credential == "draft-key-sensitive-marker" else "Saved"
            return AIProviderModelList(
                capability="supported",
                models=(
                    AIProviderModel(
                        provider=self.runtime.provider,
                        id=f"{label.lower()}-model",
                        name=f"{label} Model",
                    ),
                ),
            )

    monkeypatch.setattr(
        "app.services.ai_provider_runtime.resolve_ai_provider_runtime",
        lambda db, user: saved,
    )
    _install_operation_runtime(monkeypatch, lambda db, user: saved)
    monkeypatch.setattr(
        "app.services.ai_provider_runtime.create_ai_provider_client",
        lambda runtime: (created.append(runtime), CredentialAwareClient(runtime))[1],
    )

    draft = client.post(
        "/api/ai/providers/openai/models",
        headers=member_headers,
        json={"api_key": "draft-key-sensitive-marker"},
    )
    persisted = client.get("/api/ai/models", headers=member_headers)

    assert draft.status_code == persisted.status_code == 200
    assert draft.json()["models"][0]["id"] == "draft-model"
    assert persisted.json()["models"][0]["model"] == "saved-model"
    assert len(created) == 2


def test_draft_replacement_key_test_does_not_overwrite_saved_health(
    client: TestClient,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_runtime(monkeypatch, _runtime())

    draft = client.post(
        "/api/ai/providers/openai/test",
        headers=member_headers,
        json={"api_key": "draft-key-sensitive-marker"},
    )
    persisted = client.get("/api/ai/health", headers=member_headers)

    assert draft.status_code == persisted.status_code == 200
    assert draft.json()["status"] == "available"
    assert persisted.json()["status"] == "unchecked"
    assert persisted.json()["checked_at"] is None


def test_empty_key_without_other_override_uses_saved_model_cache(
    client: TestClient,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, clients = _install_runtime(monkeypatch, _runtime())

    first = client.post(
        "/api/ai/providers/openai/models",
        headers=member_headers,
        json={"provider": "openai", "api_key": ""},
    )
    second = client.post(
        "/api/ai/providers/openai/models",
        headers=member_headers,
        json={"provider": "openai", "api_key": ""},
    )

    assert first.status_code == second.status_code == 200
    assert len(clients) == 1
    assert clients[0].model_calls == 1


def test_connection_generate_test_returns_confirmation_without_generated_text(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_runtime(monkeypatch, _runtime())

    response = client.post(
        "/api/ai/providers/openai/generate-test",
        headers=admin_headers,
        json={},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "生成测试成功"
    assert response.json()["details"] == {"generation_confirmed": True}
    assert "连接测试成功" not in response.text


@pytest.mark.parametrize(
    ("error", "status", "code", "message"),
    [
        (AIProviderDisabledError(), 503, "AI_SERVICE_DISABLED", "AI 服务尚未启用"),
        (AIProviderInvalidConfigurationError(), 422, "AI_CONFIG_INVALID", "AI 服务配置无效"),
        (AIProviderAuthenticationError(status_code=401), 502, "AI_ACCESS_DENIED", "AI 服务认证失败"),
        (AIProviderQuotaError(status_code=402), 402, "AI_QUOTA_EXCEEDED", "AI 服务额度不足"),
        (AIProviderRateLimitError(status_code=429), 429, "AI_RATE_LIMITED", "AI 服务请求过于频繁"),
        (AIProviderModelError(status_code=404), 502, "AI_MODEL_ERROR", "模型不存在或无权访问"),
        (AIProviderConnectTimeoutError(), 504, "AI_CONNECT_TIMEOUT", "无法在限定时间内连接 AI 服务"),
        (AIProviderReadTimeoutError(), 504, "AI_RESPONSE_TIMEOUT", "模型启动或生成超时"),
        (AIProviderUpstreamError(status_code=503), 502, "AI_UPSTREAM_ERROR", "上游 AI 服务异常"),
        (AIProviderInvalidResponseError(), 502, "AI_RESPONSE_INVALID", "模型返回内容不能安全使用"),
    ],
)
def test_connection_common_provider_errors_have_stable_safe_http_contract(
    client: TestClient,
    db: Session,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    status: int,
    code: str,
    message: str,
) -> None:
    key_marker = "synthetic-key-sensitive-marker"
    header_marker = "synthetic-header-sensitive-marker"
    prompt_marker = "synthetic-prompt-sensitive-marker"
    source = type(error)(
        status_code=getattr(error, "status_code", None),
        reason=getattr(error, "reason", None),
    )
    source.add_note(f"{key_marker} {header_marker} {prompt_marker}")
    runtime = _runtime(credential=key_marker)
    _install_runtime(monkeypatch, runtime, failure=source)
    caplog.set_level(logging.DEBUG)

    response = client.post(
        "/api/ai/providers/openai/test",
        headers=member_headers,
        json={},
    )

    assert response.status_code == status
    assert response.json()["error"] == {
        "code": code,
        "message": message,
        "details": {
            "category": getattr(error, "category"),
            **(
                {"status": getattr(error, "status_code")}
                if getattr(error, "status_code", None) is not None
                else {}
            ),
        },
    }
    rendered = " ".join(
        (
            response.text,
            caplog.text,
            repr(db.query(AITask).all()),
            repr(provider_model_cache._entries),
        )
    )
    assert key_marker not in rendered
    assert header_marker not in rendered
    assert prompt_marker not in rendered


def test_connection_provider_error_boundary_detaches_source_exception_graph(
    client: TestClient,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "source-chain-sensitive-marker"
    source = AIProviderAuthenticationError(status_code=401)
    source.add_note(marker)
    _install_runtime(monkeypatch, _runtime(), failure=source)

    response = client.post(
        "/api/ai/providers/openai/test",
        headers=member_headers,
        json={},
    )

    assert response.status_code == 502
    assert marker not in response.text
    route_module = __import__("app.api.routes.ai_providers", fromlist=["_provider_api_error"])
    safe_error = route_module._provider_api_error(source, _runtime())
    assert safe_error.__cause__ is None
    assert safe_error.__context__ is None
    assert marker not in repr(safe_error.__dict__)


def test_connection_route_exception_traceback_drops_draft_key_and_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key_marker = "traceback-draft-key-sensitive-marker"
    prompt_marker = "traceback-prompt-sensitive-marker"
    runtime = _runtime(credential=key_marker)

    class FailingClient(_Client):
        async def test_connection(self) -> AIProviderHealth:
            local_prompt = prompt_marker
            raise AIProviderAuthenticationError(status_code=401)

    monkeypatch.setattr(
        "app.services.ai_provider_runtime.resolve_ai_provider_runtime",
        lambda db, user: runtime,
    )
    _install_operation_runtime(monkeypatch, lambda db, user: runtime)
    monkeypatch.setattr(
        "app.services.ai_provider_runtime.create_ai_provider_client",
        lambda candidate: FailingClient(candidate),
    )
    route_module = __import__("app.api.routes.ai_providers", fromlist=["test_provider"])
    payload = route_module.AIProviderOperationRequest(
        provider="openai",
        api_key=key_marker,
    )

    with pytest.raises(ApiError) as captured:
        asyncio.run(
            route_module.test_provider(
                "openai",
                payload,
                SimpleNamespace(),
                SimpleNamespace(id=7),
            )
        )

    pending: list[object] = []
    traceback = captured.value.__traceback__
    while traceback is not None:
        if "/app/tests/" not in traceback.tb_frame.f_code.co_filename:
            pending.extend(traceback.tb_frame.f_locals.values())
        traceback = traceback.tb_next
    seen: set[int] = set()
    rendered: list[str] = []
    while pending:
        value = pending.pop()
        if value is None or id(value) in seen:
            continue
        seen.add(id(value))
        if isinstance(value, (str, bytes)):
            rendered.append(repr(value))
            continue
        if isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
            continue
        if isinstance(value, (list, tuple, set, frozenset)):
            pending.extend(value)
            continue
        namespace = getattr(value, "__dict__", None)
        if isinstance(namespace, dict):
            pending.extend(namespace.values())
        slots = getattr(type(value), "__slots__", ())
        if isinstance(slots, str):
            slots = (slots,)
        for slot in slots:
            if slot not in {"__dict__", "__weakref__"}:
                pending.append(getattr(value, slot, None))
    graph_text = " ".join(rendered)
    assert key_marker not in graph_text
    assert prompt_marker not in graph_text


def test_health_exception_traceback_drops_saved_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key_marker = "health-traceback-key-sensitive-marker"
    runtime = _runtime(credential=key_marker)
    _install_runtime(
        monkeypatch,
        runtime,
        failure=AIProviderAuthenticationError(status_code=401),
    )
    route_module = __import__(
        "app.api.routes.ai_providers",
        fromlist=["get_active_provider_health"],
    )

    with pytest.raises(ApiError) as captured:
        asyncio.run(
            route_module.get_active_provider_health(
                SimpleNamespace(),
                SimpleNamespace(id=9),
                refresh=True,
            )
        )

    pending: list[object] = []
    traceback = captured.value.__traceback__
    while traceback is not None:
        if "/app/tests/" not in traceback.tb_frame.f_code.co_filename:
            pending.extend(traceback.tb_frame.f_locals.values())
        traceback = traceback.tb_next
    seen: set[int] = set()
    strings: list[str] = []
    while pending:
        value = pending.pop()
        if value is None or id(value) in seen:
            continue
        seen.add(id(value))
        if isinstance(value, (str, bytes)):
            strings.append(repr(value))
        elif isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, (list, tuple, set, frozenset)):
            pending.extend(value)
        else:
            namespace = getattr(value, "__dict__", None)
            if isinstance(namespace, dict):
                pending.extend(namespace.values())
            slots = getattr(type(value), "__slots__", ())
            if isinstance(slots, str):
                slots = (slots,)
            for slot in slots:
                if slot not in {"__dict__", "__weakref__"}:
                    pending.append(getattr(value, slot, None))
    assert key_marker not in " ".join(strings)


def test_compatibility_health_and_models_use_active_provider(
    client: TestClient,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(provider="gemini", model="gemini-saved")
    _install_runtime(monkeypatch, runtime)

    health = client.get("/api/ai/health?refresh=true", headers=member_headers)
    models = client.get("/api/ai/models", headers=member_headers)

    assert health.status_code == models.status_code == 200
    assert health.json()["provider"] == "gemini"
    assert health.json()["effective_model"] == "gemini-saved"
    assert models.json()["models"] == [
        {"name": "Model A", "model": "model-a", "modified_at": None, "size": None, "digest": None, "details": None}
    ]


def test_provider_routes_run_resolver_and_failure_audit_outside_event_loop(
    client: TestClient,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.routes import ai_providers as provider_routes

    runtime = _runtime()
    resolver_threads: list[int] = []
    audit_threads: list[int] = []
    event_loop_threads: list[int] = []
    fail_models = False
    original_create_task = provider_routes.create_ai_task

    def resolve(db: Session, user: object) -> AIProviderRuntime:
        del db, user
        resolver_threads.append(threading.get_ident())
        return runtime

    def audit(*args: object, **kwargs: object) -> AITask:
        audit_threads.append(threading.get_ident())
        return original_create_task(*args, **kwargs)

    class ThreadTrackingClient(_Client):
        async def test_connection(self) -> AIProviderHealth:
            event_loop_threads.append(threading.get_ident())
            return await super().test_connection()

        async def list_models(self) -> AIProviderModelList:
            event_loop_threads.append(threading.get_ident())
            if fail_models:
                raise AIProviderInvalidConfigurationError()
            return await super().list_models()

        async def generate_text(self, prompt: str, model: str | None = None) -> str:
            event_loop_threads.append(threading.get_ident())
            return await super().generate_text(prompt, model)

    monkeypatch.setattr(
        "app.services.ai_provider_runtime.resolve_ai_provider_runtime",
        resolve,
    )
    monkeypatch.setattr(
        "app.services.ai_provider_runtime.create_ai_provider_client",
        ThreadTrackingClient,
    )
    _install_operation_runtime(monkeypatch, resolve)
    monkeypatch.setattr(provider_routes, "create_ai_task", audit)

    responses = [
        client.get("/api/ai/health?refresh=true", headers=member_headers),
        client.post("/api/ai/providers/openai/test", headers=member_headers, json={}),
        client.post("/api/ai/providers/openai/models", headers=member_headers, json={}),
        client.post(
            "/api/ai/providers/openai/generate-test",
            headers=member_headers,
            json={},
        ),
    ]
    assert all(response.status_code == 200 for response in responses)

    provider_model_cache.invalidate_all()
    fail_models = True
    failed = client.get("/api/ai/models", headers=member_headers)

    assert failed.status_code == 422
    assert len(resolver_threads) == 5
    assert event_loop_threads
    assert len(audit_threads) == 1
    event_loop_thread = event_loop_threads[0]
    assert all(thread_id == event_loop_thread for thread_id in event_loop_threads)
    assert all(thread_id != event_loop_thread for thread_id in resolver_threads)
    assert audit_threads[0] != event_loop_thread
