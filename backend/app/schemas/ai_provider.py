from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.ai_setting import AIProvider


class AIProviderModelResponse(BaseModel):
    provider: AIProvider
    id: str
    name: str


class AIProviderStatusResponse(BaseModel):
    provider: AIProvider
    status: Literal["available", "unavailable", "unchecked"]
    message: str
    checked_at: datetime
    effective_model: str
    safe_base_url: str
    credential_state: Literal["missing", "configured", "unusable"]
    models: list[AIProviderModelResponse] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
