from __future__ import annotations

import json
import re
from typing import Any, TypeVar
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, ValidationError

from app.schemas.ai import (
    OllamaChatResponse,
    OllamaGenerateResponse,
    OllamaModelsResponse,
    OllamaRunningModelsResponse,
    OllamaVersionResponse,
)
from app.services.ai_setting_service import OllamaRuntimeConfig, normalize_ollama_origin
from app.services.ollama_service import parse_model_json

T = TypeVar("T", bound=BaseModel)

MAX_PROMPT_CHARS = 100_000
MAX_RESPONSE_BYTES = 1_048_576
MAX_GENERATED_TEXT_CHARS = 4_096
CF_ERROR_PREFIX_BYTES = 8 * 1024
_CF_1033_PATTERN = re.compile(rb"(?<!\d)1033(?!\d)")


class OllamaClientError(Exception):
    category = "ollama_error"

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


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
        self._headers: dict[str, str] = {}
        credentials_complete = bool(runtime.access_client_id and runtime.access_client_secret)
        if (
            credentials_complete
            and normalize_ollama_origin(runtime.base_url) is not None
            and normalize_ollama_origin(runtime.base_url)
            == normalize_ollama_origin(runtime.trusted_base_url)
        ):
            self._headers = {
                "CF-Access-Client-Id": runtime.access_client_id,
                "CF-Access-Client-Secret": runtime.access_client_secret,
            }

    async def version(self) -> OllamaVersionResponse:
        response = await self._request("GET", "/api/version")
        return self._validate_response(response, OllamaVersionResponse)

    async def list_models(self) -> OllamaModelsResponse:
        response = await self._request("GET", "/api/tags")
        return self._validate_response(response, OllamaModelsResponse)

    async def running_models(self) -> OllamaRunningModelsResponse:
        response = await self._request("GET", "/api/ps")
        return self._validate_response(response, OllamaRunningModelsResponse)

    async def generate_json(
        self,
        *,
        prompt: str,
        response_model: type[T],
        model: str | None = None,
    ) -> T:
        self._validate_prompt_length(prompt)
        selected_model = model or self.runtime.default_model
        response = await self._request(
            "POST",
            "/api/generate",
            json={
                "model": selected_model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            },
        )
        envelope = self._validate_response(response, OllamaGenerateResponse)
        validation_error: OllamaResponseInvalidError | None = None
        try:
            data = parse_model_json(envelope.response)
            data.setdefault("model", selected_model)
            return response_model.model_validate(data)
        except (ValueError, ValidationError):
            validation_error = OllamaResponseInvalidError(
                "Ollama generated an invalid response"
            )
        raise validation_error

    async def generate_text(
        self,
        *,
        prompt: str,
        model: str | None = None,
        keep_alive: int | str | None = None,
    ) -> str:
        self._validate_prompt_length(prompt)
        payload: dict[str, Any] = {
            "model": model or self.runtime.default_model,
            "prompt": prompt,
            "stream": False,
        }
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive
        response = await self._request("POST", "/api/generate", json=payload)
        text = self._validate_response(response, OllamaGenerateResponse).response
        if len(text) > MAX_GENERATED_TEXT_CHARS:
            raise OllamaResponseInvalidError("Ollama generated text exceeds the maximum length")
        return text

    async def chat(
        self,
        *,
        messages: list[dict[str, str]],
        model: str | None = None,
    ) -> str:
        serialized_messages = json.dumps(messages, ensure_ascii=False)
        self._validate_prompt_length(serialized_messages)
        response = await self._request(
            "POST",
            "/api/chat",
            json={
                "model": model or self.runtime.default_model,
                "messages": messages,
                "stream": False,
            },
        )
        envelope = self._validate_response(response, OllamaChatResponse)
        return envelope.message.content

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if not self.runtime.enabled:
            raise OllamaDisabledError("Ollama is disabled")

        base_urls = _candidate_base_urls(self.runtime.base_url)
        for base_url_index, base_url in enumerate(base_urls):
            headers = self._headers if base_url_index == 0 else {}
            async with httpx.AsyncClient(
                base_url=base_url,
                headers=headers,
                timeout=self._timeout,
                verify=self.runtime.verify_tls,
                transport=self._transport,
            ) as client:
                connect_attempts = 0
                while True:
                    response_received = False
                    request_error: OllamaClientError | None = None
                    retry_connect = False
                    try:
                        async with client.stream(method, path, **kwargs) as response:
                            response_received = True
                            if response.is_error:
                                prefix = await _read_prefix(response, CF_ERROR_PREFIX_BYTES)
                                self._raise_for_status(response.status_code, prefix)
                            content = await _read_bounded(response, MAX_RESPONSE_BYTES)
                            return httpx.Response(
                                response.status_code,
                                headers=response.headers,
                                content=content,
                                request=response.request,
                            )
                    except httpx.ConnectTimeout:
                        request_error = OllamaConnectTimeoutError("Ollama connection timed out")
                    except httpx.ReadTimeout:
                        request_error = OllamaReadTimeoutError("Ollama response timed out")
                    except httpx.ConnectError:
                        has_fallback = base_url_index + 1 < len(base_urls)
                        if not response_received and has_fallback:
                            break
                        if not response_received and connect_attempts == 0:
                            connect_attempts += 1
                            retry_connect = True
                        else:
                            request_error = OllamaUpstreamError("Ollama connection failed")
                    except httpx.RequestError:
                        request_error = OllamaUpstreamError("Ollama request failed")

                    if retry_connect:
                        continue
                    if request_error is not None:
                        raise request_error

        raise OllamaUpstreamError("Ollama connection failed")

    @staticmethod
    def _validate_response(response: httpx.Response, model: type[T]) -> T:
        validation_error: OllamaResponseInvalidError | None = None
        try:
            return model.model_validate(response.json())
        except (ValueError, ValidationError):
            validation_error = OllamaResponseInvalidError("Ollama returned an invalid response")
        raise validation_error

    @staticmethod
    def _validate_prompt_length(prompt: str) -> None:
        if len(prompt) > MAX_PROMPT_CHARS:
            raise OllamaModelError("Ollama prompt exceeds the maximum length")

    @staticmethod
    def _raise_for_status(status_code: int, prefix: bytes) -> None:
        if status_code in {401, 403}:
            raise OllamaAccessDeniedError("Ollama access was denied", status_code=status_code)
        if status_code in {502, 503}:
            raise OllamaTunnelError("Ollama tunnel is unavailable", status_code=status_code)
        if 500 <= status_code < 600 and _CF_1033_PATTERN.search(prefix):
            raise OllamaTunnelError("Ollama tunnel is unavailable", status_code=status_code)
        if 400 <= status_code < 500:
            raise OllamaModelError("Ollama rejected the request", status_code=status_code)
        if 500 <= status_code < 600:
            raise OllamaUpstreamError("Ollama upstream failed", status_code=status_code)
        raise OllamaUpstreamError("Ollama returned an unexpected status", status_code=status_code)


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


async def _read_bounded(response: httpx.Response, limit: int) -> bytes:
    content = bytearray()
    async for chunk in response.aiter_bytes():
        if len(content) + len(chunk) > limit:
            raise OllamaResponseInvalidError("Ollama response exceeds the maximum length")
        content.extend(chunk)
    return bytes(content)


def _candidate_base_urls(base_url: str) -> list[str]:
    normalized = base_url.rstrip("/")
    valid = False
    parsed = None
    try:
        parsed = urlsplit(normalized)
        valid = (
            parsed.scheme.lower() in {"http", "https"}
            and parsed.hostname is not None
            and parsed.username is None
            and parsed.password is None
        )
        parsed.port
    except ValueError:
        valid = False
    if not valid or parsed is None:
        raise OllamaModelError("Ollama base URL is invalid")

    candidates = [normalized]
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        netloc = "host.docker.internal"
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        docker_host_url = urlunsplit((parsed.scheme or "http", netloc, parsed.path, "", "")).rstrip("/")
        candidates.append(docker_host_url)
    return candidates
