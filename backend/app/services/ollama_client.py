from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, TypeVar
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, ValidationError

from app.core.ollama_url import InvalidOllamaBaseURL, normalize_ollama_base_url
from app.schemas.ai import (
    OllamaChatResponse,
    OllamaGenerateResponse,
    OllamaModelsResponse,
    OllamaRunningModelsResponse,
    OllamaVersionResponse,
)
from app.services.ai_setting_service import OllamaRuntimeConfig, normalize_access_origin
from app.services.ollama_service import parse_model_json

T = TypeVar("T", bound=BaseModel)

MAX_PROMPT_CHARS = 100_000
MAX_RESPONSE_BYTES = 1_048_576
MAX_GENERATED_TEXT_CHARS = 4_096
CF_ERROR_PREFIX_BYTES = 8 * 1024
_CF_1033_PATTERN = re.compile(rb"(?<!\d)1033(?!\d)")


class OllamaClientError(Exception):
    category = "ollama_error"

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.reason = reason


class OllamaConnectTimeoutError(OllamaClientError):
    category = "connect_timeout"


class OllamaReadTimeoutError(OllamaClientError):
    category = "read_timeout"


class OllamaDisabledError(OllamaClientError):
    category = "disabled"


class OllamaAccessDeniedError(OllamaClientError):
    category = "access_denied"


class OllamaTunnelError(OllamaClientError):
    category = "tunnel"


class OllamaModelError(OllamaClientError):
    category = "model"


class OllamaUpstreamError(OllamaClientError):
    category = "upstream"


class OllamaResponseInvalidError(OllamaClientError):
    category = "response_invalid"


@dataclass(frozen=True)
class _SafeFailure:
    error_type: type[OllamaClientError]
    message: str
    status_code: int | None = None
    reason: str | None = None


class OllamaClient:
    def __init__(
        self,
        runtime: OllamaRuntimeConfig,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.runtime = runtime
        self._transport = transport
        self._timeout = httpx.Timeout(
            connect=runtime.connect_timeout_seconds,
            read=runtime.read_timeout_seconds,
            write=runtime.read_timeout_seconds,
            pool=runtime.connect_timeout_seconds,
        )
        self._headers: dict[str, str] = {"Accept-Encoding": "identity"}
        credentials_complete = bool(runtime.access_client_id and runtime.access_client_secret)
        if (
            credentials_complete
            and normalize_access_origin(runtime.base_url) is not None
            and normalize_access_origin(runtime.base_url)
            == normalize_access_origin(runtime.trusted_base_url)
        ):
            self._headers.update({
                "CF-Access-Client-Id": runtime.access_client_id,
                "CF-Access-Client-Secret": runtime.access_client_secret,
            })

    async def version(self) -> OllamaVersionResponse:
        outcome = await _request_and_validate(self, "GET", "/api/version", OllamaVersionResponse)
        if isinstance(outcome, _SafeFailure):
            del self
            _raise_safe_failure(outcome)
        return outcome

    async def list_models(self) -> OllamaModelsResponse:
        outcome = await _request_and_validate(self, "GET", "/api/tags", OllamaModelsResponse)
        if isinstance(outcome, _SafeFailure):
            del self
            _raise_safe_failure(outcome)
        return outcome

    async def running_models(self) -> OllamaRunningModelsResponse:
        outcome = await _request_and_validate(self, "GET", "/api/ps", OllamaRunningModelsResponse)
        if isinstance(outcome, _SafeFailure):
            del self
            _raise_safe_failure(outcome)
        return outcome

    async def generate_json(
        self,
        *,
        prompt: str,
        response_model: type[T],
        model: str | None = None,
    ) -> T:
        outcome = await _generate_json_result(self, prompt, response_model, model)
        if isinstance(outcome, _SafeFailure):
            del self, prompt, response_model, model
            _raise_safe_failure(outcome)
        return outcome

    async def generate_text(
        self,
        *,
        prompt: str,
        model: str | None = None,
        keep_alive: int | str | None = None,
    ) -> str:
        outcome = await _generate_text_result(self, prompt, model, keep_alive)
        if isinstance(outcome, _SafeFailure):
            del self, prompt, model, keep_alive
            _raise_safe_failure(outcome)
        return outcome

    async def chat(
        self,
        *,
        messages: list[dict[str, str]],
        model: str | None = None,
    ) -> str:
        outcome = await _chat_result(self, messages, model)
        if isinstance(outcome, _SafeFailure):
            del self, messages, model
            _raise_safe_failure(outcome)
        return outcome

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response | _SafeFailure:
        if not self.runtime.enabled:
            return _SafeFailure(OllamaDisabledError, "Ollama is disabled")

        base_urls = _candidate_base_urls(self.runtime.base_url)
        if isinstance(base_urls, _SafeFailure):
            return base_urls
        for base_url_index, base_url in enumerate(base_urls):
            headers = (
                self._headers
                if base_url_index == 0
                else {"Accept-Encoding": "identity"}
            )
            client = _build_async_client(
                base_url=base_url,
                headers=headers,
                timeout=self._timeout,
                verify_tls=self.runtime.verify_tls,
                transport=self._transport,
            )
            if client is None:
                return _SafeFailure(OllamaModelError, "Ollama base URL is invalid")
            async with client:
                connect_attempts = 0
                while True:
                    response_received = False
                    request_error: OllamaClientError | None = None
                    retry_connect = False
                    try:
                        async with client.stream(method, path.lstrip("/"), **kwargs) as response:
                            response_received = True
                            if response.is_error:
                                prefix = await _read_prefix(response, CF_ERROR_PREFIX_BYTES)
                                return _failure_for_status(response.status_code, prefix)
                            content = await _read_bounded(response, MAX_RESPONSE_BYTES)
                            if isinstance(content, _SafeFailure):
                                return content
                            return httpx.Response(
                                response.status_code,
                                headers=response.headers,
                                content=content,
                                request=response.request,
                            )
                    except httpx.ConnectTimeout:
                        request_error = _SafeFailure(
                            OllamaConnectTimeoutError,
                            "Ollama connection timed out",
                        )
                    except httpx.ReadTimeout:
                        request_error = _SafeFailure(
                            OllamaReadTimeoutError,
                            "Ollama response timed out",
                        )
                    except httpx.ConnectError:
                        has_fallback = base_url_index + 1 < len(base_urls)
                        if not response_received and has_fallback:
                            break
                        if not response_received and connect_attempts == 0:
                            connect_attempts += 1
                            retry_connect = True
                        else:
                            request_error = _SafeFailure(
                                OllamaUpstreamError,
                                "Ollama connection failed",
                                reason="connection_failed",
                            )
                    except httpx.RequestError:
                        request_error = _SafeFailure(
                            OllamaUpstreamError,
                            "Ollama request failed",
                            reason="request_failed",
                        )
                    except (httpx.InvalidURL, UnicodeError, ValueError):
                        request_error = _SafeFailure(OllamaModelError, "Ollama base URL is invalid")

                    if retry_connect:
                        continue
                    if request_error is not None:
                        return request_error

        return _SafeFailure(
            OllamaUpstreamError,
            "Ollama connection failed",
            reason="connection_failed",
        )


async def _request_and_validate(
    client: OllamaClient,
    method: str,
    path: str,
    model: type[T],
) -> T | _SafeFailure:
    response = await client._request(method, path)
    if isinstance(response, _SafeFailure):
        return response
    return _validate_response(response, model)


async def _generate_json_result(
    client: OllamaClient,
    prompt: str,
    response_model: type[T],
    model: str | None,
) -> T | _SafeFailure:
    prompt_failure = _validate_prompt_length(prompt)
    if prompt_failure is not None:
        return prompt_failure
    selected_model = model or client.runtime.default_model
    response = await client._request(
        "POST",
        "/api/generate",
        json={
            "model": selected_model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        },
    )
    if isinstance(response, _SafeFailure):
        return response
    envelope = _validate_response(response, OllamaGenerateResponse)
    if isinstance(envelope, _SafeFailure):
        return envelope
    try:
        data = parse_model_json(envelope.response)
        data.setdefault("model", selected_model)
        return response_model.model_validate(data)
    except (ValueError, ValidationError, RecursionError):
        return _SafeFailure(
            OllamaResponseInvalidError,
            "Ollama generated an invalid response",
        )


async def _generate_text_result(
    client: OllamaClient,
    prompt: str,
    model: str | None,
    keep_alive: int | str | None,
) -> str | _SafeFailure:
    prompt_failure = _validate_prompt_length(prompt)
    if prompt_failure is not None:
        return prompt_failure
    payload: dict[str, Any] = {
        "model": model or client.runtime.default_model,
        "prompt": prompt,
        "stream": False,
    }
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
    response = await client._request("POST", "/api/generate", json=payload)
    if isinstance(response, _SafeFailure):
        return response
    envelope = _validate_response(response, OllamaGenerateResponse)
    if isinstance(envelope, _SafeFailure):
        return envelope
    if len(envelope.response) > MAX_GENERATED_TEXT_CHARS:
        return _SafeFailure(
            OllamaResponseInvalidError,
            "Ollama generated text exceeds the maximum length",
        )
    return envelope.response


async def _chat_result(
    client: OllamaClient,
    messages: list[dict[str, str]],
    model: str | None,
) -> str | _SafeFailure:
    serialized_messages = json.dumps(messages, ensure_ascii=False)
    prompt_failure = _validate_prompt_length(serialized_messages)
    if prompt_failure is not None:
        return prompt_failure
    response = await client._request(
        "POST",
        "/api/chat",
        json={
            "model": model or client.runtime.default_model,
            "messages": messages,
            "stream": False,
        },
    )
    if isinstance(response, _SafeFailure):
        return response
    envelope = _validate_response(response, OllamaChatResponse)
    if isinstance(envelope, _SafeFailure):
        return envelope
    return envelope.message.content


def _validate_response(response: httpx.Response, model: type[T]) -> T | _SafeFailure:
    try:
        return model.model_validate(response.json())
    except (ValueError, ValidationError):
        return _SafeFailure(
            OllamaResponseInvalidError,
            "Ollama returned an invalid response",
        )


def _validate_prompt_length(prompt: str) -> _SafeFailure | None:
    if len(prompt) > MAX_PROMPT_CHARS:
        return _SafeFailure(OllamaModelError, "Ollama prompt exceeds the maximum length")
    return None


def _failure_for_status(status_code: int, prefix: bytes) -> _SafeFailure:
    if status_code in {401, 403}:
        return _SafeFailure(
            OllamaAccessDeniedError,
            "Ollama access was denied",
            status_code,
        )
    if _CF_1033_PATTERN.search(prefix):
        return _SafeFailure(OllamaTunnelError, "Ollama tunnel is unavailable", status_code)
    if status_code in {502, 503}:
        return _SafeFailure(OllamaTunnelError, "Ollama tunnel is unavailable", status_code)
    if 400 <= status_code < 500:
        return _SafeFailure(OllamaModelError, "Ollama rejected the request", status_code)
    if 500 <= status_code < 600:
        return _SafeFailure(OllamaUpstreamError, "Ollama upstream failed", status_code)
    return _SafeFailure(
        OllamaUpstreamError,
        "Ollama returned an unexpected status",
        status_code,
    )


def _raise_safe_failure(failure: _SafeFailure) -> None:
    raise failure.error_type(
        failure.message,
        status_code=failure.status_code,
        reason=failure.reason,
    )


async def _read_prefix(response: httpx.Response, limit: int) -> bytes:
    prefix = bytearray()
    async for chunk in response.aiter_bytes():
        remaining = limit - len(prefix)
        if remaining <= 0:
            break
        prefix.extend(chunk[:remaining])
        if len(prefix) >= limit:
            break
    return bytes(prefix)


async def _read_bounded(response: httpx.Response, limit: int) -> bytes | _SafeFailure:
    content = bytearray()
    async for chunk in response.aiter_bytes():
        if len(content) + len(chunk) > limit:
            return _SafeFailure(
                OllamaResponseInvalidError,
                "Ollama response exceeds the maximum length",
            )
        content.extend(chunk)
    return bytes(content)


def _candidate_base_urls(base_url: str) -> list[str] | _SafeFailure:
    try:
        normalized = normalize_ollama_base_url(base_url).rstrip("/")
        parsed = urlsplit(normalized)
        parsed.port
    except (InvalidOllamaBaseURL, ValueError):
        parsed = None
    if parsed is None:
        return _SafeFailure(OllamaModelError, "Ollama base URL is invalid")

    candidates = [normalized]
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        netloc = "host.docker.internal"
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        docker_host_url = urlunsplit((parsed.scheme or "http", netloc, parsed.path, "", "")).rstrip("/")
        candidates.append(docker_host_url)
    return candidates


def _build_async_client(
    *,
    base_url: str,
    headers: dict[str, str],
    timeout: httpx.Timeout,
    verify_tls: bool,
    transport: httpx.AsyncBaseTransport | None,
) -> httpx.AsyncClient | None:
    try:
        return httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/",
            headers=headers,
            timeout=timeout,
            verify=verify_tls,
            transport=transport,
        )
    except (httpx.InvalidURL, UnicodeError, ValueError):
        return None
