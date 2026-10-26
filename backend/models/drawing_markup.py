"""Contract-drawing markups. Coordinates are display-frame fractions in [0, 1], y = 0 at the top."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DrawingMarkup(Base):
    __tablename__ = "drawing_markups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    drawing_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("drawings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # polyline | cloud | arrow | rect | text
    points_json: Mapped[list[list[float]]] = mapped_column(JSON, nullable=False)  # [[x, y], ...] fractions
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    inspection_type: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    color: Mapped[str | None] = mapped_column(String(9), nullable=True)  # #RRGGBB or #RRGGBBAA
    created_by: Mapped[str] = mapped_column(String(120), nullable=False, default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
