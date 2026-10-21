from __future__ import annotations

import asyncio
from datetime import datetime
from types import FrameType, TracebackType
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.services.ai_providers.base import (
    AIProviderAuthenticationError,
    AIProviderConnectTimeoutError,
    AIProviderDisabledError,
    AIProviderInvalidResponseError,
    AIProviderModelError,
    AIProviderReadTimeoutError,
    AIProviderRuntime,
    AIProviderUpstreamError,
)
from app.services.ai_providers.ollama import OllamaProviderClient


class _Record(BaseModel):
    title: str
    model: str


def _run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


def _runtime(
    *,
    base_url: str = "https://ollama.example.test",
    trusted_base_url: str = "https://ollama.example.test",
    enabled: bool = True,
) -> AIProviderRuntime:
    from app.services.ai_providers.base import OllamaProviderRuntimeOptions

    return AIProviderRuntime(
        provider="ollama",
        enabled=enabled,
        base_url=base_url,
        default_model="qwen-test",
        credential_state="configured",
        connect_timeout_seconds=3.0,
        read_timeout_seconds=12.0,
        verify_tls=True,
        ollama=OllamaProviderRuntimeOptions(
            trusted_base_url=trusted_base_url,
            access_client_id="access-id-marker",
            access_client_secret="access-secret-marker",
            uses_access=base_url == trusted_base_url,
            config_version=7,
        ),
    )


def test_ollama_adapter_maps_version_models_running_and_generation() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payloads = {
            "/api/version": {"version": "0.12.0"},
            "/api/tags": {"models": [{"name": "b"}, {"name": "a"}]},
            "/api/ps": {"models": [{"name": "a"}]},
            "/api/generate": {"response": '{"title":"结果"}' if request.content.find(b'"format":"json"') >= 0 else "文本结果"},
        }
        return httpx.Response(200, json=payloads[request.url.path])

    client = OllamaProviderClient(_runtime(), transport=httpx.MockTransport(handler))

    models = _run(client.list_models())
    health = _run(client.test_connection())
    assert _run(client.generate_text("生成文本")) == "文本结果"
    assert _run(client.generate_json("生成 JSON", _Record)) == _Record(title="结果", model="qwen-test")

    assert [(model.provider, model.id, model.name) for model in models.models] == [
        ("ollama", "a", "a"),
        ("ollama", "b", "b"),
    ]
    assert models.capability == "supported"
    assert health.status == "available"
    assert health.provider == "ollama"
    assert isinstance(health.checked_at, datetime)
    assert health.details == {
        "version": "0.12.0",
        "installed_model_count": 2,
        "running_model_count": 1,
        "uses_access": True,
    }
    assert all(request.headers["Accept-Encoding"] == "identity" for request in requests)
    assert all(request.headers["CF-Access-Client-Id"] == "access-id-marker" for request in requests)
    assert all(request.headers["CF-Access-Client-Secret"] == "access-secret-marker" for request in requests)


def test_ollama_adapter_never_sends_access_headers_to_untrusted_origin() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"models": []})

    runtime = _runtime(
        base_url="https://untrusted.example.test",
        trusted_base_url="https://ollama.example.test",
    )
    client = OllamaProviderClient(runtime, transport=httpx.MockTransport(handler))

    _run(client.list_models())

    assert requests[0].headers["Accept-Encoding"] == "identity"
    assert "CF-Access-Client-Id" not in requests[0].headers
    assert "CF-Access-Client-Secret" not in requests[0].headers


@pytest.mark.parametrize(
    ("path", "response", "expected"),
    [
        ("/api/tags", httpx.Response(401), AIProviderAuthenticationError),
        ("/api/tags", httpx.Response(403), AIProviderAuthenticationError),
        ("/api/tags", httpx.Response(404), AIProviderModelError),
        ("/api/tags", httpx.Response(502), AIProviderUpstreamError),
        ("/api/tags", httpx.Response(503), AIProviderUpstreamError),
        ("/api/tags", httpx.Response(500), AIProviderUpstreamError),
        ("/api/tags", httpx.Response(200, content=b"not-json"), AIProviderInvalidResponseError),
    ],
)
def test_ollama_adapter_maps_existing_status_and_response_errors(
    path: str,
    response: httpx.Response,
    expected: type[Exception],
) -> None:
    del path
    client = OllamaProviderClient(
        _runtime(),
        transport=httpx.MockTransport(lambda request: response),
    )

    with pytest.raises(expected) as captured:
        _run(client.list_models())
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (httpx.ConnectTimeout("secret-marker"), AIProviderConnectTimeoutError),
        (httpx.ReadTimeout("secret-marker"), AIProviderReadTimeoutError),
        (httpx.ConnectError("secret-marker"), AIProviderUpstreamError),
        (httpx.RequestError("secret-marker"), AIProviderUpstreamError),
    ],
)
def test_ollama_adapter_maps_existing_transport_errors(
    failure: Exception,
    expected: type[Exception],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        raise failure

    client = OllamaProviderClient(_runtime(), transport=httpx.MockTransport(handler))
    with pytest.raises(expected) as captured:
        _run(client.list_models())
    assert "secret-marker" not in repr(captured.value)


def test_ollama_adapter_maps_disabled_runtime() -> None:
    client = OllamaProviderClient(
        _runtime(enabled=False),
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
    )

    with pytest.raises(AIProviderDisabledError):
        _run(client.list_models())


def test_ollama_adapter_exception_graph_excludes_access_credentials() -> None:
    client = OllamaProviderClient(
        _runtime(),
        transport=httpx.MockTransport(lambda request: httpx.Response(401)),
    )

    with pytest.raises(AIProviderAuthenticationError) as captured:
        _run(client.list_models())

    pending: list[object] = [captured.value]
    seen: set[int] = set()
    rendered: list[str] = []
    while pending:
        value = pending.pop()
        if value is None or id(value) in seen:
            continue
        seen.add(id(value))
        rendered.append(repr(value))
        if isinstance(value, BaseException):
            pending.extend((value.__cause__, value.__context__, value.__traceback__))
        elif isinstance(value, TracebackType):
            pending.extend((value.tb_frame, value.tb_next))
        elif isinstance(value, FrameType):
            if "/app/" in value.f_code.co_filename and "/app/tests/" not in value.f_code.co_filename:
                pending.append(value.f_locals)
        elif isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, (list, tuple, set, frozenset)):
            pending.extend(value)

    combined = "\n".join(rendered)
    assert "access-id-marker" not in combined
    assert "access-secret-marker" not in combined
