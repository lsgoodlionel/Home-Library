from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import httpx
import pytest
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
    safe_runtime = runtime.to_safe_dict()
    assert "credential" not in safe_runtime
    assert credential not in repr(safe_runtime)


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
