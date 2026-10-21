from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SystemAISetting(Base):
    """One optional database override of environment-level AI server settings."""

    __tablename__ = "system_ai_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_base_url: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    trusted_base_url: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    default_model: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    connect_timeout_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=20.0)
    read_timeout_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=180.0)
    verify_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    access_client_id_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_client_secret_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now,
    )

    __table_args__ = (CheckConstraint("id = 1", name="ck_system_ai_settings_singleton"),)

    # Optimistic concurrency applies to both UPDATE and DELETE across instances.
    __mapper_args__ = {"version_id_col": config_version, "version_id_generator": False}
