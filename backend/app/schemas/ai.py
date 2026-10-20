from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, StrictBool, field_validator, model_validator

from app.schemas.ai_setting import OllamaRuntimeStatus

BookStatus = Literal["available", "borrowed", "lost", "pending", "gifted"]
ReadStatus = Literal["unread", "reading", "read", "paused"]


class AIBaseRequest(BaseModel):
    model: str | None = None


class OllamaModel(BaseModel):
    name: str
    model: str | None = None
    modified_at: str | None = None
    size: int | None = None
    digest: str | None = None
    details: dict[str, Any] | None = None


class OllamaModelsResponse(BaseModel):
    models: list[OllamaModel] = Field(default_factory=list)


class OllamaVersionResponse(BaseModel):
    version: str


class OllamaRunningModel(OllamaModel):
    expires_at: str | None = None
    size_vram: int | None = None


class OllamaRunningModelsResponse(BaseModel):
    models: list[OllamaRunningModel] = Field(default_factory=list)


class OllamaGenerateResponse(BaseModel):
    response: str


class OllamaChatMessage(BaseModel):
    role: str
    content: str


class OllamaChatResponse(BaseModel):
    message: OllamaChatMessage


class AIConnectionTestRequest(BaseModel):
    generate: StrictBool = False


class AIHealthResponse(BaseModel):
    status: Literal["unchecked", "healthy", "error"] = "unchecked"
    message: str = "尚未检查"
    checked_at: datetime | None = None
    version: str | None = None
    installed_model_count: int = 0
    running_model_count: int = 0
    generated: bool = False
    ollama_runtime: OllamaRuntimeStatus | None = None


class ClassifyBookRequest(AIBaseRequest):
    title: str
    author: str | None = None
    publisher: str | None = None
    summary: str | None = None


class ClassifyBookResponse(BaseModel):
    category_code: str
    category_name: str
    confidence: float = Field(ge=0, le=1)
    tags: list[str] = Field(default_factory=list)
    reason: str
    model: str


class GenerateTagsRequest(AIBaseRequest):
    title: str
    author: str | None = None
    publisher: str | None = None
    summary: str | None = None
    category_name: str | None = None
    existing_tags: list[str] = Field(default_factory=list)


class GenerateTagsResponse(BaseModel):
    tags: list[str] = Field(default_factory=list)
    reason: str | None = None
    model: str

    @field_validator("tags")
    @classmethod
    def tags_not_empty(cls, value: list[str]) -> list[str]:
        return [tag.strip() for tag in value if tag.strip()]


class BookContentCandidate(BaseModel):
    source: str
    source_id: str | None = None
    title: str | None = None
    subtitle: str | None = None
    author: str | None = None
    translator: str | None = None
    publisher: str | None = None
    publish_year: int | None = None
    isbn: str | None = None
    language: str | None = None
    pages: int | None = None
    cover_url: str | None = None
    summary: str | None = None
    author_intro: str | None = None
    binding: str | None = None
    series: str | None = None
    note: str | None = None
    raw: dict[str, Any] | None = None


class BookContentFields(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    author: str | None = None
    translator: str | None = None
    publisher: str | None = None
    publish_year: int | None = None
    isbn: str | None = None
    language: str | None = None
    pages: int | None = None
    cover_url: str | None = None
    summary: str | None = None
    author_intro: str | None = None
    binding: str | None = None
    series: str | None = None
    note: str | None = None


class RecommendBookContentRequest(AIBaseRequest):
    current: BookContentFields
    candidates: list[BookContentCandidate] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)


class RecommendBookContentResponse(BaseModel):
    recommended: BookContentFields = Field(default_factory=BookContentFields)
    source_summary: str = ""
    confidence: float = Field(default=0.5, ge=0, le=1)
    reason: str = ""
    model: str


class SummarizeBookRequest(AIBaseRequest):
    title: str
    author: str | None = None
    publisher: str | None = None
    raw_summary: str | None = None
    raw_author_intro: str | None = None


class SummarizeBookResponse(BaseModel):
    summary: str
    author_intro: str = ""
    model: str


class BookDuplicateCandidate(BaseModel):
    title: str
    author: str | None = None
    publisher: str | None = None
    publish_year: int | None = None
    isbn: str | None = None
    summary: str | None = None


class DetectDuplicateRequest(AIBaseRequest):
    first: BookDuplicateCandidate
    second: BookDuplicateCandidate


class DetectDuplicateResponse(BaseModel):
    is_duplicate: bool
    confidence: float = Field(ge=0, le=1)
    reason: str
    model: str


class NaturalSearchRequest(AIBaseRequest):
    query: str


class NaturalSearchResponse(BaseModel):
    keyword: str | None = None
    category_code: str | None = None
    category_name: str | None = None
    location_keyword: str | None = None
    status: BookStatus | None = None
    read_status: ReadStatus | None = None
    is_favorite: bool | None = None
    publish_year_from: int | None = None
    publish_year_to: int | None = None
    tags: list[str] = Field(default_factory=list)
    model: str

    @model_validator(mode="after")
    def validate_year_range(self) -> NaturalSearchResponse:
        if (
            self.publish_year_from is not None
            and self.publish_year_to is not None
            and self.publish_year_from > self.publish_year_to
        ):
            raise ValueError("publish_year_from 不能大于 publish_year_to")
        return self


class OllamaRawJSON(BaseModel):
    data: dict[str, Any]
