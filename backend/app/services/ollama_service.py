from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.schemas.ai import OllamaModelsResponse

T = TypeVar("T", bound=BaseModel)

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"


class OllamaServiceError(Exception):
    """Raised when the local Ollama service cannot provide a usable response."""


class OllamaUnavailableError(OllamaServiceError):
    pass


class OllamaInvalidJSONError(OllamaServiceError):
    pass


class OllamaValidationError(OllamaServiceError):
    pass


def load_prompt_template(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


class OllamaService:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        base_url: str | None = None,
        default_model: str | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.base_url = (base_url or self.settings.ollama_base_url).rstrip("/")
        self.default_model = default_model or self.settings.ollama_default_model
        self.timeout = self.settings.ollama_timeout_seconds

    def list_models(self) -> OllamaModelsResponse:
        response: httpx.Response | None = None
        try:
            response = self._request("GET", "/api/tags")
        except httpx.HTTPError as exc:
            raise OllamaUnavailableError(_ollama_unavailable_message(self.base_url)) from exc

        try:
            return OllamaModelsResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise OllamaValidationError("Ollama 模型列表响应格式无效") from exc

    def generate_json(
        self,
        *,
        prompt: str,
        response_model: type[T],
        model: str | None = None,
    ) -> T:
        selected_model = model or self.default_model
        payload = {
            "model": selected_model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }

        try:
            response = self._request("POST", "/api/generate", json=payload)
        except httpx.HTTPError as exc:
            raise OllamaUnavailableError(_ollama_unavailable_message(self.base_url)) from exc

        try:
            raw = response.json()
        except ValueError as exc:
            raise OllamaInvalidJSONError("Ollama HTTP 响应不是合法 JSON") from exc

        content = raw.get("response")
        if not isinstance(content, str):
            raise OllamaInvalidJSONError("Ollama 响应缺少 response 文本")

        data = _parse_model_json(content)
        data.setdefault("model", selected_model)

        try:
            return response_model.model_validate(data)
        except ValidationError as exc:
            raise OllamaValidationError("模型输出不符合预期结构") from exc

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        last_exc: httpx.HTTPError | None = None
        for base_url in _candidate_base_urls(self.base_url):
            try:
                with httpx.Client(base_url=base_url, timeout=self.timeout) as client:
                    response = client.request(method, path, **kwargs)
                    response.raise_for_status()
                    return response
            except httpx.HTTPError as exc:
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        raise httpx.ConnectError("No Ollama base URL configured")


def _parse_model_json(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise OllamaInvalidJSONError("模型输出不是合法 JSON") from exc

    if not isinstance(data, dict):
        raise OllamaInvalidJSONError("模型输出 JSON 必须是对象")
    return data


def _candidate_base_urls(base_url: str) -> list[str]:
    candidates = [base_url.rstrip("/")]
    parsed = urlsplit(base_url)
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        netloc = "host.docker.internal"
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        docker_host_url = urlunsplit((parsed.scheme or "http", netloc, parsed.path, "", "")).rstrip("/")
        if docker_host_url not in candidates:
            candidates.append(docker_host_url)
    return candidates


def _ollama_unavailable_message(base_url: str) -> str:
    candidates = _candidate_base_urls(base_url)
    if len(candidates) > 1:
        return (
            "Ollama 服务不可用。已尝试配置地址及 Docker 宿主机地址："
            f"{', '.join(candidates)}。请确认 Ollama 已启动并允许网络访问。"
        )
    return "Ollama 服务不可用，请确认本地 Ollama 已启动"
