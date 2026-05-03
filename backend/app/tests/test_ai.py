from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import AITask


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


def test_models_reads_ollama_tags(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "qwen2.5", "size": 123}]})

    _mock_ollama(monkeypatch, handler)

    response = client.get("/api/ai/models")

    assert response.status_code == 200
    assert response.json()["models"][0]["name"] == "qwen2.5"


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
