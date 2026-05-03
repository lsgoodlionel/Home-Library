from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional, List
from pydantic import BaseModel, field_validator
from .category import CategoryBrief
from .location import LocationBrief
from .tag import TagResponse


BookStatus = Literal["available", "borrowed", "lost", "pending", "gifted"]
ReadStatus = Literal["unread", "reading", "read", "paused"]
BookSource = Literal["manual", "isbn_lookup", "title_search", "ollama", "import"]


class BookBase(BaseModel):
    title: str
    subtitle: Optional[str] = None
    author: Optional[str] = None
    translator: Optional[str] = None
    publisher: Optional[str] = None
    publish_year: Optional[int] = None
    isbn: Optional[str] = None
    original_isbn: Optional[str] = None
    language: Optional[str] = None
    pages: Optional[int] = None
    price_cents: Optional[int] = None
    binding: Optional[str] = None
    series: Optional[str] = None
    cover_url: Optional[str] = None
    summary: Optional[str] = None
    author_intro: Optional[str] = None
    category_id: Optional[int] = None
    location_id: Optional[int] = None
    status: BookStatus = "available"
    read_status: ReadStatus = "unread"
    rating: Optional[int] = None
    is_favorite: bool = False
    note: Optional[str] = None

    @field_validator("rating")
    @classmethod
    def rating_range(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 5):
            raise ValueError("评分必须在 1-5 之间")
        return v


class BookCreate(BookBase):
    source: BookSource = "manual"
    tag_names: List[str] = []


class BookUpdate(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    author: Optional[str] = None
    translator: Optional[str] = None
    publisher: Optional[str] = None
    publish_year: Optional[int] = None
    isbn: Optional[str] = None
    language: Optional[str] = None
    pages: Optional[int] = None
    price_cents: Optional[int] = None
    binding: Optional[str] = None
    series: Optional[str] = None
    cover_url: Optional[str] = None
    summary: Optional[str] = None
    author_intro: Optional[str] = None
    category_id: Optional[int] = None
    location_id: Optional[int] = None
    status: Optional[BookStatus] = None
    read_status: Optional[ReadStatus] = None
    rating: Optional[int] = None
    is_favorite: Optional[bool] = None
    note: Optional[str] = None
    tag_names: Optional[List[str]] = None

    @field_validator("rating")
    @classmethod
    def rating_range(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 5):
            raise ValueError("评分必须在 1-5 之间")
        return v


class BookListItem(BaseModel):
    id: int
    title: str
    subtitle: Optional[str] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    publish_year: Optional[int] = None
    isbn: Optional[str] = None
    cover_url: Optional[str] = None
    category: Optional[CategoryBrief] = None
    location: Optional[LocationBrief] = None
    status: BookStatus
    read_status: ReadStatus
    rating: Optional[int] = None
    is_favorite: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BookResponse(BookBase):
    id: int
    source: BookSource
    category: Optional[CategoryBrief] = None
    location: Optional[LocationBrief] = None
    tags: List[TagResponse] = []
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BookBatchUpdate(BaseModel):
    book_ids: List[int]
    updates: dict


class PaginatedBooks(BaseModel):
    items: List[BookListItem]
    total: int
    page: int
    page_size: int
