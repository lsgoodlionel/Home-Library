from __future__ import annotations

import asyncio
import logging
import secrets
import traceback
import types
from dataclasses import FrozenInstanceError
from dataclasses import asdict
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from app.services.ai_providers.base import (
    AIProviderAuthenticationError,
    AIProviderClient,
    AIProviderConnectTimeoutError,
    AIProviderDisabledError,
    AIProviderError,
    AIProviderHealth,
    AIProviderInvalidConfigurationError,
    AIProviderInvalidResponseError,
    AIProviderModel,
    AIProviderModelList,
    AIProviderModelError,
    AIProviderQuotaError,
    AIProviderRateLimitError,
    AIProviderReadTimeoutError,
    AIProviderRuntime,
    AIProviderUpstreamError,
    map_provider_exception,
    run_provider_operation,
)


class _ResponseModel(BaseModel):
    value: str


class _CompleteClient:
    async def test_connection(self) -> AIProviderHealth:
        raise NotImplementedError

    async def list_models(self) -> AIProviderModelList:
        return AIProviderModelList(capability="supported")

    async def generate_text(self, prompt: str, model: str | None = None) -> str:
        raise NotImplementedError

    async def generate_json(
        self,
        prompt: str,
        response_model: type[BaseModel],
        model: str | None = None,
    ) -> BaseModel:
        raise NotImplementedError


class _IncompleteClient:
    async def test_connection(self) -> AIProviderHealth:
        raise NotImplementedError


def test_provider_client_protocol_is_runtime_checkable() -> None:
    assert isinstance(_CompleteClient(), AIProviderClient)
    assert not isinstance(_IncompleteClient(), AIProviderClient)


def test_public_model_list_result_distinguishes_capability_and_is_immutable() -> None:
    supported = AIProviderModelList(
        capability="supported",
        models=(AIProviderModel(provider="openai", id="model-1", name="Model 1"),),
    )
    unsupported = AIProviderModelList(capability="unsupported")

    assert supported.models[0].provider == "openai"
    assert unsupported.models == ()
    with pytest.raises(FrozenInstanceError):
        supported.capability = "unsupported"  # type: ignore[misc]


def test_provider_data_structures_are_immutable_and_runtime_repr_is_safe() -> None:
    credential = "provider-key-sensitive-marker"
    runtime = AIProviderRuntime(
        provider="openai",
        enabled=True,
        base_url="https://api.example.test/v1",
        default_model="model-1",
        credential_state="configured",
        credential=credential,
        connect_timeout_seconds=5.0,
        read_timeout_seconds=30.0,
        verify_tls=True,
    )
    model = AIProviderModel(provider="openai", id="model-1", name="Model 1")
    health = AIProviderHealth(
        provider="openai",
        status="available",
        message="连接正常",
        checked_at=datetime(2026, 10, 21, tzinfo=UTC),
        effective_model="model-1",
        safe_base_url="https://api.example.test/v1",
        credential_state="configured",
    )

    for value in (runtime, model, health):
        with pytest.raises(FrozenInstanceError):
            value.provider = "changed"  # type: ignore[misc]

    assert credential not in repr(runtime)
    assert credential not in repr(asdict(runtime))
    assert credential not in repr(jsonable_encoder(runtime))
    safe_runtime = runtime.to_safe_dict()
    assert "credential" not in safe_runtime
    assert credential not in repr(safe_runtime)
    assert runtime.get_credential_value() == credential


@pytest.mark.parametrize(
    ("source", "expected_type", "category"),
    [
        (httpx.ConnectTimeout("secret prompt"), AIProviderConnectTimeoutError, "connect_timeout"),
        (httpx.ReadTimeout("secret response"), AIProviderReadTimeoutError, "read_timeout"),
        (httpx.ConnectError("https://user:password@example.test/?token=secret"), AIProviderUpstreamError, "upstream"),
        (ValueError("raw upstream body sensitive-marker"), AIProviderInvalidResponseError, "invalid_response"),
    ],
)
def test_provider_exception_mapping_is_stable_and_redacted(
    source: Exception,
    expected_type: type[Exception],
    category: str,
) -> None:
    mapped = map_provider_exception(source)

    assert isinstance(mapped, expected_type)
    assert mapped.category == category
    rendered = f"{mapped!s} {mapped!r}"
    for secret in ("secret", "password", "token", "sensitive-marker", "raw upstream body"):
        assert secret not in rendered
    assert mapped.__cause__ is None
    assert mapped.__context__ is None


@pytest.mark.parametrize(
    ("status_code", "expected_type", "category"),
    [
        (401, AIProviderAuthenticationError, "authentication"),
        (402, AIProviderQuotaError, "quota"),
        (429, AIProviderRateLimitError, "rate_limit"),
        (404, AIProviderModelError, "model"),
        (500, AIProviderUpstreamError, "upstream"),
    ],
)
def test_http_status_mapping_uses_safe_provider_taxonomy(
    status_code: int,
    expected_type: type[Exception],
    category: str,
) -> None:
    request = httpx.Request(
        "POST",
        "https://api.example.test/v1/chat?api_key=query-sensitive-marker",
        headers={"Authorization": "Bearer authorization-sensitive-marker"},
        content=b"prompt-sensitive-marker",
    )
    response = httpx.Response(
        status_code,
        request=request,
        content=b"upstream-body-sensitive-marker",
    )

    mapped = map_provider_exception(httpx.HTTPStatusError("unsafe", request=request, response=response))

    assert isinstance(mapped, expected_type)
    assert mapped.category == category
    rendered = f"{mapped!s} {mapped!r}"
    for marker in (
        "query-sensitive-marker",
        "authorization-sensitive-marker",
        "prompt-sensitive-marker",
        "upstream-body-sensitive-marker",
    ):
        assert marker not in rendered


def test_provider_error_taxonomy_exposes_disabled_and_invalid_configuration() -> None:
    disabled = AIProviderDisabledError()
    invalid = AIProviderInvalidConfigurationError(reason="dns_failure")

    assert disabled.category == "disabled"
    assert invalid.category == "invalid_configuration"
    assert invalid.reason == "dns_failure"


def test_safe_provider_operation_raise_boundary_drops_source_exception_graph_and_locals(
    caplog: pytest.LogCaptureFixture,
) -> None:
    source_marker = "source-exception-sensitive-marker"
    authorization_marker = "authorization-sensitive-marker"
    prompt_marker = "prompt-sensitive-marker"
    query_marker = "query-sensitive-marker"
    response_marker = "response-sensitive-marker"

    async def failing_operation() -> str:
        request = httpx.Request(
            "POST",
            f"https://api.example.test/v1/chat?token={query_marker}",
            headers={"Authorization": f"Bearer {authorization_marker}"},
            content=prompt_marker.encode(),
        )
        response = httpx.Response(401, request=request, content=response_marker.encode())
        raise httpx.HTTPStatusError(source_marker, request=request, response=response)

    with pytest.raises(AIProviderAuthenticationError) as captured:
        asyncio.run(run_provider_operation(failing_operation))

    markers = {
        source_marker,
        authorization_marker,
        prompt_marker,
        query_marker,
        response_marker,
    }
    graph: list[BaseException] = [captured.value]
    seen: set[int] = set()
    rendered: list[str] = []
    while graph:
        current = graph.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        rendered.extend((str(current), repr(current)))
        if current.__cause__ is not None:
            graph.append(current.__cause__)
        if current.__context__ is not None:
            graph.append(current.__context__)
        traceback = current.__traceback__
        while traceback is not None:
            if traceback.tb_frame.f_globals.get("__name__") == "app.services.ai_providers.base":
                rendered.append(repr(traceback.tb_frame.f_locals))
            traceback = traceback.tb_next

    rendered.extend(record.getMessage() for record in caplog.records)
    combined = "\n".join(rendered)
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    for marker in markers:
        assert marker not in combined


def _assert_public_provider_graph_is_safe(error: BaseException, markers: set[str]) -> None:
    """Walk retained values, including application frames, without caller-owned fixtures."""
    pending: list[object] = [error]
    seen: set[int] = set()
    while pending:
        value = pending.pop()
        if id(value) in seen:
            continue
        seen.add(id(value))
        if isinstance(value, str):
            if any(marker in value for marker in markers):
                pytest.fail("sensitive text reachable from public provider error", pytrace=False)
        elif isinstance(value, (bytes, bytearray, memoryview)):
            if any(marker.encode() in bytes(value) for marker in markers):
                pytest.fail("sensitive bytes reachable from public provider error", pytrace=False)
        if type(value) in (str, bytes, int, float, bool, type(None)):
            continue
        if isinstance(value, (httpx.Request, httpx.Response, httpx.HTTPError)):
            pytest.fail("upstream HTTP object reachable from public provider error", pytrace=False)
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
        if isinstance(value, types.GeneratorType):
            pending.extend((value.gi_frame, value.gi_yieldfrom))
        if isinstance(value, asyncio.Future):
            pending.extend((value._result, value._exception))
            if isinstance(value, asyncio.Task):
                pending.append(value.get_coro())
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
                pass  # Empty closure cells retain no value.
            continue
        if isinstance(value, (types.ModuleType, type)):
            # Global namespaces and caller-owned test fixtures are outside this boundary.
            continue
        pending.append(getattr(value, "__dict__", None))
        for cls in type(value).__mro__:
            slots = cls.__dict__.get("__slots__", ())
            for slot in (slots,) if isinstance(slots, str) else slots:
                if slot not in ("__dict__", "__weakref__"):
                    pending.append(getattr(value, slot, None))


@pytest.mark.parametrize("explicit_cause", [False, True], ids=["implicit-context", "explicit-cause"])
def test_existing_provider_error_chain_is_isolated_by_operation_boundary(
    explicit_cause: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    plaintext, authorization, prompt, query, body = (secrets.token_hex(24) for _ in range(5))
    markers = {plaintext, authorization, prompt, query, body}
    verified_source_link: list[bool] = []

    async def operation() -> str:
        request = httpx.Request(
            "POST", f"https://api.example.test/v1/chat?token={query}",
            headers={"Authorization": f"Bearer {authorization}"}, content=prompt.encode(),
        )
        response = httpx.Response(503, request=request, content=body.encode())
        try:
            try:
                raise httpx.HTTPStatusError(plaintext, request=request, response=response)
            except httpx.HTTPStatusError as source:
                if explicit_cause:
                    raise AIProviderUpstreamError(status_code=503, reason="request_failed") from source
                raise AIProviderUpstreamError(status_code=503, reason="request_failed")
        except AIProviderUpstreamError as wrapped:
            verified_source_link.append(
                isinstance(wrapped.__context__, httpx.HTTPStatusError)
                and authorization in wrapped.__context__.request.headers["Authorization"]
                and (wrapped.__cause__ is wrapped.__context__ if explicit_cause else wrapped.__cause__ is None)
            )
            raise

    with pytest.raises(AIProviderUpstreamError) as captured:
        asyncio.run(run_provider_operation(operation))

    error = captured.value
    assert verified_source_link == [True]
    assert error.status_code == 503
    assert error.reason == "request_failed"
    logging.getLogger(__name__).error("Safe provider failure", exc_info=(type(error), error, error.__traceback__))
    rendered = "\n".join((str(error), repr(error), *traceback.format_exception(error),
                          *(logging.Formatter().format(record) for record in caplog.records)))
    assert not any(marker in rendered for marker in markers)
    _assert_public_provider_graph_is_safe(error, markers)
    assert error.__cause__ is None
    assert error.__context__ is None


@pytest.mark.parametrize("error_type", [
    AIProviderError, AIProviderDisabledError, AIProviderInvalidConfigurationError,
    AIProviderAuthenticationError, AIProviderQuotaError, AIProviderRateLimitError,
    AIProviderModelError, AIProviderConnectTimeoutError, AIProviderReadTimeoutError,
    AIProviderUpstreamError, AIProviderInvalidResponseError,
])
def test_existing_provider_error_is_reconstructed_with_only_safe_metadata(
    error_type: type[AIProviderError],
) -> None:
    marker = secrets.token_hex(24)
    request = httpx.Request("POST", "https://api.example.test/", content=marker.encode())
    source = error_type(status_code=429, reason="dns_failure")
    source.args = (marker,)
    source.category = marker
    source.default_message = marker
    source.debug_payload = {"request": request}
    source.add_note(marker)
    try:
        raise httpx.ReadTimeout(marker, request=request)
    except httpx.ReadTimeout as upstream:
        try:
            raise source from upstream
        except AIProviderError as caught:
            mapped = map_provider_exception(caught)

    assert mapped is not source
    assert type(mapped) is error_type
    assert mapped.category == error_type.category
    assert mapped.args == (error_type.default_message,)
    assert mapped.status_code == 429
    assert mapped.reason == "dns_failure"
    assert mapped.__traceback__ is None
    assert mapped.__cause__ is None
    assert mapped.__context__ is None
    assert vars(mapped) == {"status_code": 429, "reason": "dns_failure"}
    _assert_public_provider_graph_is_safe(mapped, {marker})


def test_nested_provider_error_uses_trusted_taxonomy_not_custom_constructor_or_text() -> None:
    marker = secrets.token_hex(24)
    constructed: list[bool] = []

    class DiagnosticUpstreamError(AIProviderUpstreamError):
        category = marker
        default_message = marker

        def __init__(self, diagnostic: str) -> None:
            constructed.append(True)
            super().__init__(status_code=503, reason="request_failed")
            self.diagnostic = diagnostic

    async def operation() -> str:
        try:
            try:
                raise httpx.ConnectError(marker)
            except httpx.ConnectError as source:
                raise AIProviderInvalidConfigurationError(reason="dns_failure") from source
        except AIProviderInvalidConfigurationError as wrapped:
            raise DiagnosticUpstreamError(marker) from wrapped

    with pytest.raises(AIProviderUpstreamError) as captured:
        asyncio.run(run_provider_operation(operation))

    assert constructed == [True]
    assert type(captured.value) is AIProviderUpstreamError
    assert captured.value.category == "upstream"
    assert captured.value.status_code == 503
    assert captured.value.reason == "request_failed"
    _assert_public_provider_graph_is_safe(captured.value, {marker})


@pytest.mark.parametrize("metadata_kind", ["scalar-subclasses", "invalid-values"])
def test_provider_error_metadata_cannot_retain_source_graph(metadata_kind: str) -> None:
    marker = secrets.token_hex(24)
    request = httpx.Request("GET", "https://api.example.test/", headers={"Authorization": marker})

    class StatusCode(int):
        pass

    class SafeReason(str):
        pass

    error = AIProviderUpstreamError()
    if metadata_kind == "scalar-subclasses":
        status = StatusCode(503)
        reason = SafeReason("request_failed")
        status.request = request
        reason.request = request
        error.status_code, error.reason = status, reason
        expected_status, expected_reason = 503, "request_failed"
    else:
        error.status_code = {"request": request}
        error.reason = [request]
        expected_status, expected_reason = None, None

    mapped = map_provider_exception(error)

    assert mapped.status_code == expected_status
    assert mapped.reason == expected_reason
    assert type(mapped.status_code) in (int, type(None))
    assert type(mapped.reason) in (str, type(None))
    _assert_public_provider_graph_is_safe(mapped, {marker})
