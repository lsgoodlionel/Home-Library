from __future__ import annotations
from datetime import datetime, date
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Integer, String, Text, Date, ForeignKey, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

if TYPE_CHECKING:
    from .book import Book
    from .user import User


class ReadingNote(Base):
    __tablename__ = "reading_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    progress: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    finished_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    book: Mapped["Book"] = relationship("Book", back_populates="reading_notes")
    user: Mapped["User"] = relationship("User", back_populates="reading_notes")

    __table_args__ = (
        Index("idx_reading_notes_book_id", "book_id"),
        Index("idx_reading_notes_user_id", "user_id"),
    )
