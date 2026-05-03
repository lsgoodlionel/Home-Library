"""Schemas for external book search candidates and import."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel


class ExternalBookCandidate(BaseModel):
    """Normalized book result from any external provider."""

    source: str
    source_id: Optional[str] = None
    title: str
    subtitle: Optional[str] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    publish_year: Optional[int] = None
    isbn: Optional[str] = None
    cover_url: Optional[str] = None
    summary: Optional[str] = None
    language: Optional[str] = None
    pages: Optional[int] = None
    raw: dict[str, Any] = {}


class ExternalBookSearchResponse(BaseModel):
    items: list[ExternalBookCandidate]


class ImportResultRequest(BaseModel):
    result: ExternalBookCandidate
    category_id: Optional[int] = None
    location_id: Optional[int] = None
    import_mode: Literal["draft", "book"] = "draft"


class ImportResultResponse(BaseModel):
    """Unified response for import-result endpoint.

    draft mode: book_id is None, data is populated for client to pre-fill a form.
    book mode: book_id is the newly created record's id.
    """

    import_mode: Literal["draft", "book"]
    book_id: Optional[int] = None
    title: str
    subtitle: Optional[str] = None
    author: Optional[str] = None
    translator: Optional[str] = None
    publisher: Optional[str] = None
    publish_year: Optional[int] = None
    isbn: Optional[str] = None
    language: Optional[str] = None
    pages: Optional[int] = None
    cover_url: Optional[str] = None
    summary: Optional[str] = None
    category_id: Optional[int] = None
    location_id: Optional[int] = None
    source: str
    tag_names: list[str] = []
