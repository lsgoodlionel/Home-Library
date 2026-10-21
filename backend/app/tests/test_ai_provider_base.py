from __future__ import annotations

import asyncio
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
    AIProviderHealth,
    AIProviderInvalidConfigurationError,
    AIProviderInvalidResponseError,
    AIProviderModel,
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

    async def list_models(self) -> list[AIProviderModel]:
        raise NotImplementedError

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
