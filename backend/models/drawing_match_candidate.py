"""Internal backend storage for inspection match candidates.

Scores in this table are backend-only and must never be returned to the frontend.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.sql import func

from .base import Base


class DrawingMatchCandidate(Base):
    __tablename__ = "drawing_match_candidates"

    id = Column(Integer, primary_key=True)
    inspection_id = Column(String, nullable=False, index=True)
    inspection_run_id = Column(
        Integer,
        ForeignKey("inspection_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    master_drawing_id = Column(
        Integer,
        ForeignKey("drawings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page = Column(Integer, nullable=False, server_default="1")
    region_id = Column(
        Integer,
        ForeignKey("drawing_regions.id", ondelete="SET NULL"),
        nullable=True,
    )
    score = Column(Float, nullable=False)  # BACKEND ONLY
    bbox_json = Column(JSON, nullable=True)
    source = Column(String, nullable=False, server_default="clue_match")
    rank = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
