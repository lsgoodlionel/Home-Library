from __future__ import annotations

import inspect
import json
import threading
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models import AITask
from app.services.ai_providers.base import (
    AIProviderDisabledError,
    AIProviderRuntime,
    OllamaProviderRuntimeOptions,
)
from app.services.ai_providers.openai_compatible import parse_bounded_json


@dataclass(frozen=True)
class _BusinessCase:
    path: str
    payload: dict[str, Any]
    response: dict[str, Any]
    prompt_markers: tuple[str, ...]


_BUSINESS_CASES = (
    _BusinessCase(
        path="/api/ai/classify-book",
        payload={"title": "乡土中国", "author": "费孝通"},
        response={
            "category_code": "C91",
            "category_name": "社会学",
            "confidence": 0.96,
            "tags": ["乡土社会"],
            "reason": "主题匹配",
            "model": "provider-model",
        },
        prompt_markers=("乡土中国", "费孝通"),
    ),
    _BusinessCase(
        path="/api/ai/generate-tags",
        payload={"title": "乡土中国", "existing_tags": ["社会学"]},
        response={"tags": ["乡土社会"], "reason": "内容相关", "model": "provider-model"},
        prompt_markers=("乡土中国", "社会学"),
    ),
    _BusinessCase(
        path="/api/ai/recommend-book-content",
        payload={
            "current": {"title": "乡土中国"},
            "candidates": [{"source": "openlibrary", "summary": "乡土社会研究"}],
            "missing_fields": ["summary"],
        },
        response={
            "recommended": {
                "title": None,
                "subtitle": None,
                "author": None,
                "translator": None,
                "publisher": None,
                "publish_year": None,
                "isbn": None,
                "language": None,
                "pages": None,
                "cover_url": None,
                "summary": "乡土社会研究",
                "author_intro": None,
                "binding": None,
                "series": None,
                "note": None,
            },
            "source_summary": "openlibrary",
            "confidence": 0.88,
            "reason": "候选信息完整",
            "model": "provider-model",
        },
        prompt_markers=("乡土中国", "openlibrary", "summary"),
    ),
    _BusinessCase(
        path="/api/ai/summarize-book",
        payload={"title": "乡土中国", "raw_summary": "讨论中国基层社会结构"},
        response={
            "summary": "中国基层社会结构研究",
            "author_intro": "",
            "model": "provider-model",
        },
        prompt_markers=("乡土中国", "讨论中国基层社会结构"),
    ),
    _BusinessCase(
        path="/api/ai/detect-duplicate",
        payload={
            "first": {"title": "乡土中国", "isbn": "9787108045269"},
            "second": {"title": "乡土中国（修订本）", "isbn": "9787108045269"},
        },
        response={
            "is_duplicate": True,
            "confidence": 0.99,
            "reason": "ISBN 相同",
            "model": "provider-model",
        },
        prompt_markers=("乡土中国", "9787108045269"),
    ),
    _BusinessCase(
        path="/api/ai/natural-search",
        payload={"query": "找已读的社会学图书"},
        response={
            "keyword": "社会学",
            "category_code": None,
            "category_name": None,
            "location_keyword": None,
            "status": None,
            "read_status": "read",
            "is_favorite": None,
            "publish_year_from": None,
            "publish_year_to": None,
            "tags": [],
            "model": "provider-model",
        },
        prompt_markers=("找已读的社会学图书",),
    ),
)


def _runtime(provider: str, *, enabled: bool = True) -> AIProviderRuntime:
    if provider == "ollama":
        return AIProviderRuntime(
            provider=provider,
            enabled=enabled,
            base_url="https://ollama.example.test",
            default_model="provider-model",
            credential_state="missing",
            ollama=OllamaProviderRuntimeOptions(
                trusted_base_url="https://ollama.example.test",
            ),
        )
    return AIProviderRuntime(
        provider=provider,
        enabled=enabled,
        base_url=f"https://{provider}.example.test/v1",
        default_model="provider-model",
        credential_state="configured",
        credential="test-only-key",
    )


class _FakeProviderClient:
    def __init__(self, runtime: AIProviderRuntime, response: dict[str, Any]) -> None:
        self.runtime = runtime
        self.response = response
        self.calls: list[tuple[str, str | None, type[BaseModel]]] = []

    async def generate_json(
        self,
        prompt: str,
        response_model: type[BaseModel],
        model: str | None = None,
    ) -> BaseModel:
        frame = inspect.currentframe()
        while frame is not None:
            assert not any(isinstance(value, Session) for value in frame.f_locals.values())
            frame = frame.f_back
        self.calls.append((prompt, model, response_model))
        return response_model.model_validate(self.response)


class _FakeOllamaClient(_FakeProviderClient):
    pass


class _FakeOpenAICompatibleClient(_FakeProviderClient):
    pass


class _FakeGeminiClient(_FakeProviderClient):
    pass


_FAKE_CLIENT_TYPES = {
    "ollama": _FakeOllamaClient,
    "openai": _FakeOpenAICompatibleClient,
    "gemini": _FakeGeminiClient,
}


def _install_provider(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    response: dict[str, Any],
) -> tuple[list[_FakeProviderClient], list[int]]:
    clients: list[_FakeProviderClient] = []
    resolver_threads: list[int] = []
    runtime = _runtime(provider)

    def resolve(db: Session, user: object) -> AIProviderRuntime:
        del db, user
        resolver_threads.append(threading.get_ident())
        return runtime

    def create(candidate: AIProviderRuntime) -> _FakeProviderClient:
        assert candidate is runtime
        fake = _FAKE_CLIENT_TYPES[provider](candidate, response)
        clients.append(fake)
        return fake

    monkeypatch.setattr(
        "app.services.ai_provider_runtime.resolve_ai_provider_runtime",
        resolve,
    )
    monkeypatch.setattr(
        "app.services.ai_provider_runtime.create_ai_provider_client",
        create,
    )
    return clients, resolver_threads


@pytest.mark.parametrize("provider", ["ollama", "openai", "gemini"])
@pytest.mark.parametrize("case", _BUSINESS_CASES, ids=lambda case: case.path.rsplit("/", 1)[-1])
def test_business_routes_use_active_provider_model_prompt_and_safe_audit(
    client: TestClient,
    member_headers: dict[str, str],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    case: _BusinessCase,
) -> None:
    from app.api.routes import ai as ai_routes

    clients, resolver_threads = _install_provider(monkeypatch, provider, case.response)
    event_loop_threads: list[int] = []

    original_generate = _FAKE_CLIENT_TYPES[provider].generate_json

    async def generate(self: _FakeProviderClient, *args: Any, **kwargs: Any) -> BaseModel:
        event_loop_threads.append(threading.get_ident())
        return await original_generate(self, *args, **kwargs)

    monkeypatch.setattr(_FAKE_CLIENT_TYPES[provider], "generate_json", generate)
    monkeypatch.setattr(
        ai_routes,
        "OllamaClient",
        lambda runtime: (_ for _ in ()).throw(AssertionError("legacy Ollama path used")),
    )

    response = client.post(case.path, headers=member_headers, json=case.payload)

    assert response.status_code == 200
    assert response.json() == case.response
    assert len(clients) == 1
    [(prompt, model, _)] = clients[0].calls
    assert model == "provider-model"
    for marker in case.prompt_markers:
        assert marker in prompt
    assert resolver_threads and event_loop_threads
    assert resolver_threads[0] != event_loop_threads[0]

    task = db.query(AITask).order_by(AITask.id.desc()).first()
    assert task is not None
    assert task.model == "provider-model"
    assert json.loads(task.input_data) == {"provider": provider}
    assert json.loads(task.output_data) == case.response
    assert "test-only-key" not in repr(task.__dict__)
    assert prompt not in repr(task.__dict__)


def test_business_route_persists_only_bounded_validated_output(
    client: TestClient,
    member_headers: dict[str, str],
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validated_summary = "中" * 100_000
    _install_provider(
        monkeypatch,
        "openai",
        {
            "summary": validated_summary,
            "author_intro": "",
            "model": "provider-model",
        },
    )

    response = client.post(
        "/api/ai/summarize-book",
        headers=member_headers,
        json={"title": "乡土中国"},
    )

    assert response.status_code == 200
    assert response.json()["summary"] == validated_summary
    task = db.query(AITask).order_by(AITask.id.desc()).first()
    assert task is not None
    assert task.output_data is not None
    assert len(task.output_data.encode("utf-8")) <= 65_536
    decoded = json.loads(task.output_data)
    assert decoded["model"] == "provider-model"
    assert set(decoded) <= {"summary", "author_intro", "model"}


def test_disabled_active_provider_fails_before_client_creation(
    client: TestClient,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[object] = []

    def disabled(db: Session, user: object) -> AIProviderRuntime:
        del db, user
        raise AIProviderDisabledError()

    monkeypatch.setattr(
        "app.services.ai_provider_runtime.resolve_ai_provider_runtime",
        disabled,
    )
    monkeypatch.setattr(
        "app.services.ai_provider_runtime.create_ai_provider_client",
        lambda runtime: created.append(runtime),
    )

    response = client.post(
        "/api/ai/summarize-book",
        headers=member_headers,
        json={"title": "乡土中国"},
    )

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "AI_SERVICE_DISABLED",
        "message": "AI 服务尚未启用",
        "details": {"category": "disabled"},
    }
    assert created == []


def test_requested_model_mismatch_fails_before_client_creation(
    client: TestClient,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[object] = []
    runtime = _runtime("openai")
    monkeypatch.setattr(
        "app.services.ai_provider_runtime.resolve_ai_provider_runtime",
        lambda db, user: runtime,
    )
    monkeypatch.setattr(
        "app.services.ai_provider_runtime.create_ai_provider_client",
        lambda candidate: created.append(candidate),
    )

    response = client.post(
        "/api/ai/generate-tags",
        headers=member_headers,
        json={"title": "乡土中国", "model": "gemini-2.5-flash"},
    )

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "AI_CONFIG_INVALID",
        "message": "AI 服务配置无效",
        "details": {"category": "invalid_configuration"},
    }
    assert created == []


@pytest.mark.parametrize(
    ("raw", "status_code", "error_code"),
    [
        ('{"tags":["社会学"],"reason":"匹配","model":"provider-model"}', 200, None),
        ('```json\n{"tags":["社会学"],"reason":"匹配","model":"provider-model"}\n```', 200, None),
        ("not-json-sensitive-raw-response", 502, "AI_RESPONSE_INVALID"),
        ('{"tags":"not-a-list","model":"provider-model"}', 502, "AI_RESPONSE_INVALID"),
    ],
    ids=["canonical", "fenced", "malformed", "schema-invalid"],
)
def test_business_route_preserves_common_structured_output_contract(
    client: TestClient,
    member_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    raw: str,
    status_code: int,
    error_code: str | None,
) -> None:
    runtime = _runtime("openai")
    calls: list[str] = []

    class ParsingFakeClient:
        async def generate_json(
            self,
            prompt: str,
            response_model: type[BaseModel],
            model: str | None = None,
        ) -> BaseModel:
            del prompt, model
            calls.append(raw)
            return parse_bounded_json(raw, response_model)

    monkeypatch.setattr(
        "app.services.ai_provider_runtime.resolve_ai_provider_runtime",
        lambda db, user: runtime,
    )
    monkeypatch.setattr(
        "app.services.ai_provider_runtime.create_ai_provider_client",
        lambda candidate: ParsingFakeClient(),
    )

    response = client.post(
        "/api/ai/generate-tags",
        headers=member_headers,
        json={"title": "乡土中国"},
    )

    assert response.status_code == status_code
    assert calls == [raw]
    if error_code is None:
        assert response.json() == {
            "tags": ["社会学"],
            "reason": "匹配",
            "model": "provider-model",
        }
    else:
        assert response.json()["error"] == {
            "code": error_code,
            "message": "模型返回内容不能安全使用",
            "details": {"category": "invalid_response"},
        }
        assert "not-json-sensitive-raw-response" not in response.text
