from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, SecretStr, field_validator

from app.schemas.ai_setting import AIProvider


class AIProviderModelResponse(BaseModel):
    provider: AIProvider
    id: str
    name: str


class AIProviderStatusResponse(BaseModel):
    provider: AIProvider
    status: Literal["available", "unavailable", "unchecked"]
    message: str
    checked_at: datetime | None = None
    effective_model: str
    safe_base_url: str
    credential_state: Literal["missing", "configured", "unusable"]
    models: list[AIProviderModelResponse] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class AIProviderOperationRequest(BaseModel):
    provider: AIProvider | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: SecretStr | None = None

    @field_validator("base_url", "model")
    @classmethod
    def reject_blank_or_untrimmed_override(cls, value: str | None) -> str | None:
        if value is not None and (not value or value != value.strip()):
            raise ValueError("临时配置字段不能为空或包含首尾空白")
        return value
