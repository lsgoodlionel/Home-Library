from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.services.ai_setting_service import OllamaRuntimeConfig
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


def _runtime(
    *,
    base_url: str = "https://ollama.example.com",
    trusted_base_url: str = "https://OLLAMA.example.com:443/trusted/path",
) -> OllamaRuntimeConfig:
    return OllamaRuntimeConfig(
        enabled=True,
        base_url=base_url,
        trusted_base_url=trusted_base_url,
        default_model="qwen3:8b",
        connect_timeout_seconds=2.5,
        read_timeout_seconds=30.0,
        verify_tls=True,
        access_client_id="client-id-secret-marker",
        access_client_secret="client-secret-marker",
    )


def _run(coro):
    return asyncio.run(coro)


def _assert_sensitive_exception_state_unreachable(
    exc: BaseException,
    *markers: str,
) -> None:
    assert exc.__cause__ is None
    assert exc.__context__ is None

    pending: list[Any] = [exc]
    seen: set[int] = set()
    while pending:
        value = pending.pop()
        if value is None or id(value) in seen:
            continue
        seen.add(id(value))

        if isinstance(value, bytes):
            text = value.decode("utf-8", errors="replace")
            assert all(marker not in text for marker in markers)
            continue
        if isinstance(value, str):
            assert all(marker not in value for marker in markers)
            continue
        if isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
            continue
        if isinstance(value, (list, tuple, set, frozenset)):
            pending.extend(value)
            continue

        if isinstance(value, BaseException):
            pending.extend(value.args)
            pending.extend([value.__cause__, value.__context__])
        if isinstance(value, httpx.Request):
            pending.extend([str(value.url), dict(value.headers), value.content])
        if isinstance(value, httpx.Response):
            pending.extend([value.request, dict(value.headers), value.content])

        for attribute in ("request", "response", "input", "doc"):
            try:
                pending.append(getattr(value, attribute, None))
            except (AttributeError, RuntimeError):
                pass

        errors = getattr(value, "errors", None)
        if callable(errors):
            pending.append(errors())


def test_trusted_origin_receives_access_headers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["CF-Access-Client-Id"] == "client-id-secret-marker"
        assert request.headers["CF-Access-Client-Secret"] == "client-secret-marker"
        return httpx.Response(200, json={"version": "0.6.2"})

    client = OllamaClient(_runtime(), transport=httpx.MockTransport(handler))

    response = _run(client.version())

    assert response.version == "0.6.2"


def test_untrusted_origin_never_receives_access_headers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "CF-Access-Client-Id" not in request.headers
        assert "CF-Access-Client-Secret" not in request.headers
        return httpx.Response(200, json={"version": "0.6.2"})

    client = OllamaClient(
        _runtime(base_url="https://ollama.other.example"),
        transport=httpx.MockTransport(handler),
    )

    _run(client.version())


@pytest.mark.parametrize(
    "base_url",
    [
        "http://[",
        "ftp://ollama.example.com",
        "localhost:11434",
        "http:///missing-host",
        "https://ollama.example.com@evil.example",
    ],
)
def test_invalid_or_unsupported_base_url_maps_to_safe_model_error(base_url: str) -> None:
    def request_must_not_be_sent(request: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid base URL reached the transport")

    client = OllamaClient(
        _runtime(base_url=base_url),
        transport=httpx.MockTransport(request_must_not_be_sent),
    )

    with pytest.raises(OllamaModelError) as caught:
        _run(client.version())

    assert caught.value.category == "model"
    assert str(caught.value) == "Ollama base URL is invalid"
    _assert_sensitive_exception_state_unreachable(caught.value, base_url)


@pytest.mark.parametrize(
    "base_url",
    [
        "https://sub.ollama.example.com",
        "https://evil.example?next=https://ollama.example.com",
    ],
)
def test_userinfo_subdomain_and_query_cannot_spoof_trusted_origin(base_url: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "CF-Access-Client-Id" not in request.headers
        assert "CF-Access-Client-Secret" not in request.headers
        return httpx.Response(200, json={"version": "0.6.2"})

    client = OllamaClient(_runtime(base_url=base_url), transport=httpx.MockTransport(handler))

    _run(client.version())


@pytest.mark.parametrize(
    ("transport_error", "expected_error"),
    [
        (httpx.ConnectTimeout, OllamaConnectTimeoutError),
        (httpx.ReadTimeout, OllamaReadTimeoutError),
    ],
)
def test_connect_timeout_and_read_timeout_are_distinct(
    transport_error: type[httpx.TimeoutException],
    expected_error: type[Exception],
) -> None:
    timeout_marker = "timeout-sensitive-marker"

    def handler(request: httpx.Request) -> httpx.Response:
        raise transport_error(timeout_marker, request=request)

    client = OllamaClient(_runtime(), transport=httpx.MockTransport(handler))

    with pytest.raises(expected_error) as caught:
        _run(client.version())

    _assert_sensitive_exception_state_unreachable(
        caught.value,
        timeout_marker,
        "client-secret-marker",
    )


@pytest.mark.parametrize("status_code", [401, 403])
def test_access_401_and_403_map_to_access_denied(status_code: int) -> None:
    body_marker = "upstream-secret-body-marker"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text=body_marker)

    client = OllamaClient(_runtime(), transport=httpx.MockTransport(handler))

    with pytest.raises(OllamaAccessDeniedError) as caught:
        _run(client.version())

    assert caught.value.category == "access_denied"
    assert caught.value.status_code == status_code
    assert body_marker not in str(caught.value)
    _assert_sensitive_exception_state_unreachable(caught.value, body_marker)


@pytest.mark.parametrize(
    ("status_code", "body"),
    [
        (502, "upstream-secret-body-marker"),
        (503, "upstream-secret-body-marker"),
        (500, ("x" * 4096) + " error code: 1033 " + "upstream-secret-body-marker"),
    ],
)
def test_tunnel_502_503_and_1033_map_to_tunnel_error(status_code: int, body: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text=body)

    client = OllamaClient(_runtime(), transport=httpx.MockTransport(handler))

    with pytest.raises(OllamaTunnelError) as caught:
        _run(client.version())

    assert caught.value.category == "tunnel"
    assert caught.value.status_code == status_code
    assert "upstream-secret-body-marker" not in str(caught.value)
    _assert_sensitive_exception_state_unreachable(
        caught.value,
        "upstream-secret-body-marker",
    )


@pytest.mark.parametrize(
    ("status_code", "body", "expected_error"),
    [
        (500, ("x" * 8192) + " 1033 ", OllamaUpstreamError),
        (500, "error code 11033", OllamaUpstreamError),
        (500, "error code 10330", OllamaUpstreamError),
        (400, "error code 1033", OllamaModelError),
    ],
)
def test_1033_outside_prefix_adjacent_or_non_5xx_is_not_tunnel(
    status_code: int,
    body: str,
    expected_error: type[Exception],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text=body)

    client = OllamaClient(_runtime(), transport=httpx.MockTransport(handler))

    with pytest.raises(expected_error) as caught:
        _run(client.version())

    assert not isinstance(caught.value, OllamaTunnelError)


@pytest.mark.parametrize("status_code", [400, 404, 429])
def test_model_4xx_maps_to_model_error_without_body_leak(status_code: int) -> None:
    body_marker = "upstream-secret-body-marker"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text=body_marker)

    client = OllamaClient(_runtime(), transport=httpx.MockTransport(handler))

    with pytest.raises(OllamaModelError) as caught:
        _run(client.version())

    assert caught.value.category == "model"
    assert caught.value.status_code == status_code
    assert body_marker not in str(caught.value)
    _assert_sensitive_exception_state_unreachable(caught.value, body_marker)


@pytest.mark.parametrize("status_code", [500, 504])
def test_upstream_5xx_maps_to_upstream_error_without_body_leak(status_code: int) -> None:
    body_marker = "upstream-secret-body-marker"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text=body_marker)

    client = OllamaClient(_runtime(), transport=httpx.MockTransport(handler))

    with pytest.raises(OllamaUpstreamError) as caught:
        _run(client.version())

    assert caught.value.category == "upstream"
    assert caught.value.status_code == status_code
    assert body_marker not in str(caught.value)
    _assert_sensitive_exception_state_unreachable(caught.value, body_marker)


class _GeneratedPayload(BaseModel):
    title: str
    model: str


@pytest.mark.parametrize(
    "response_body",
    [
        b"not-http-json",
        b'{"response":"not-model-json"}',
        b'{"response":"{\\"unexpected\\":true}"}',
    ],
)
def test_generate_json_rejects_invalid_json_and_schema(response_body: bytes) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=response_body)

    client = OllamaClient(_runtime(), transport=httpx.MockTransport(handler))

    with pytest.raises(OllamaResponseInvalidError) as caught:
        _run(client.generate_json(prompt="Return a title", response_model=_GeneratedPayload))

    assert caught.value.category == "response_invalid"
    assert "not-model-json" not in str(caught.value)
    _assert_sensitive_exception_state_unreachable(
        caught.value,
        response_body.decode(),
    )


def test_disabled_runtime_never_sends_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("disabled client sent an upstream request")

    runtime = _runtime()
    disabled_runtime = OllamaRuntimeConfig(
        enabled=False,
        base_url=runtime.base_url,
        trusted_base_url=runtime.trusted_base_url,
        default_model=runtime.default_model,
        connect_timeout_seconds=runtime.connect_timeout_seconds,
        read_timeout_seconds=runtime.read_timeout_seconds,
        verify_tls=runtime.verify_tls,
        access_client_id=runtime.access_client_id,
        access_client_secret=runtime.access_client_secret,
    )
    client = OllamaClient(disabled_runtime, transport=httpx.MockTransport(handler))

    with pytest.raises(OllamaDisabledError) as caught:
        _run(client.version())

    assert caught.value.category == "disabled"
    _assert_sensitive_exception_state_unreachable(
        caught.value,
        "client-id-secret-marker",
        "client-secret-marker",
    )


def test_transient_connect_failure_retries_once_before_response() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("temporary connect failure", request=request)
        return httpx.Response(200, json={"version": "0.6.2"})

    client = OllamaClient(_runtime(), transport=httpx.MockTransport(handler))

    response = _run(client.version())

    assert response.version == "0.6.2"
    assert attempts == 2


def test_health_generation_and_chat_methods_use_expected_upstream_contracts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3:8b"}]})
        if request.url.path == "/api/ps":
            return httpx.Response(
                200,
                json={"models": [{"name": "qwen3:8b", "expires_at": "2026-10-20T12:00:00Z"}]},
            )

        payload = json.loads(request.content)
        assert payload["model"] == "qwen3:8b"
        assert payload["stream"] is False
        if request.url.path == "/api/generate":
            assert payload["format"] == "json"
            assert payload["prompt"] == "Return a title"
            return httpx.Response(200, json={"response": '{"title":"Home Library"}'})
        if request.url.path == "/api/chat":
            assert payload["messages"] == [{"role": "user", "content": "Hello"}]
            return httpx.Response(200, json={"message": {"role": "assistant", "content": "Hi"}})
        raise AssertionError(f"unexpected path: {request.url.path}")

    client = OllamaClient(_runtime(), transport=httpx.MockTransport(handler))

    models = _run(client.list_models())
    running = _run(client.running_models())
    generated = _run(
        client.generate_json(prompt="Return a title", response_model=_GeneratedPayload)
    )
    chat_text = _run(client.chat(messages=[{"role": "user", "content": "Hello"}]))

    assert models.models[0].name == "qwen3:8b"
    assert running.models[0].name == "qwen3:8b"
    assert generated == _GeneratedPayload(title="Home Library", model="qwen3:8b")
    assert chat_text == "Hi"


def test_generate_text_uses_current_model_keep_alive_zero_and_returns_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/generate"
        payload = json.loads(request.content)
        assert payload == {
            "model": "qwen3:8b",
            "prompt": "Reply with OK",
            "stream": False,
            "keep_alive": 0,
        }
        return httpx.Response(200, json={"response": "OK"})

    client = OllamaClient(_runtime(), transport=httpx.MockTransport(handler))

    text = _run(client.generate_text(prompt="Reply with OK", keep_alive=0))

    assert text == "OK"


def test_generate_text_rejects_text_over_bound_without_retaining_it() -> None:
    response_marker = "oversized-text-sensitive-marker"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": response_marker + ("x" * 4097)})

    client = OllamaClient(_runtime(), transport=httpx.MockTransport(handler))

    with pytest.raises(OllamaResponseInvalidError) as caught:
        _run(client.generate_text(prompt="Reply briefly", keep_alive=0))

    _assert_sensitive_exception_state_unreachable(caught.value, response_marker)


def test_generate_json_enforces_prompt_and_response_bounds() -> None:
    prompt_marker = "oversized-prompt-sensitive-marker"

    def request_must_not_be_sent(request: httpx.Request) -> httpx.Response:
        raise AssertionError("oversized prompt was sent upstream")

    prompt_client = OllamaClient(
        _runtime(), transport=httpx.MockTransport(request_must_not_be_sent)
    )
    with pytest.raises(OllamaModelError) as prompt_caught:
        _run(
            prompt_client.generate_json(
                prompt=prompt_marker + ("x" * 100_001),
                response_model=_GeneratedPayload,
            )
        )
    _assert_sensitive_exception_state_unreachable(prompt_caught.value, prompt_marker)

    response_marker = "oversized-response-sensitive-marker"
    def oversized_response(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=response_marker.encode() + (b"x" * 1_048_577),
        )

    response_client = OllamaClient(
        _runtime(), transport=httpx.MockTransport(oversized_response)
    )
    with pytest.raises(OllamaResponseInvalidError) as response_caught:
        _run(
            response_client.generate_json(
                prompt="Return a title",
                response_model=_GeneratedPayload,
            )
        )
    _assert_sensitive_exception_state_unreachable(
        response_caught.value,
        response_marker,
    )


def test_propagated_ollama_errors_drop_sensitive_exception_state() -> None:
    secret_marker = "access-secret-boundary-marker"
    prompt_marker = "full-prompt-boundary-marker"
    query_marker = "query-boundary-marker"
    response_marker = "response-boundary-marker"
    runtime = OllamaRuntimeConfig(
        enabled=True,
        base_url=f"https://ollama.example.com?token={query_marker}",
        trusted_base_url="https://ollama.example.com",
        default_model="qwen3:8b",
        connect_timeout_seconds=2.5,
        read_timeout_seconds=30.0,
        verify_tls=True,
        access_client_id="client-id",
        access_client_secret=secret_marker,
    )

    def connect_failure(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    connect_client = OllamaClient(runtime, transport=httpx.MockTransport(connect_failure))
    with pytest.raises(OllamaUpstreamError) as connect_caught:
        _run(
            connect_client.generate_json(
                prompt=prompt_marker,
                response_model=_GeneratedPayload,
            )
        )
    _assert_sensitive_exception_state_unreachable(
        connect_caught.value,
        secret_marker,
        prompt_marker,
        query_marker,
        response_marker,
    )

    invalid_responses = [
        response_marker.encode(),
        json.dumps({"response": f"not-json-{response_marker}"}).encode(),
        json.dumps(
            {"response": json.dumps({"unexpected": response_marker})}
        ).encode(),
    ]
    for response_body in invalid_responses:
        def invalid_response(
            request: httpx.Request,
            body: bytes = response_body,
        ) -> httpx.Response:
            return httpx.Response(200, content=body)

        response_client = OllamaClient(
            runtime,
            transport=httpx.MockTransport(invalid_response),
        )
        with pytest.raises(OllamaResponseInvalidError) as response_caught:
            _run(
                response_client.generate_json(
                    prompt=prompt_marker,
                    response_model=_GeneratedPayload,
                )
            )
        _assert_sensitive_exception_state_unreachable(
            response_caught.value,
            secret_marker,
            prompt_marker,
            query_marker,
            response_marker,
        )
