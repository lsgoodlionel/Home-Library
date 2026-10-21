from __future__ import annotations

import asyncio
import json
import socket
import types
from collections.abc import Callable
from typing import Any, get_type_hints

import httpx
import pytest
from pydantic import BaseModel

from app.services.ai_provider_url import PinnedAsyncHTTPTransport, ValidatedCloudProviderTarget
from app.services.ai_providers.base import (
    AIProviderAuthenticationError,
    AIProviderClient,
    AIProviderConnectTimeoutError,
    AIProviderDisabledError,
    AIProviderHealth,
    AIProviderInvalidConfigurationError,
    AIProviderInvalidResponseError,
    AIProviderModelError,
    AIProviderModelList,
    AIProviderQuotaError,
    AIProviderRateLimitError,
    AIProviderReadTimeoutError,
    AIProviderRuntime,
    AIProviderUpstreamError,
)
from app.services.ai_providers.gemini import (
    MAX_MODEL_PAGES,
    MAX_PAGE_TOKEN_LENGTH,
    MAX_TOTAL_MODELS,
    GeminiProviderClient,
)
from app.services.ai_providers.openai_compatible import (
    MAX_RESPONSE_BYTES,
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
    *,
    credential: str = "gemini-key",
    base_url: str = "https://generativelanguage.example.test",
    default_model: str = "models/gemini-default",
    enabled: bool = True,
    credential_state: str = "configured",
) -> AIProviderRuntime:
    return AIProviderRuntime(
        provider="gemini",
        enabled=enabled,
        base_url=base_url,
        default_model=default_model,
        credential_state=credential_state,  # type: ignore[arg-type]
        credential=credential,
        connect_timeout_seconds=3.25,
        read_timeout_seconds=17.5,
        verify_tls=True,
    )


def _client_with_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
    **runtime_kwargs: Any,
) -> tuple[GeminiProviderClient, list[ValidatedCloudProviderTarget]]:
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
        "app.services.ai_providers.gemini.create_pinned_async_transport",
        make_transport,
    )
    return GeminiProviderClient(_runtime(**runtime_kwargs)), targets


def _generation_response(text: str = "生成结果") -> dict[str, Any]:
    return {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [{"text": text}],
                },
                "finishReason": "STOP",
            }
        ]
    }


def test_static_contract_uses_public_model_list_and_health_types() -> None:
    assert get_type_hints(AIProviderClient.list_models)["return"] is AIProviderModelList
    assert get_type_hints(GeminiProviderClient.list_models)["return"] is AIProviderModelList
    assert get_type_hints(GeminiProviderClient.test_connection)["return"] is AIProviderHealth


def test_generation_uses_native_header_payload_timeouts_and_no_key_in_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_generation_response())

    client, targets = _client_with_transport(monkeypatch, handler)

    assert _run(client.generate_text("请生成摘要", model="gemini-selected")) == "生成结果"

    assert len(requests) == 1
    request = requests[0]
    assert request.url == (
        "https://generativelanguage.example.test/"
        "v1beta/models/gemini-selected:generateContent"
    )
    assert request.headers["x-goog-api-key"] == "gemini-key"
    assert "gemini-key" not in str(request.url)
    assert "Authorization" not in request.headers
    assert request.headers["Accept-Encoding"] == "identity"
    assert json.loads(request.content) == {
        "contents": [{"role": "user", "parts": [{"text": "请生成摘要"}]}]
    }
    assert request.extensions["timeout"] == {
        "connect": 3.25,
        "read": 17.5,
        "write": 3.25,
        "pool": 3.25,
    }
    assert [target.url for target in targets] == [str(request.url)]


@pytest.mark.parametrize(
    ("model", "expected_raw_path"),
    [
        ("gemini-2.5-flash", b"/v1beta/models/gemini-2.5-flash:generateContent"),
        ("models/gemini-2.5-flash", b"/v1beta/models/gemini-2.5-flash:generateContent"),
        (
            "models/team/model?token=model-query-marker",
            b"/v1beta/models/team%2Fmodel%3Ftoken%3Dmodel-query-marker:generateContent",
        ),
    ],
)
def test_generation_normalizes_model_ids_and_percent_encodes_the_path_segment(
    monkeypatch: pytest.MonkeyPatch,
    model: str,
    expected_raw_path: bytes,
) -> None:
    requests: list[httpx.Request] = []
    client, _ = _client_with_transport(
        monkeypatch,
        lambda request: requests.append(request) or httpx.Response(200, json=_generation_response()),
    )

    assert _run(client.generate_text("prompt", model=model)) == "生成结果"
    assert requests[0].url.raw_path == expected_raw_path
    assert requests[0].url.query == b""


def test_model_listing_paginates_filters_normalizes_deduplicates_and_sorts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "models/gemini-z",
                            "displayName": "Gemini Z",
                            "supportedGenerationMethods": ["generateContent"],
                        },
                        {
                            "name": "models/embedding-1",
                            "displayName": "Embedding",
                            "supportedGenerationMethods": ["embedContent"],
                        },
                    ],
                    "nextPageToken": "page-sensitive-token",
                },
            )
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "gemini-a",
                        "displayName": "Gemini A",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/gemini-z",
                        "displayName": "Duplicate Z",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                ]
            },
        )

    client, targets = _client_with_transport(monkeypatch, handler)
    result = _run(client.list_models())

    assert result.capability == "supported"
    assert [(model.provider, model.id, model.name) for model in result.models] == [
        ("gemini", "gemini-a", "Gemini A"),
        ("gemini", "gemini-z", "Gemini Z"),
    ]
    assert [request.url.path for request in requests] == ["/v1beta/models", "/v1beta/models"]
    assert requests[0].url.query == b""
    assert dict(requests[1].url.params) == {"pageToken": "page-sensitive-token"}
    assert all(request.headers["x-goog-api-key"] == "gemini-key" for request in requests)
    assert all("gemini-key" not in str(request.url) for request in requests)
    assert len(targets) == 2
    assert all(target.url.endswith("/v1beta/models") for target in targets)


def test_production_client_uses_task3_pinned_transport_for_every_page_and_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_public_dns(monkeypatch)
    built: list[tuple[ValidatedCloudProviderTarget, bool]] = []
    page_calls = 0

    def pinned_factory(
        target: ValidatedCloudProviderTarget,
        *,
        verify: bool = True,
        **kwargs: Any,
    ) -> httpx.AsyncBaseTransport:
        nonlocal page_calls
        del kwargs
        transport = PinnedAsyncHTTPTransport(target, verify=verify)
        built.append((target, isinstance(transport, PinnedAsyncHTTPTransport)))

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal page_calls
            if request.method == "GET":
                page_calls += 1
                if page_calls == 1:
                    return httpx.Response(200, json={"models": [], "nextPageToken": "next"})
                return httpx.Response(200, json={"models": []})
            return httpx.Response(200, json=_generation_response("ok"))

        return httpx.MockTransport(handler)

    monkeypatch.setattr(
        "app.services.ai_providers.gemini.create_pinned_async_transport",
        pinned_factory,
    )
    client = GeminiProviderClient(_runtime())

    assert _run(client.list_models()).capability == "supported"
    assert _run(client.generate_text("prompt")) == "ok"
    assert len(built) == 3
    assert all(target.resolved_addresses == ("93.184.216.34",) for target, _ in built)
    assert all(is_pinned for _, is_pinned in built)


@pytest.mark.parametrize("failure", ["repeat", "cycle"])
def test_model_listing_rejects_repeated_or_cyclic_page_tokens(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    responses = (
        [
            {"models": [], "nextPageToken": "same"},
            {"models": [], "nextPageToken": "same"},
        ]
        if failure == "repeat"
        else [
            {"models": [], "nextPageToken": "first"},
            {"models": [], "nextPageToken": "second"},
            {"models": [], "nextPageToken": "first"},
        ]
    )
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        response = responses[calls]
        calls += 1
        return httpx.Response(200, json=response)

    client, _ = _client_with_transport(monkeypatch, handler)

    with pytest.raises(AIProviderInvalidResponseError):
        _run(client.list_models())


def test_model_listing_enforces_page_token_page_and_total_model_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    too_long_client, _ = _client_with_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            json={"models": [], "nextPageToken": "x" * (MAX_PAGE_TOKEN_LENGTH + 1)},
        ),
    )
    with pytest.raises(AIProviderInvalidResponseError):
        _run(too_long_client.list_models())

    page_calls = 0

    def endless_pages(request: httpx.Request) -> httpx.Response:
        nonlocal page_calls
        page_calls += 1
        return httpx.Response(200, json={"models": [], "nextPageToken": f"page-{page_calls}"})

    page_client, _ = _client_with_transport(monkeypatch, endless_pages)
    with pytest.raises(AIProviderInvalidResponseError):
        _run(page_client.list_models())
    assert page_calls == MAX_MODEL_PAGES

    model = {
        "name": "models/gemini-one",
        "supportedGenerationMethods": ["generateContent"],
    }
    total_client, _ = _client_with_transport(
        monkeypatch,
        lambda request: httpx.Response(200, json={"models": [model] * (MAX_TOTAL_MODELS + 1)}),
    )
    with pytest.raises(AIProviderInvalidResponseError):
        _run(total_client.list_models())


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"models": "wrong"},
        {"models": [None]},
        {"models": [{"name": "models/x", "supportedGenerationMethods": "generateContent"}]},
        {"models": [], "nextPageToken": 42},
    ],
)
def test_model_listing_rejects_invalid_native_schema(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
) -> None:
    client, _ = _client_with_transport(
        monkeypatch,
        lambda request: httpx.Response(200, json=payload),
    )

    with pytest.raises(AIProviderInvalidResponseError):
        _run(client.list_models())


def test_connection_uses_model_listing_without_billable_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    methods_and_paths: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods_and_paths.append((request.method, request.url.path))
        return httpx.Response(200, json={"models": []})

    client, _ = _client_with_transport(monkeypatch, handler)
    health = _run(client.test_connection())

    assert health.status == "available"
    assert health.provider == "gemini"
    assert health.effective_model == "gemini-default"
    assert health.safe_base_url == "https://generativelanguage.example.test"
    assert methods_and_paths == [("GET", "/v1beta/models")]


def test_generation_extracts_all_text_parts_from_exactly_one_usable_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "candidates": [
            {"finishReason": "SAFETY"},
            {
                "content": {
                    "role": "model",
                    "parts": [{"text": "first"}, {"inlineData": {}}, {"text": " second"}],
                }
            },
        ]
    }
    client, _ = _client_with_transport(
        monkeypatch,
        lambda request: httpx.Response(200, json=payload),
    )

    assert _run(client.generate_text("prompt")) == "first second"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"candidates": []},
        {"promptFeedback": {"blockReason": "SAFETY"}, "candidates": []},
        {
            "promptFeedback": {"blockReason": "SAFETY"},
            "candidates": [
                {"content": {"role": "model", "parts": [{"text": "must not escape"}]}}
            ],
        },
        {"candidates": [{"finishReason": "SAFETY"}]},
        {
            "candidates": [
                {
                    "finishReason": "SAFETY",
                    "content": {"role": "model", "parts": [{"text": "must not escape"}]},
                }
            ]
        },
        {"candidates": [{"content": {"role": "model", "parts": []}}]},
        {"candidates": [{"content": {"role": "model", "parts": [{"text": ""}]}}]},
        {"candidates": [{"content": {"role": "model", "parts": ["wrong"]}}]},
        {"candidates": [{"content": {"role": "model", "parts": [{"text": 42}]}}]},
        {"candidates": [{"content": {"role": "user", "parts": [{"text": "wrong"}]}}]},
        {"candidates": [{"content": {"role": "model", "parts": "wrong"}}]},
        {
            "candidates": [
                {"content": {"role": "model", "parts": [{"text": "first"}]}},
                {"content": {"role": "model", "parts": [{"text": "second"}]}},
            ]
        },
    ],
)
def test_generation_rejects_empty_blocked_malformed_or_multiple_usable_candidates(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
) -> None:
    client, _ = _client_with_transport(
        monkeypatch,
        lambda request: httpx.Response(200, json=payload),
    )

    with pytest.raises(AIProviderInvalidResponseError):
        _run(client.generate_text("prompt"))


def test_generate_json_reuses_task4_bounded_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.ai_providers.gemini as gemini_module

    assert gemini_module.parse_bounded_json is parse_bounded_json
    client, _ = _client_with_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            json=_generation_response('```json\n{"title":"图书","count":2}\n```'),
        ),
    )

    assert _run(client.generate_json("return json", _GeneratedRecord)) == _GeneratedRecord(
        title="图书",
        count=2,
    )


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        '{"title":"图书","count":2} trailing prose',
        '[{"title":"图书","count":2}]',
        '{"title":"图书"}',
        '```json\n{"title":"图书","count":2}\n```\nextra',
        "x" * (MAX_RESPONSE_BYTES + 1),
    ],
    ids=[
        "malformed",
        "trailing-prose",
        "non-object",
        "schema-invalid",
        "fence-with-trailing-prose",
        "oversized",
    ],
)
def test_generate_json_preserves_task4_invalid_json_behavior(
    monkeypatch: pytest.MonkeyPatch,
    text: str,
) -> None:
    client, _ = _client_with_transport(
        monkeypatch,
        lambda request: httpx.Response(200, json=_generation_response(text)),
    )

    with pytest.raises(AIProviderInvalidResponseError):
        _run(client.generate_json("return json", _GeneratedRecord))


@pytest.mark.parametrize(
    ("status_code", "body", "expected_error"),
    [
        (401, {"error": {"message": "bad key"}}, AIProviderAuthenticationError),
        (403, {"error": {"message": "forbidden"}}, AIProviderAuthenticationError),
        (402, {"error": {"message": "quota"}}, AIProviderQuotaError),
        (429, {"error": {"status": "RESOURCE_EXHAUSTED"}}, AIProviderRateLimitError),
        (400, {"error": {"status": "RESOURCE_EXHAUSTED"}}, AIProviderQuotaError),
        (400, {"error": {"status": "INVALID_ARGUMENT"}}, AIProviderModelError),
        (404, {"error": {"status": "NOT_FOUND"}}, AIProviderModelError),
        (422, {"error": {"status": "INVALID_ARGUMENT"}}, AIProviderModelError),
        (500, {"error": {"message": "server failed"}}, AIProviderUpstreamError),
        (503, {"error": {"message": "unavailable"}}, AIProviderUpstreamError),
    ],
)
def test_generation_maps_native_http_failures_to_safe_error_classes(
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


class _BodyReadProbe(httpx.AsyncByteStream):
    def __init__(self, body: bytes = b"must-not-be-read") -> None:
        self.body = body
        self.iterated = False

    async def __aiter__(self):
        self.iterated = True
        yield self.body


def test_streaming_response_bound_rejects_declared_and_actual_oversized_bodies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    declared_stream = _BodyReadProbe()
    actual_stream = _BodyReadProbe(b"x" * (MAX_RESPONSE_BYTES + 1))
    responses = iter(
        [
            httpx.Response(
                200,
                headers={"Content-Length": str(MAX_RESPONSE_BYTES + 1)},
                stream=declared_stream,
            ),
            httpx.Response(200, stream=actual_stream),
        ]
    )
    client, _ = _client_with_transport(
        monkeypatch,
        lambda request: next(responses),
    )

    with pytest.raises(AIProviderInvalidResponseError):
        _run(client.generate_text("declared"))
    assert declared_stream.iterated is False
    with pytest.raises(AIProviderInvalidResponseError):
        _run(client.generate_text("actual"))
    assert actual_stream.iterated is True


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, AIProviderAuthenticationError),
        (403, AIProviderAuthenticationError),
        (402, AIProviderQuotaError),
        (429, AIProviderRateLimitError),
        (404, AIProviderModelError),
        (422, AIProviderModelError),
        (500, AIProviderUpstreamError),
        (503, AIProviderUpstreamError),
    ],
)
def test_explicit_status_and_redirect_precede_body_read(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    expected_error: type[Exception],
) -> None:
    stream = _BodyReadProbe()
    client, _ = _client_with_transport(
        monkeypatch,
        lambda request: httpx.Response(
            status_code,
            headers={"Content-Length": str(MAX_RESPONSE_BYTES + 1)},
            stream=stream,
        ),
    )

    with pytest.raises(expected_error):
        _run(client.generate_text("prompt"))
    assert stream.iterated is False


def test_redirect_is_not_followed_and_is_rejected_before_body_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = _BodyReadProbe()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            302,
            headers={
                "Location": "https://other.example.test/v1beta/models/private:generateContent",
                "Content-Length": str(MAX_RESPONSE_BYTES + 1),
            },
            stream=stream,
        )

    client, _ = _client_with_transport(monkeypatch, handler)

    with pytest.raises(AIProviderInvalidConfigurationError) as captured:
        _run(client.generate_text("prompt"))
    assert captured.value.reason == "redirect_not_allowed"
    assert len(requests) == 1
    assert stream.iterated is False


@pytest.mark.parametrize(
    "runtime_kwargs",
    [
        {"enabled": False},
        {"credential_state": "missing", "credential": ""},
        {"base_url": "http://private.example.test"},
    ],
)
def test_runtime_and_target_validation_fail_before_network(
    monkeypatch: pytest.MonkeyPatch,
    runtime_kwargs: dict[str, Any],
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_generation_response())

    client, _ = _client_with_transport(monkeypatch, handler, **runtime_kwargs)

    with pytest.raises((AIProviderDisabledError, AIProviderInvalidConfigurationError)) as captured:
        _run(client.generate_text("prompt"))
    assert isinstance(captured.value, (AIProviderDisabledError, AIProviderInvalidConfigurationError))
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


def test_public_failure_graph_drops_key_header_prompt_token_query_model_and_raw_body(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    key = "key-sensitive-marker"
    prompt = "prompt-sensitive-marker"
    page_token = "page-token-sensitive-marker"
    query = "query-sensitive-marker"
    model = "models/model-sensitive-marker?query=query-sensitive-marker"
    body = "raw-body-sensitive-marker"
    source = "source-sensitive-marker"
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"models": [], "nextPageToken": page_token})
        upstream_request = httpx.Request(
            "POST",
            f"{request.url}?token={query}",
            headers=request.headers,
            content=request.content or prompt.encode(),
        )
        response = httpx.Response(401, request=upstream_request, content=body.encode())
        raise httpx.HTTPStatusError(source, request=upstream_request, response=response)

    client, _ = _client_with_transport(monkeypatch, handler, credential=key)

    with pytest.raises(AIProviderAuthenticationError) as page_error:
        _run(client.list_models())
    _assert_public_error_graph_is_safe(
        page_error.value,
        {key, page_token, query, body, source},
    )

    calls = 1
    with pytest.raises(AIProviderAuthenticationError) as generation_error:
        _run(client.generate_text(prompt, model=model))
    markers = {key, f"x-goog-api-key: {key}", prompt, page_token, query, model, body, source}
    _assert_public_error_graph_is_safe(generation_error.value, markers)
    combined_logs = "\n".join(record.getMessage() for record in caplog.records)
    assert not any(marker in combined_logs for marker in markers)
    assert generation_error.value.__cause__ is None
    assert generation_error.value.__context__ is None
