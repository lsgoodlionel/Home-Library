from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, String, Text, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class ExternalBookResult(Base):
    __tablename__ = "external_book_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    raw_data: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_data: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_external_book_results_query", "query"),
        Index("idx_external_book_results_source", "source"),
        Index("idx_external_book_results_source_id", "source_id"),
    )
