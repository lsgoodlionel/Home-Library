from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, field_validator

from app.core.ollama_url import InvalidOllamaBaseURL, normalize_ollama_base_url

AIProvider = Literal["ollama", "openai", "gemini", "deepseek", "moonshot", "qwen", "custom"]


class AIProviderConfig(BaseModel):
    provider: AIProvider
    enabled: bool = False
    base_url: str = ""
    api_key: str = ""
    default_model: str = ""
    note: str = ""
    has_api_key: bool = False


class OllamaRuntimeStatus(BaseModel):
    enabled: bool
    base_url: str
    default_model: str
    connect_timeout_seconds: float
    read_timeout_seconds: float
    verify_tls: bool
    access_configured: bool
    uses_access: bool


class AISettingsResponse(BaseModel):
    active_provider: AIProvider = "ollama"
    default_model: str = ""
    providers: list[AIProviderConfig] = Field(default_factory=list)
    ollama_runtime: OllamaRuntimeStatus


class AIProviderConfigUpdate(BaseModel):
    provider: AIProvider
    enabled: bool = False
    base_url: str = ""
    api_key: str | None = None
    default_model: str = ""
    note: str = ""

    @field_validator("default_model", "note", mode="before")
    @classmethod
    def clean_optional_text(cls, value: object) -> str:
        return value.strip() if isinstance(value, str) else ""

    @field_validator("base_url", mode="before")
    @classmethod
    def clean_base_url(cls, value: object) -> str:
        return value if isinstance(value, str) else ""

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        if not value:
            return value
        try:
            return normalize_ollama_base_url(value)
        except InvalidOllamaBaseURL:
            raise ValueError("服务地址必须是包含主机名的 HTTP 或 HTTPS URL")


class AISettingsUpdate(BaseModel):
    active_provider: AIProvider = "ollama"
    default_model: str = ""
    providers: list[AIProviderConfigUpdate] = Field(default_factory=list)

    @field_validator("default_model", mode="before")
    @classmethod
    def clean_default_model(cls, value: object) -> str:
        return value.strip() if isinstance(value, str) else ""
