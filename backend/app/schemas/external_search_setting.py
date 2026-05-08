from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

ExternalSearchProvider = Literal["google_books", "isbn_work", "douban"]


class ExternalSearchProviderConfig(BaseModel):
    provider: ExternalSearchProvider
    enabled: bool = True
    api_key: str = ""
    extra: str = ""
    note: str = ""
    has_api_key: bool = False
    has_extra: bool = False


class ExternalSearchSettingsResponse(BaseModel):
    providers: list[ExternalSearchProviderConfig] = Field(default_factory=list)


class ExternalSearchProviderConfigUpdate(BaseModel):
    provider: ExternalSearchProvider
    enabled: bool = True
    api_key: str | None = None
    extra: str | None = None
    note: str = ""

    @field_validator("api_key", "extra", "note", mode="before")
    @classmethod
    def clean_optional_text(cls, value: object) -> str | None:
        return value.strip() if isinstance(value, str) else value  # type: ignore[return-value]


class ExternalSearchSettingsUpdate(BaseModel):
    providers: list[ExternalSearchProviderConfigUpdate] = Field(default_factory=list)


class ExternalProviderValidateResponse(BaseModel):
    provider: ExternalSearchProvider
    ok: bool
    message: str
