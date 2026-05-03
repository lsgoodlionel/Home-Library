from __future__ import annotations
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Integer, String, Text, DateTime, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

if TYPE_CHECKING:
    from .book import Book


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room: Mapped[str] = mapped_column(String(80), nullable=False)
    shelf: Mapped[str] = mapped_column(String(80), nullable=False)
    layer: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    position: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    full_path: Mapped[str] = mapped_column(String(400), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    books: Mapped[List["Book"]] = relationship("Book", back_populates="location")

    __table_args__ = (
        Index("idx_locations_room", "room"),
        Index("idx_locations_shelf", "shelf"),
        Index("idx_locations_full_path", "full_path"),
        UniqueConstraint("room", "shelf", "layer", "position", name="uq_locations_path"),
    )
