from __future__ import annotations

from datetime import datetime, date
from typing import Literal, Optional

from pydantic import BaseModel, field_validator


ReadStatus = Literal["unread", "reading", "read", "paused"]


class BookBasicInfo(BaseModel):
    id: int
    title: str
    author: Optional[str] = None
    cover_url: Optional[str] = None

    model_config = {"from_attributes": True}


class ReadingNoteBase(BaseModel):
    title: str
    content: Optional[str] = None
    progress: Optional[int] = None
    rating: Optional[int] = None
    started_at: Optional[date] = None
    finished_at: Optional[date] = None

    @field_validator("progress")
    @classmethod
    def progress_range(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("进度必须在 0-100 之间")
        return v

    @field_validator("rating")
    @classmethod
    def rating_range(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 5):
            raise ValueError("评分必须在 1-5 之间")
        return v


class ReadingNoteCreate(ReadingNoteBase):
    pass


class ReadingNoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    progress: Optional[int] = None
    rating: Optional[int] = None
    started_at: Optional[date] = None
    finished_at: Optional[date] = None

    @field_validator("progress")
    @classmethod
    def progress_range(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("进度必须在 0-100 之间")
        return v

    @field_validator("rating")
    @classmethod
    def rating_range(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 5):
            raise ValueError("评分必须在 1-5 之间")
        return v


class ReadingNoteResponse(ReadingNoteBase):
    id: int
    book_id: int
    book: Optional[BookBasicInfo] = None
    user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReadStatusUpdate(BaseModel):
    read_status: ReadStatus
