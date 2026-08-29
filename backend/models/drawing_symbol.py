"""Detected / manual symbols on a drawing page (sheet digitization S-3)."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class DrawingSymbol(Base):
    __tablename__ = "drawing_symbols"

    id = Column(Integer, primary_key=True)
    drawing_id = Column(
        Integer,
        ForeignKey("drawings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page = Column(Integer, nullable=False, default=1)
    symbol_class = Column(String, nullable=False)  # ssmh | ssco | north_arrow | ...
    bbox_json = Column(JSON, nullable=False)  # {x0,y0,x1,y1} fractional
    viewport_id = Column(String, nullable=True)  # semantic viewport id; null = unassigned
    confidence = Column(Float, nullable=False, server_default="1.0")
    detector = Column(String, nullable=False)  # yolo | manual | contour
    meta_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    drawing = relationship("Drawing", back_populates="symbols")
