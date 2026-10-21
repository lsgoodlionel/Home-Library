from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from typing import Awaitable, Callable, TypeVar

import httpx
from pydantic import BaseModel

from app.services.ai_providers.base import (
    AIProviderAuthenticationError,
    AIProviderConnectTimeoutError,
    AIProviderDisabledError,
    AIProviderError,
    AIProviderHealth,
    AIProviderInvalidConfigurationError,
    AIProviderInvalidResponseError,
    AIProviderModel,
    AIProviderModelError,
    AIProviderModelList,
    AIProviderReadTimeoutError,
    AIProviderRuntime,
    AIProviderUpstreamError,
)
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


ResultT = TypeVar("ResultT")
ResponseT = TypeVar("ResponseT", bound=BaseModel)


def _map_ollama_error(error: Exception) -> AIProviderError:
    status_code = getattr(error, "status_code", None)
    reason = getattr(error, "reason", None)
    if isinstance(error, OllamaDisabledError):
        return AIProviderDisabledError()
    if isinstance(error, OllamaAccessDeniedError):
        return AIProviderAuthenticationError(status_code=status_code)
    if isinstance(error, OllamaConnectTimeoutError):
        return AIProviderConnectTimeoutError()
    if isinstance(error, OllamaReadTimeoutError):
        return AIProviderReadTimeoutError()
    if isinstance(error, OllamaModelError):
        return AIProviderModelError(status_code=status_code)
    if isinstance(error, OllamaResponseInvalidError):
        return AIProviderInvalidResponseError()
    if isinstance(error, (OllamaTunnelError, OllamaUpstreamError)):
        return AIProviderUpstreamError(status_code=status_code, reason=reason)
    return AIProviderUpstreamError()


@dataclass(frozen=True, slots=True)
class _Failure:
    error: AIProviderError


async def _capture(operation: Callable[[], Awaitable[ResultT]]) -> ResultT | _Failure:
    try:
        return await operation()
    except Exception as source:
        error = _map_ollama_error(source)
        source.__traceback__ = None
        del source, operation
        return _Failure(error)


def _raise_or_return(outcome: ResultT | _Failure) -> ResultT:
    if isinstance(outcome, _Failure):
        error = outcome.error
        del outcome
        raise error from None
    return outcome


class OllamaProviderClient:
    def __init__(
        self,
        runtime: AIProviderRuntime,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        options = runtime.ollama
        if runtime.provider != "ollama" or options is None:
            del runtime, transport
            raise AIProviderInvalidConfigurationError() from None
        client_id, client_secret = options.get_access_credentials()
        ollama_runtime = OllamaRuntimeConfig(
            enabled=runtime.enabled,
            base_url=runtime.base_url,
            trusted_base_url=options.trusted_base_url,
            default_model=runtime.default_model,
            connect_timeout_seconds=runtime.connect_timeout_seconds,
            read_timeout_seconds=runtime.read_timeout_seconds,
            verify_tls=runtime.verify_tls,
            access_client_id=client_id,
            access_client_secret=client_secret,
        )
        client_id = ""
        client_secret = ""
        self._runtime = runtime
        self._client = OllamaClient(ollama_runtime, transport=transport)

    async def test_connection(self) -> AIProviderHealth:
        operation = partial(self._test_connection_impl)
        outcome = await _capture(operation)
        del operation, self
        return _raise_or_return(outcome)

    async def list_models(self) -> AIProviderModelList:
        operation = partial(self._list_models_impl)
        outcome = await _capture(operation)
        del operation, self
        return _raise_or_return(outcome)

    async def generate_text(self, prompt: str, model: str | None = None) -> str:
        operation = partial(self._client.generate_text, prompt=prompt, model=model)
        outcome = await _capture(operation)
        del operation, self, prompt, model
        return _raise_or_return(outcome)

    async def generate_json(
        self,
        prompt: str,
        response_model: type[ResponseT],
        model: str | None = None,
    ) -> ResponseT:
        operation = partial(
            self._client.generate_json,
            prompt=prompt,
            response_model=response_model,
            model=model,
        )
        outcome = await _capture(operation)
        del operation, self, prompt, response_model, model
        return _raise_or_return(outcome)

    async def _list_models_impl(self) -> AIProviderModelList:
        response = await self._client.list_models()
        names = sorted({model.name for model in response.models if model.name})
        return AIProviderModelList(
            capability="supported",
            models=tuple(
                AIProviderModel(provider="ollama", id=name, name=name)
                for name in names
            ),
        )

    async def _test_connection_impl(self) -> AIProviderHealth:
        version = await self._client.version()
        models = await self._client.list_models()
        running = await self._client.running_models()
        options = self._runtime.ollama
        return AIProviderHealth(
            provider="ollama",
            status="available",
            message="连接正常",
            checked_at=datetime.now(tz=UTC),
            effective_model=self._runtime.default_model,
            safe_base_url=self._runtime.base_url,
            credential_state=self._runtime.credential_state,
            details={
                "version": version.version,
                "installed_model_count": len(models.models),
                "running_model_count": len(running.models),
                "uses_access": bool(options and options.uses_access),
            },
        )


__all__ = ["OllamaProviderClient"]
