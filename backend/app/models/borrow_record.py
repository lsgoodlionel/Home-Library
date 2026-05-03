from __future__ import annotations
from datetime import datetime, date
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Integer, String, Text, Date, ForeignKey, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

if TYPE_CHECKING:
    from .book import Book
    from .user import User


class BorrowRecord(Base):
    __tablename__ = "borrow_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id"), nullable=False)
    borrower_name: Mapped[str] = mapped_column(String(120), nullable=False)
    borrower_contact: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    borrowed_at: Mapped[date] = mapped_column(Date, nullable=False)
    due_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    returned_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    book: Mapped["Book"] = relationship("Book", back_populates="borrow_records")
    creator: Mapped[Optional["User"]] = relationship("User", back_populates="borrow_records")

    __table_args__ = (
        Index("idx_borrow_records_book_id", "book_id"),
        Index("idx_borrow_records_status", "status"),
        Index("idx_borrow_records_due_at", "due_at"),
    )
