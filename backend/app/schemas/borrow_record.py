from __future__ import annotations

from datetime import datetime, date
from typing import Literal, Optional

from pydantic import BaseModel


BorrowStatus = Literal["active", "returned", "overdue"]


class BookBasicInfo(BaseModel):
    id: int
    title: str
    author: Optional[str] = None
    isbn: Optional[str] = None
    cover_url: Optional[str] = None

    model_config = {"from_attributes": True}


class BorrowRecordBase(BaseModel):
    book_id: int
    borrower_name: str
    borrower_contact: Optional[str] = None
    borrowed_at: date
    due_at: Optional[date] = None
    note: Optional[str] = None


class BorrowRecordCreate(BorrowRecordBase):
    pass


class BorrowReturn(BaseModel):
    returned_at: date
    note: Optional[str] = None


class BorrowRecordResponse(BorrowRecordBase):
    id: int
    returned_at: Optional[date] = None
    status: BorrowStatus
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    book: Optional[BookBasicInfo] = None

    model_config = {"from_attributes": True}


class PaginatedBorrowRecords(BaseModel):
    items: list[BorrowRecordResponse]
    total: int
    page: int
    page_size: int
