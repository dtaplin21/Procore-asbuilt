"""Per-viewport regions and scales on a drawing page.

Feet conversion MUST use DrawingViewport.scale_json for geometry inside bbox.
``drawings.scale_json`` remains a legacy titleblock hint only — do not use it
for geometry that sits inside a known viewport.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class DrawingViewport(Base):
    __tablename__ = "drawing_viewports"
    __table_args__ = (
        UniqueConstraint(
            "drawing_id",
            "page",
            "viewport_id",
            name="uq_drawing_viewports_drawing_page_viewport",
        ),
    )

    id = Column(Integer, primary_key=True)
    drawing_id = Column(
        Integer,
        ForeignKey("drawings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page = Column(Integer, nullable=False, default=1)
    # Semantic id unique per drawing+page, e.g. "plan", "section_a"
    viewport_id = Column(String, nullable=False)
    kind = Column(String, nullable=False)  # plan | section | detail | elevation | profile | other
    bbox_json = Column(JSON, nullable=False)  # {x0,y0,x1,y1} fractional
    scale_json = Column(JSON, nullable=True)  # same shape as drawing_scale_parser output
    source = Column(String, nullable=False)  # manual | ocr | detected
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    drawing = relationship("Drawing", back_populates="viewports")
