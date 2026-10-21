from __future__ import annotations

import asyncio
import json
import socket
import types
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.services.ai_provider_url import PinnedAsyncHTTPTransport, ValidatedCloudProviderTarget
from app.services.ai_providers.base import (
    AIProviderAuthenticationError,
    AIProviderConnectTimeoutError,
    AIProviderInvalidConfigurationError,
    AIProviderInvalidResponseError,
    AIProviderModelError,
    AIProviderQuotaError,
    AIProviderRateLimitError,
    AIProviderReadTimeoutError,
    AIProviderRuntime,
    AIProviderUpstreamError,
)
from app.services.ai_providers.openai_compatible import (
    MAX_MODEL_LENGTH,
    MAX_PROMPT_BYTES,
    MAX_RESPONSE_BYTES,
    OPENAI_COMPATIBLE_DESCRIPTORS,
    OpenAICompatibleProviderClient,
    parse_bounded_json,
)


class _GeneratedRecord(BaseModel):
    title: str
    count: int


def _run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


def _install_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def getaddrinfo(
        host: str,
        port: int,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        del host, family, type, proto, flags
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)


def _runtime(
    provider: str = "openai",
    *,
    credential: str = "provider-key",
    base_url: str = "https://api.example.test/v1",
) -> AIProviderRuntime:
    return AIProviderRuntime(
        provider=provider,
        enabled=True,
        base_url=base_url,
        default_model="model-default",
        credential_state="configured",
        credential=credential,
        connect_timeout_seconds=3.25,
        read_timeout_seconds=17.5,
        verify_tls=True,
    )


def _client_with_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    provider: str = "openai",
    credential: str = "provider-key",
    base_url: str = "https://api.example.test/v1",
) -> tuple[OpenAICompatibleProviderClient, list[ValidatedCloudProviderTarget]]:
    _install_public_dns(monkeypatch)
    targets: list[ValidatedCloudProviderTarget] = []

    def make_transport(
        target: ValidatedCloudProviderTarget,
        **kwargs: Any,
    ) -> httpx.AsyncBaseTransport:
        del kwargs
        targets.append(target)
        return httpx.MockTransport(handler)

    monkeypatch.setattr(
        "app.services.ai_providers.openai_compatible.create_pinned_async_transport",
        make_transport,
    )
    return (
        OpenAICompatibleProviderClient(
            _runtime(provider, credential=credential, base_url=base_url)
        ),
        targets,
    )


@pytest.mark.parametrize(
    ("provider", "generation_path", "model_path", "supports_models"),
    [
        ("openai", "/chat/completions", "/models", True),
        ("deepseek", "/chat/completions", "/models", True),
        ("moonshot", "/chat/completions", "/models", True),
        ("qwen", "/chat/completions", None, False),
        ("custom", "/chat/completions", "/models", True),
    ],
)
def test_descriptors_define_paths_and_model_capability(
    provider: str,
    generation_path: str,
    model_path: str | None,
    supports_models: bool,
) -> None:
    descriptor = OPENAI_COMPATIBLE_DESCRIPTORS[provider]

    assert descriptor.provider == provider
    assert descriptor.generation_path == generation_path
    assert descriptor.model_list_path == model_path
    assert descriptor.supports_model_listing is supports_models


@pytest.mark.parametrize("provider", ["openai", "deepseek", "moonshot", "qwen", "custom"])
def test_generation_uses_bearer_headers_explicit_timeouts_and_non_streaming_payload(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "生成结果"}}]},
        )

    client, targets = _client_with_transport(monkeypatch, handler, provider=provider)

    assert _run(client.generate_text("请生成摘要", model="model-selected")) == "生成结果"

    assert len(requests) == 1
    request = requests[0]
    assert request.url == "https://api.example.test/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer provider-key"
    assert request.headers["Accept-Encoding"] == "identity"
    assert request.headers["Content-Type"] == "application/json"
    assert json.loads(request.content) == {
        "model": "model-selected",
        "messages": [{"role": "user", "content": "请生成摘要"}],
        "stream": False,
    }
    assert request.extensions["timeout"] == {
        "connect": 3.25,
        "read": 17.5,
        "write": 3.25,
        "pool": 3.25,
    }
    assert targets == [
        ValidatedCloudProviderTarget(
            url="https://api.example.test/v1/chat/completions",
            origin="https://api.example.test",
            hostname="api.example.test",
            port=443,
            resolved_addresses=("93.184.216.34",),
        )
    ]


def test_production_request_constructs_transport_through_task3_pinning_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_public_dns(monkeypatch)
    built: list[tuple[ValidatedCloudProviderTarget, bool]] = []

    def pinned_factory(
        target: ValidatedCloudProviderTarget,
        *,
        verify: bool = True,
        **kwargs: Any,
    ) -> httpx.AsyncBaseTransport:
        del kwargs
        transport = PinnedAsyncHTTPTransport(target, verify=verify)
        built.append((target, isinstance(transport, PinnedAsyncHTTPTransport)))
        return httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
            )
        )

    monkeypatch.setattr(
        "app.services.ai_providers.openai_compatible.create_pinned_async_transport",
        pinned_factory,
    )
    client = OpenAICompatibleProviderClient(_runtime())

    assert _run(client.generate_text("bounded prompt")) == "ok"
    assert len(built) == 1
    assert built[0][0].resolved_addresses == ("93.184.216.34",)
    assert built[0][1] is True


@pytest.mark.parametrize("provider", ["openai", "deepseek"])
def test_supported_model_listing_maps_provider_scoped_models(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/models"
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"id": "model-b", "object": "model", "owned_by": "vendor"},
                    {"id": "model-a", "object": "model", "owned_by": "vendor"},
                ],
            },
        )

    client, _ = _client_with_transport(monkeypatch, handler, provider=provider)
    result = _run(client.list_models())

    assert result.capability == "supported"
    assert [(model.provider, model.id, model.name) for model in result.models] == [
        (provider, "model-a", "model-a"),
        (provider, "model-b", "model-b"),
    ]


def test_descriptor_without_model_listing_returns_explicit_unsupported_without_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError(f"unexpected request: {request.url}")

    client, _ = _client_with_transport(monkeypatch, handler, provider="qwen")

    result = _run(client.list_models())
    health = _run(client.test_connection())

    assert result.capability == "unsupported"
    assert result.models == ()
    assert health.status == "unchecked"
    assert health.provider == "qwen"
    assert calls == 0


def test_unsupported_model_listing_still_validates_runtime_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _client_with_transport(
        monkeypatch,
        lambda request: httpx.Response(200, json={}),
        provider="qwen",
        base_url="http://private.example.test/v1",
    )

    with pytest.raises(AIProviderInvalidConfigurationError):
        _run(client.list_models())


@pytest.mark.parametrize("status_code", [404, 405])
def test_missing_model_endpoint_returns_explicit_unsupported(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
) -> None:
    client, _ = _client_with_transport(
        monkeypatch,
        lambda request: httpx.Response(status_code, json={"error": {"message": "not available"}}),
        provider="custom",
    )

    result = _run(client.list_models())

    assert result.capability == "unsupported"
    assert result.models == ()


def test_supported_connection_check_uses_model_listing_without_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    methods_and_paths: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods_and_paths.append((request.method, request.url.path))
        return httpx.Response(200, json={"data": [{"id": "model-1"}]})

    client, _ = _client_with_transport(monkeypatch, handler)

    health = _run(client.test_connection())

    assert health.status == "available"
    assert health.provider == "openai"
    assert health.effective_model == "model-default"
    assert methods_and_paths == [("GET", "/v1/models")]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{"message": {"role": "assistant", "content": ""}}]},
        {"choices": [{"message": {"role": "tool", "content": "wrong role"}}]},
        {"choices": [{"message": {"role": "assistant", "content": 42}}]},
        {
            "choices": [
                {"message": {"role": "assistant", "content": "first"}},
                {"message": {"role": "assistant", "content": "second"}},
            ]
        },
    ],
)
def test_generation_rejects_empty_malformed_or_multiple_results(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
) -> None:
    client, _ = _client_with_transport(
        monkeypatch,
        lambda request: httpx.Response(200, json=payload),
    )

    with pytest.raises(AIProviderInvalidResponseError):
        _run(client.generate_text("prompt"))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"title":"图书","count":2}', _GeneratedRecord(title="图书", count=2)),
        (
            '```json\n{"title":"图书","count":2}\n```',
            _GeneratedRecord(title="图书", count=2),
        ),
    ],
)
def test_bounded_json_parser_accepts_plain_json_and_one_markdown_fence(
    text: str,
    expected: _GeneratedRecord,
) -> None:
    assert parse_bounded_json(text, _GeneratedRecord) == expected


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        '{"title":"图书","count":2} trailing prose',
        '```json\n{"title":"图书","count":2}\n```\nextra',
        '```json\n```json\n{"title":"图书","count":2}\n```\n```',
        '{"title":"图书"}',
        '[{"title":"图书","count":2}]',
    ],
)
def test_bounded_json_parser_rejects_malformed_trailing_or_schema_invalid_data(text: str) -> None:
    with pytest.raises(AIProviderInvalidResponseError):
        parse_bounded_json(text, _GeneratedRecord)


def test_bounded_json_parser_rejects_oversized_text() -> None:
    with pytest.raises(AIProviderInvalidResponseError):
        parse_bounded_json("x" * (MAX_RESPONSE_BYTES + 1), _GeneratedRecord)


def test_generate_json_uses_generation_and_local_schema_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _client_with_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": '```json\n{"title":"图书","count":2}\n```',
                        }
                    }
                ]
            },
        ),
    )

    result = _run(client.generate_json("return json", _GeneratedRecord))

    assert result == _GeneratedRecord(title="图书", count=2)


@pytest.mark.parametrize(
    ("status_code", "body", "expected_error"),
    [
        (401, {"error": {"message": "bad key"}}, AIProviderAuthenticationError),
        (403, {"error": {"message": "forbidden"}}, AIProviderAuthenticationError),
        (429, {"error": {"message": "slow down"}}, AIProviderRateLimitError),
        (400, {"error": {"type": "insufficient_quota"}}, AIProviderQuotaError),
        (400, {"error": {"code": "model_not_found"}}, AIProviderModelError),
        (404, {"error": {"message": "unknown model"}}, AIProviderModelError),
        (422, {"error": {"message": "invalid model"}}, AIProviderModelError),
        (500, {"error": {"message": "server failed"}}, AIProviderUpstreamError),
        (503, {"error": {"message": "unavailable"}}, AIProviderUpstreamError),
    ],
)
def test_generation_maps_http_failures_to_safe_error_classes(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    body: dict[str, Any],
    expected_error: type[Exception],
) -> None:
    client, _ = _client_with_transport(
        monkeypatch,
        lambda request: httpx.Response(status_code, json=body),
    )

    with pytest.raises(expected_error):
        _run(client.generate_text("prompt"))


@pytest.mark.parametrize(
    ("source", "expected_error"),
    [
        (httpx.ConnectTimeout("connect marker"), AIProviderConnectTimeoutError),
        (httpx.ReadTimeout("read marker"), AIProviderReadTimeoutError),
    ],
)
def test_generation_maps_transport_timeouts(
    monkeypatch: pytest.MonkeyPatch,
    source: Exception,
    expected_error: type[Exception],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise source

    client, _ = _client_with_transport(monkeypatch, handler)

    with pytest.raises(expected_error):
        _run(client.generate_text("prompt"))


def test_generation_rejects_malformed_or_oversized_upstream_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            httpx.Response(200, content=b"not-json"),
            httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1)),
        ]
    )
    client, _ = _client_with_transport(monkeypatch, lambda request: next(responses))

    with pytest.raises(AIProviderInvalidResponseError):
        _run(client.generate_text("first"))
    with pytest.raises(AIProviderInvalidResponseError):
        _run(client.generate_text("second"))


class _BodyReadProbe(httpx.AsyncByteStream):
    def __init__(self) -> None:
        self.iterated = False

    async def __aiter__(self):
        self.iterated = True
        yield b"must-not-be-read"


def test_declared_oversized_response_is_rejected_before_body_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = _BodyReadProbe()
    client, _ = _client_with_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            headers={"Content-Length": str(MAX_RESPONSE_BYTES + 1)},
            stream=stream,
        ),
    )

    with pytest.raises(AIProviderInvalidResponseError):
        _run(client.generate_text("prompt"))
    assert stream.iterated is False


def test_redirect_response_is_not_followed_and_returns_safe_redirect_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://other.example.test/v1/chat"})

    client, _ = _client_with_transport(monkeypatch, handler)

    with pytest.raises(AIProviderInvalidConfigurationError) as captured:
        _run(client.generate_text("prompt"))

    assert captured.value.reason == "redirect_not_allowed"
    assert len(requests) == 1


@pytest.mark.parametrize(
    ("prompt", "model"),
    [
        ("x" * (MAX_PROMPT_BYTES + 1), "model"),
        ("prompt", "m" * (MAX_MODEL_LENGTH + 1)),
        ("prompt", ""),
    ],
    ids=["prompt-too-large", "model-too-long", "model-empty"],
)
def test_request_bounds_fail_before_network(
    monkeypatch: pytest.MonkeyPatch,
    prompt: str,
    model: str,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client, _ = _client_with_transport(monkeypatch, handler)

    with pytest.raises(AIProviderInvalidConfigurationError):
        _run(client.generate_text(prompt, model=model))
    assert calls == 0


def _assert_public_error_graph_is_safe(error: BaseException, markers: set[str]) -> None:
    pending: list[object] = [error]
    seen: set[int] = set()
    while pending:
        value = pending.pop()
        if value is None or id(value) in seen:
            continue
        seen.add(id(value))
        if isinstance(value, str) and any(marker in value for marker in markers):
            pytest.fail("sensitive text reachable from provider error", pytrace=False)
        if isinstance(value, (bytes, bytearray, memoryview)):
            if any(marker.encode() in bytes(value) for marker in markers):
                pytest.fail("sensitive bytes reachable from provider error", pytrace=False)
        if type(value) in (str, bytes, int, float, bool, type(None)):
            continue
        if isinstance(value, (httpx.Request, httpx.Response, httpx.HTTPError)):
            pytest.fail("upstream HTTP object reachable from provider error", pytrace=False)
        if isinstance(value, BaseException):
            pending.extend((value.args, value.__cause__, value.__context__, value.__traceback__))
        if isinstance(value, types.TracebackType):
            pending.extend((value.tb_frame, value.tb_next))
            continue
        if isinstance(value, types.FrameType):
            module = value.f_globals.get("__name__", "")
            if module.startswith("app.") and not module.startswith("app.tests."):
                pending.append(value.f_locals)
            continue
        if isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, (list, tuple, set, frozenset)):
            pending.extend(value)
        if isinstance(value, types.CoroutineType):
            pending.extend((value.cr_frame, value.cr_await))
        if isinstance(value, types.FunctionType):
            pending.extend((value.__defaults__, value.__kwdefaults__, value.__closure__, value.__dict__))
            continue
        if isinstance(value, types.MethodType):
            pending.extend((value.__self__, value.__func__))
            continue
        if isinstance(value, types.CellType):
            try:
                pending.append(value.cell_contents)
            except ValueError:
                pass
            continue
        if isinstance(value, (types.ModuleType, type)):
            continue
        pending.append(getattr(value, "__dict__", None))
        for cls in type(value).__mro__:
            slots = cls.__dict__.get("__slots__", ())
            for slot in (slots,) if isinstance(slots, str) else slots:
                if slot not in ("__dict__", "__weakref__"):
                    pending.append(getattr(value, slot, None))


def test_public_failure_graph_drops_key_authorization_prompt_query_and_raw_body(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    key = "key-sensitive-marker"
    prompt = "prompt-sensitive-marker"
    query = "query-sensitive-marker"
    body = "raw-body-sensitive-marker"
    source = "source-sensitive-marker"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {key}"
        upstream_request = httpx.Request(
            "POST",
            f"https://api.example.test/v1/chat/completions?token={query}",
            headers=request.headers,
            content=request.content,
        )
        response = httpx.Response(401, request=upstream_request, content=body.encode())
        raise httpx.HTTPStatusError(source, request=upstream_request, response=response)

    client, _ = _client_with_transport(monkeypatch, handler, credential=key)

    with pytest.raises(AIProviderAuthenticationError) as captured:
        _run(client.generate_text(prompt))

    markers = {key, f"Bearer {key}", prompt, query, body, source}
    _assert_public_error_graph_is_safe(captured.value, markers)
    combined_logs = "\n".join(record.getMessage() for record in caplog.records)
    assert not any(marker in combined_logs for marker in markers)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
