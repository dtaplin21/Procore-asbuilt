"""
The DrawingRegion model for inspectable zones on a master drawing.

Extended with the columns this pipeline needs:
  - inspection_type_tags / location_tags — used by region_index_loader.py /
    drawing_location_resolver.py for evidence matching
  - geometry — normalized 0–1 rect or polygon (canonical storage; rect is the
    common case for PR2 CRUD and the admin draw tool)
  - polygon_points — optional additive polygon detail (list of [x, y] in the
    same normalized 0–1 space as geometry). None for simple rectangular
    regions. When set alongside a rect geometry, geometry remains the fallback
    hit-box / bbox for matching.
  - created_at / updated_at — audit timestamps for PATCH (PR2)

Reconciled with the existing Postgres schema (migration 61eebd8aec0e): integer
PK/FK, master_drawing_id, label, page — not the reference's separate pixel
x/y/width/height columns.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship

from .base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DrawingRegion(Base):
    """User-defined region on a master drawing (geometry + lookup tags)."""

    __tablename__ = "drawing_regions"

    id = Column(Integer, primary_key=True, index=True)
    master_drawing_id = Column(
        Integer,
        ForeignKey("drawings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label = Column(String(length=255), nullable=False)
    page = Column(Integer, nullable=False, default=1)

    # Normalized 0–1 rect or polygon — required hit-box / primary geometry.
    geometry = Column(JSON, nullable=False)

    # Optional polygon detail (normalized [x, y] points). None for rects.
    polygon_points = Column(JSON, nullable=True)

    inspection_type_tags = Column(
        ARRAY(String),
        nullable=True,
        server_default=text("'{}'::text[]"),
    )
    location_tags = Column(
        ARRAY(String),
        nullable=True,
        server_default=text("'{}'::text[]"),
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    master_drawing = relationship("Drawing", back_populates="regions")
    inspection_reviews = relationship("DrawingInspectionReview", back_populates="region")
    overlays = relationship(
        "DrawingOverlay",
        back_populates="region",
        passive_deletes=True,
    )
