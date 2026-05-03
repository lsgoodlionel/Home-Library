from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

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
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.ollama_base_url.rstrip("/")
        self.timeout = self.settings.ollama_timeout_seconds

    def list_models(self) -> OllamaModelsResponse:
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                response = client.get("/api/tags")
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaUnavailableError("Ollama 服务不可用，请确认本地 Ollama 已启动") from exc

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
        selected_model = model or self.settings.ollama_default_model
        payload = {
            "model": selected_model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }

        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                response = client.post("/api/generate", json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaUnavailableError("Ollama 服务不可用，请确认本地 Ollama 已启动") from exc

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
