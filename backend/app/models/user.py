from __future__ import annotations
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Integer, String, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

if TYPE_CHECKING:
    from .book import Book
    from .borrow_record import BorrowRecord
    from .reading_note import ReadingNote
    from .ai_task import AITask


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    books_created: Mapped[List["Book"]] = relationship("Book", foreign_keys="Book.created_by", back_populates="creator")
    books_updated: Mapped[List["Book"]] = relationship("Book", foreign_keys="Book.updated_by", back_populates="updater")
    borrow_records: Mapped[List["BorrowRecord"]] = relationship("BorrowRecord", back_populates="creator")
    reading_notes: Mapped[List["ReadingNote"]] = relationship("ReadingNote", back_populates="user")
    ai_tasks: Mapped[List["AITask"]] = relationship("AITask", back_populates="creator")

    __table_args__ = (
        Index("idx_users_username", "username"),
        Index("idx_users_role", "role"),
        Index("idx_users_status", "status"),
    )
