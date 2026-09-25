"""Persisted legend exemplar grounding hits on a master drawing page."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class DrawingLegendGroundingHit(Base):
    __tablename__ = "drawing_legend_grounding_hits"

    id = Column(Integer, primary_key=True)
    master_drawing_id = Column(
        Integer,
        ForeignKey("drawings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page = Column(Integer, nullable=False, default=1)
    grounding_run_id = Column(String, nullable=False, index=True)
    legend_row_id = Column(Integer, nullable=True)
    legend_label_text = Column(Text, nullable=False)
    match_method = Column(String, nullable=False)  # document_ai_text | template_match
    provider = Column(String, nullable=False, server_default="document_ai")
    bbox_json = Column(JSON, nullable=False)  # {x0,y0,x1,y1} fractional page
    confidence = Column(Float, nullable=False)
    meta_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    master_drawing = relationship("Drawing", back_populates="legend_grounding_hits")
