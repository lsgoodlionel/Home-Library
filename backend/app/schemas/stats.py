from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RecentBookItem(BaseModel):
    id: int
    title: str
    author: Optional[str] = None
    cover_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ActiveBorrowItem(BaseModel):
    id: int
    book_id: int
    book_title: str
    borrower_name: str
    borrowed_at: str
    due_at: Optional[str] = None

    model_config = {"from_attributes": True}


class OverviewStats(BaseModel):
    total_books: int
    available_books: int
    borrowed_books: int
    read_books: int
    unread_books: int
    favorite_books: int
    recent_books: list[RecentBookItem]
    active_borrows: list[ActiveBorrowItem]


class CategoryDistItem(BaseModel):
    category_id: Optional[int]
    category_code: Optional[str]
    category_name: Optional[str]
    count: int


class LocationDistItem(BaseModel):
    location_id: Optional[int]
    full_path: Optional[str]
    room: Optional[str]
    shelf: Optional[str]
    count: int


class ReadingStats(BaseModel):
    unread: int
    reading: int
    read: int
    paused: int


class TimelinePoint(BaseModel):
    year: int
    month: int
    count: int


class TimelineStats(BaseModel):
    points: list[TimelinePoint]
