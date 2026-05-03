from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class StatBookSummary(BaseModel):
    id: int
    title: str
    author: Optional[str] = None
    category_name: Optional[str] = None
    location_path: Optional[str] = None
    created_at: datetime


class ActiveBorrowSummary(BaseModel):
    id: int
    book_id: int
    book_title: str
    borrower_name: str
    borrowed_at: date
    due_at: Optional[date] = None


class StatsOverview(BaseModel):
    total_books: int
    available_books: int
    borrowed_books: int
    read_books: int
    unread_books: int
    favorite_books: int
    recent_books: list[StatBookSummary]
    active_borrows: list[ActiveBorrowSummary]


class DistributionItem(BaseModel):
    id: Optional[int] = None
    code: Optional[str] = None
    name: str
    count: int


class ReadingStats(BaseModel):
    unread: int
    reading: int
    read: int
    paused: int


class TimelinePoint(BaseModel):
    period: str
    count: int
