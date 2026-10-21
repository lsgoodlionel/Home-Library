from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from typing import Any, Awaitable, Callable, Generic, TypeVar
from urllib.parse import quote

import httpx
from pydantic import BaseModel

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
from app.services.ai_providers.openai_compatible import (
    MAX_MODEL_LENGTH,
    MAX_PROMPT_BYTES,
    MAX_RESPONSE_BYTES,
    parse_bounded_json,
)

ResponseT = TypeVar("ResponseT", bound=BaseModel)
OperationT = TypeVar("OperationT")

MAX_MODEL_PAGES = 20
MAX_PAGE_TOKEN_LENGTH = 2048
MAX_TOTAL_MODELS = 1000

_MODEL_LIST_PATH = "/v1beta/models"
_GENERATE_PATH_PREFIX = "/v1beta/models/"
_GENERATE_PATH_SUFFIX = ":generateContent"
_QUOTA_STATUS = "RESOURCE_EXHAUSTED"
_BLOCKED_FINISH_REASONS = {"BLOCKLIST", "PROHIBITED_CONTENT", "RECITATION", "SAFETY", "SPII"}


@dataclass(frozen=True, slots=True)
class _OperationFailure:
    error: AIProviderError


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


class GeminiProviderClient(Generic[ResponseT]):
    def __init__(self, runtime: AIProviderRuntime) -> None:
        if runtime.provider != "gemini":
            del runtime
            raise AIProviderInvalidConfigurationError() from None
        self._runtime = runtime

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
        params: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _, credential = self._validate_runtime()
        target = self._validated_target(self._url_for(path))
        transport = create_pinned_async_transport(target, verify=self._runtime.verify_tls)
        headers = {
            "x-goog-api-key": credential,
            "Accept-Encoding": "identity",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(
            transport=transport,
            timeout=self._timeout(),
            follow_redirects=CLOUD_PROVIDER_FOLLOW_REDIRECTS,
            headers=headers,
        ) as client:
            async with client.stream(
                method,
                target.url,
                params=params,
                json=payload,
            ) as response:
                if 300 <= response.status_code < 400:
                    raise AIProviderInvalidConfigurationError(reason="redirect_not_allowed")
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
                    if self._is_quota_payload(parsed):
                        raise AIProviderQuotaError(status_code=response.status_code)
                    response.raise_for_status()
        if not isinstance(parsed, dict):
            raise AIProviderInvalidResponseError()
        return parsed

    @staticmethod
    def _is_quota_payload(payload: object) -> bool:
        if not isinstance(payload, dict) or not isinstance(payload.get("error"), dict):
            return False
        return payload["error"].get("status") == _QUOTA_STATUS

    @staticmethod
    def _canonical_model_id(model: object) -> str:
        if not isinstance(model, str) or not model or model != model.strip():
            raise AIProviderInvalidConfigurationError()
        canonical = model.removeprefix("models/")
        if not canonical or len(canonical) > MAX_MODEL_LENGTH:
            raise AIProviderInvalidConfigurationError()
        return canonical

    @classmethod
    def _model_from_native(cls, item: object) -> tuple[str, str] | None:
        if not isinstance(item, dict):
            raise AIProviderInvalidResponseError()
        methods = item.get("supportedGenerationMethods")
        if not isinstance(methods, list) or not all(isinstance(method, str) for method in methods):
            raise AIProviderInvalidResponseError()
        if "generateContent" not in methods:
            return None
        try:
            model_id = cls._canonical_model_id(item.get("name"))
        except AIProviderInvalidConfigurationError:
            raise AIProviderInvalidResponseError() from None
        display_name = item.get("displayName", model_id)
        if not isinstance(display_name, str) or not display_name.strip():
            raise AIProviderInvalidResponseError()
        return model_id, display_name

    async def _list_models_impl(self) -> AIProviderModelList:
        page_token: str | None = None
        seen_tokens: set[str] = set()
        models: dict[str, str] = {}
        total_models = 0

        for page_number in range(MAX_MODEL_PAGES):
            params = {"pageToken": page_token} if page_token is not None else None
            payload = await self._request_json("GET", _MODEL_LIST_PATH, params=params)
            native_models = payload.get("models")
            if not isinstance(native_models, list):
                raise AIProviderInvalidResponseError()
            total_models += len(native_models)
            if total_models > MAX_TOTAL_MODELS:
                raise AIProviderInvalidResponseError()
            for item in native_models:
                mapped = self._model_from_native(item)
                if mapped is not None:
                    model_id, display_name = mapped
                    models.setdefault(model_id, display_name)

            next_token = payload.get("nextPageToken")
            if next_token is None or next_token == "":
                break
            if (
                not isinstance(next_token, str)
                or len(next_token.encode("utf-8")) > MAX_PAGE_TOKEN_LENGTH
                or next_token in seen_tokens
            ):
                raise AIProviderInvalidResponseError()
            seen_tokens.add(next_token)
            page_token = next_token
            if page_number == MAX_MODEL_PAGES - 1:
                raise AIProviderInvalidResponseError()
        else:
            raise AIProviderInvalidResponseError()

        return AIProviderModelList(
            capability="supported",
            models=tuple(
                AIProviderModel(provider="gemini", id=model_id, name=models[model_id])
                for model_id in sorted(models)
            ),
        )

    async def _test_connection_impl(self) -> AIProviderHealth:
        await self._list_models_impl()
        effective_model = self._canonical_model_id(self._runtime.default_model)
        return AIProviderHealth(
            provider="gemini",
            status="available",
            message="连接正常",
            checked_at=datetime.now(tz=UTC),
            effective_model=effective_model,
            safe_base_url=self._runtime.base_url,
            credential_state=self._runtime.credential_state,
        )

    def _validated_generation_input(self, prompt: str, model: str | None) -> tuple[str, str]:
        if not isinstance(prompt, str) or not prompt or len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
            raise AIProviderInvalidConfigurationError()
        selected_model = model if model is not None else self._runtime.default_model
        return prompt, self._canonical_model_id(selected_model)

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str:
        prompt_feedback = payload.get("promptFeedback")
        if isinstance(prompt_feedback, dict) and prompt_feedback.get("blockReason"):
            raise AIProviderInvalidResponseError()
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise AIProviderInvalidResponseError()

        usable: list[str] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                raise AIProviderInvalidResponseError()
            if candidate.get("finishReason") in _BLOCKED_FINISH_REASONS:
                continue
            content = candidate.get("content")
            if content is None:
                continue
            if not isinstance(content, dict) or content.get("role") != "model":
                raise AIProviderInvalidResponseError()
            parts = content.get("parts")
            if not isinstance(parts, list):
                raise AIProviderInvalidResponseError()
            text_parts: list[str] = []
            for part in parts:
                if not isinstance(part, dict):
                    raise AIProviderInvalidResponseError()
                if "text" not in part:
                    continue
                text = part["text"]
                if not isinstance(text, str):
                    raise AIProviderInvalidResponseError()
                if text:
                    text_parts.append(text)
            text = "".join(text_parts)
            if text.strip():
                usable.append(text)

        if len(usable) != 1 or len(usable[0].encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise AIProviderInvalidResponseError()
        return usable[0]

    async def _generate_text_impl(self, prompt: str, model: str | None) -> str:
        prompt, selected_model = self._validated_generation_input(prompt, model)
        encoded_model = quote(selected_model, safe="")
        payload = await self._request_json(
            "POST",
            f"{_GENERATE_PATH_PREFIX}{encoded_model}{_GENERATE_PATH_SUFFIX}",
            payload={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            },
        )
        return self._extract_text(payload)

    async def _generate_json_impl(
        self,
        prompt: str,
        response_model: type[ResponseT],
        model: str | None,
    ) -> ResponseT:
        text = await self._generate_text_impl(prompt, model)
        return parse_bounded_json(text, response_model)


__all__ = [
    "GeminiProviderClient",
    "MAX_MODEL_PAGES",
    "MAX_PAGE_TOKEN_LENGTH",
    "MAX_TOTAL_MODELS",
]
