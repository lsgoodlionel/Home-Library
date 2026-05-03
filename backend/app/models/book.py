from __future__ import annotations
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Integer, String, Text, Boolean, ForeignKey, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

if TYPE_CHECKING:
    from .user import User
    from .category import Category
    from .location import Location
    from .tag import Tag
    from .borrow_record import BorrowRecord
    from .reading_note import ReadingNote


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    subtitle: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    translator: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    publish_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    isbn: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    original_isbn: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    pages: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    price_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    binding: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    series: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cover_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author_intro: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("categories.id"), nullable=True)
    location_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("locations.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="available")
    read_status: Mapped[str] = mapped_column(String(20), nullable=False, default="unread")
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    category: Mapped[Optional["Category"]] = relationship("Category", back_populates="books")
    location: Mapped[Optional["Location"]] = relationship("Location", back_populates="books")
    creator: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by], back_populates="books_created")
    updater: Mapped[Optional["User"]] = relationship("User", foreign_keys=[updated_by], back_populates="books_updated")
    book_tags: Mapped[List["BookTag"]] = relationship("BookTag", back_populates="book", cascade="all, delete-orphan")
    borrow_records: Mapped[List["BorrowRecord"]] = relationship("BorrowRecord", back_populates="book")
    reading_notes: Mapped[List["ReadingNote"]] = relationship("ReadingNote", back_populates="book")

    __table_args__ = (
        Index("idx_books_title", "title"),
        Index("idx_books_author", "author"),
        Index("idx_books_isbn", "isbn"),
        Index("idx_books_publisher", "publisher"),
        Index("idx_books_category_id", "category_id"),
        Index("idx_books_location_id", "location_id"),
        Index("idx_books_status", "status"),
        Index("idx_books_read_status", "read_status"),
        Index("idx_books_created_at", "created_at"),
    )


class BookTag(Base):
    __tablename__ = "book_tags"

    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(Integer, ForeignKey("tags.id"), primary_key=True)

    book: Mapped["Book"] = relationship("Book", back_populates="book_tags")
    tag: Mapped["Tag"] = relationship("Tag", back_populates="book_tags")

    __table_args__ = (
        Index("idx_book_tags_book_id", "book_id"),
        Index("idx_book_tags_tag_id", "tag_id"),
    )
