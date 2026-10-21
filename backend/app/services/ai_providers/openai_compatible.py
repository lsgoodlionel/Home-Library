from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from typing import Any, Awaitable, Callable, Generic, Literal, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.services.ai_provider_url import (
    CLOUD_PROVIDER_FOLLOW_REDIRECTS,
    ValidatedCloudProviderTarget,
    create_pinned_async_transport,
    validate_cloud_provider_target,
)
from app.services.ai_providers.base import (
    AIProviderDisabledError,
    AIProviderError,
    AIProviderHealth,
    AIProviderInvalidConfigurationError,
    AIProviderInvalidResponseError,
    AIProviderModel,
    AIProviderModelList,
    AIProviderQuotaError,
    AIProviderRuntime,
    map_provider_exception,
    run_provider_operation,
)

ResponseT = TypeVar("ResponseT", bound=BaseModel)
OperationT = TypeVar("OperationT")

MAX_PROMPT_BYTES = 128 * 1024
MAX_MODEL_LENGTH = 256
MAX_RESPONSE_BYTES = 2 * 1024 * 1024

_JSON_FENCE = re.compile(r"\A```(?:json)?[ \t]*\r?\n(?P<body>.*)\r?\n```\Z", re.DOTALL)
_QUOTA_CODES = {"billing_hard_limit_reached", "insufficient_quota", "quota_exceeded"}


@dataclass(frozen=True, slots=True)
class OpenAICompatibleProviderDescriptor:
    provider: str
    generation_path: str
    model_list_path: str | None
    supports_model_listing: bool


OPENAI_COMPATIBLE_DESCRIPTORS: dict[str, OpenAICompatibleProviderDescriptor] = {
    "openai": OpenAICompatibleProviderDescriptor(
        provider="openai",
        generation_path="/chat/completions",
        model_list_path="/models",
        supports_model_listing=True,
    ),
    "deepseek": OpenAICompatibleProviderDescriptor(
        provider="deepseek",
        generation_path="/chat/completions",
        model_list_path="/models",
        supports_model_listing=True,
    ),
    "moonshot": OpenAICompatibleProviderDescriptor(
        provider="moonshot",
        generation_path="/chat/completions",
        model_list_path="/models",
        supports_model_listing=True,
    ),
    "qwen": OpenAICompatibleProviderDescriptor(
        provider="qwen",
        generation_path="/chat/completions",
        model_list_path=None,
        supports_model_listing=False,
    ),
    "custom": OpenAICompatibleProviderDescriptor(
        provider="custom",
        generation_path="/chat/completions",
        model_list_path="/models",
        supports_model_listing=True,
    ),
}


@dataclass(frozen=True, slots=True)
class _OperationFailure:
    error: AIProviderError


def _parse_bounded_json_outcome(
    text: str,
    response_model: type[ResponseT],
) -> ResponseT | _OperationFailure:
    try:
        if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise ValueError("invalid structured response")
        candidate = text.strip()
        fence = _JSON_FENCE.fullmatch(candidate)
        if fence is not None:
            candidate = fence.group("body").strip()
        parsed = json.loads(candidate)
        if not isinstance(parsed, dict):
            raise ValueError("structured response must be an object")
        return response_model.model_validate(parsed)
    except (TypeError, ValueError, json.JSONDecodeError, ValidationError) as source:
        source.__traceback__ = None
        del source, text, response_model
        return _OperationFailure(AIProviderInvalidResponseError())


def parse_bounded_json(text: str, response_model: type[ResponseT]) -> ResponseT:
    outcome = _parse_bounded_json_outcome(text, response_model)
    del text, response_model
    if isinstance(outcome, _OperationFailure):
        error = outcome.error
        del outcome
        raise error from None
    return outcome


async def _capture_provider_operation(
    operation: Callable[[], Awaitable[OperationT]],
) -> OperationT | _OperationFailure:
    try:
        return await run_provider_operation(operation)
    except AIProviderError as source:
        error = map_provider_exception(source)
        source.__traceback__ = None
        del source, operation
        return _OperationFailure(error)


def _raise_or_return(outcome: OperationT | _OperationFailure) -> OperationT:
    if isinstance(outcome, _OperationFailure):
        error = outcome.error
        del outcome
        raise error from None
    return outcome


class OpenAICompatibleProviderClient(Generic[ResponseT]):
    def __init__(self, runtime: AIProviderRuntime) -> None:
        descriptor = OPENAI_COMPATIBLE_DESCRIPTORS.get(runtime.provider)
        if descriptor is None:
            del runtime
            raise AIProviderInvalidConfigurationError() from None
        self._runtime = runtime
        self._descriptor = descriptor

    async def test_connection(self) -> AIProviderHealth:
        operation = partial(self._test_connection_impl)
        outcome = await _capture_provider_operation(operation)
        del operation, self
        return _raise_or_return(outcome)

    async def list_models(self) -> AIProviderModelList:
        operation = partial(self._list_models_impl)
        outcome = await _capture_provider_operation(operation)
        del operation, self
        return _raise_or_return(outcome)

    async def generate_text(self, prompt: str, model: str | None = None) -> str:
        operation = partial(self._generate_text_impl, prompt, model)
        outcome = await _capture_provider_operation(operation)
        del operation, self, prompt, model
        return _raise_or_return(outcome)

    async def generate_json(
        self,
        prompt: str,
        response_model: type[ResponseT],
        model: str | None = None,
    ) -> ResponseT:
        operation = partial(self._generate_json_impl, prompt, response_model, model)
        outcome = await _capture_provider_operation(operation)
        del operation, self, prompt, response_model, model
        return _raise_or_return(outcome)

    def _validate_runtime(self) -> tuple[str, str]:
        if not self._runtime.enabled:
            raise AIProviderDisabledError()
        credential = self._runtime.get_credential_value()
        if self._runtime.credential_state != "configured" or not credential:
            raise AIProviderInvalidConfigurationError()
        base_url = self._runtime.base_url.rstrip("/")
        if not base_url:
            raise AIProviderInvalidConfigurationError()
        return base_url, credential

    def _url_for(self, path: str) -> str:
        base_url, credential = self._validate_runtime()
        del credential
        return f"{base_url}{path}"

    def _validated_target(self, url: str) -> ValidatedCloudProviderTarget:
        return validate_cloud_provider_target(
            url,
            allowed_private_origins=get_settings().ai_provider_allowed_private_origins,
        )

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self._runtime.connect_timeout_seconds,
            read=self._runtime.read_timeout_seconds,
            write=self._runtime.connect_timeout_seconds,
            pool=self._runtime.connect_timeout_seconds,
        )

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        model_listing: bool = False,
    ) -> tuple[Literal["ok", "unsupported"], dict[str, Any] | None]:
        _, credential = self._validate_runtime()
        target = self._validated_target(self._url_for(path))
        transport = create_pinned_async_transport(target, verify=self._runtime.verify_tls)
        headers = {
            "Authorization": f"Bearer {credential}",
            "Accept-Encoding": "identity",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(
            transport=transport,
            timeout=self._timeout(),
            follow_redirects=CLOUD_PROVIDER_FOLLOW_REDIRECTS,
            headers=headers,
        ) as client:
            async with client.stream(method, target.url, json=payload) as response:
                if 300 <= response.status_code < 400:
                    raise AIProviderInvalidConfigurationError(reason="redirect_not_allowed")
                if model_listing and response.status_code in {404, 405}:
                    return "unsupported", None
                if response.status_code in {401, 402, 403, 404, 422, 429} or response.status_code >= 500:
                    response.raise_for_status()

                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        if int(content_length) > MAX_RESPONSE_BYTES:
                            raise AIProviderInvalidResponseError()
                    except ValueError:
                        raise AIProviderInvalidResponseError() from None

                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                    if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise AIProviderInvalidResponseError()
                    body.extend(chunk)

                try:
                    parsed = json.loads(body)
                except (TypeError, ValueError, json.JSONDecodeError):
                    parsed = None
                if response.status_code >= 400:
                    if self._is_quota_payload(response.status_code, parsed):
                        raise AIProviderQuotaError(status_code=response.status_code)
                    response.raise_for_status()
        if not isinstance(parsed, dict):
            raise AIProviderInvalidResponseError()
        return "ok", parsed

    @staticmethod
    def _is_quota_payload(status_code: int, payload: object) -> bool:
        if status_code == 402:
            return True
        if not isinstance(payload, dict) or not isinstance(payload.get("error"), dict):
            return False
        error = payload["error"]
        return error.get("type") in _QUOTA_CODES or error.get("code") in _QUOTA_CODES

    async def _list_models_impl(self) -> AIProviderModelList:
        if not self._descriptor.supports_model_listing or self._descriptor.model_list_path is None:
            self._validate_runtime()
            self._validated_target(self._runtime.base_url.rstrip("/"))
            return AIProviderModelList(capability="unsupported")
        capability, payload = await self._request_json(
            "GET",
            self._descriptor.model_list_path,
            model_listing=True,
        )
        if capability == "unsupported":
            return AIProviderModelList(capability="unsupported")
        if payload is None or not isinstance(payload.get("data"), list):
            raise AIProviderInvalidResponseError()
        model_ids: set[str] = set()
        for item in payload["data"]:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise AIProviderInvalidResponseError()
            model_id = item["id"].strip()
            if not model_id or len(model_id) > MAX_MODEL_LENGTH:
                raise AIProviderInvalidResponseError()
            model_ids.add(model_id)
        models = tuple(
            AIProviderModel(provider=self._runtime.provider, id=model_id, name=model_id)
            for model_id in sorted(model_ids)
        )
        return AIProviderModelList(capability="supported", models=models)

    async def _test_connection_impl(self) -> AIProviderHealth:
        result = await self._list_models_impl()
        status: Literal["available", "unchecked"]
        message: str
        if result.capability == "supported":
            status = "available"
            message = "连接正常"
        else:
            status = "unchecked"
            message = "供应商不支持非计费连接检查"
        return AIProviderHealth(
            provider=self._runtime.provider,
            status=status,
            message=message,
            checked_at=datetime.now(tz=UTC),
            effective_model=self._runtime.default_model,
            safe_base_url=self._runtime.base_url,
            credential_state=self._runtime.credential_state,
        )

    def _validated_generation_input(self, prompt: str, model: str | None) -> tuple[str, str]:
        if not isinstance(prompt, str) or not prompt or len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
            raise AIProviderInvalidConfigurationError()
        selected_model = model if model is not None else self._runtime.default_model
        if (
            not isinstance(selected_model, str)
            or not selected_model
            or selected_model != selected_model.strip()
            or len(selected_model) > MAX_MODEL_LENGTH
        ):
            raise AIProviderInvalidConfigurationError()
        return prompt, selected_model

    async def _generate_text_impl(self, prompt: str, model: str | None) -> str:
        prompt, selected_model = self._validated_generation_input(prompt, model)
        _, payload = await self._request_json(
            "POST",
            self._descriptor.generation_path,
            payload={
                "model": selected_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
        )
        if payload is None:
            raise AIProviderInvalidResponseError()
        choices = payload.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise AIProviderInvalidResponseError()
        choice = choices[0]
        if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
            raise AIProviderInvalidResponseError()
        message = choice["message"]
        content = message.get("content")
        if message.get("role") != "assistant" or not isinstance(content, str) or not content.strip():
            raise AIProviderInvalidResponseError()
        if len(content.encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise AIProviderInvalidResponseError()
        return content

    async def _generate_json_impl(
        self,
        prompt: str,
        response_model: type[ResponseT],
        model: str | None,
    ) -> ResponseT:
        text = await self._generate_text_impl(prompt, model)
        return parse_bounded_json(text, response_model)


__all__ = [
    "AIProviderModelList",
    "MAX_MODEL_LENGTH",
    "MAX_PROMPT_BYTES",
    "MAX_RESPONSE_BYTES",
    "OPENAI_COMPATIBLE_DESCRIPTORS",
    "OpenAICompatibleProviderClient",
    "OpenAICompatibleProviderDescriptor",
    "parse_bounded_json",
]
