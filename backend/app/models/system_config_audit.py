from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SystemConfigAudit(Base):
    """Append-only configuration history storing field names, never field values."""

    __tablename__ = "system_config_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    changed_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        Index("idx_system_config_audits_action", "action"),
        Index("idx_system_config_audits_created_at", "created_at"),
    )
