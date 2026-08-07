"""Survey coordinate points indexed on drawings for coordinate matching."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class DrawingSurveyPoint(Base):
    __tablename__ = "drawing_survey_points"

    id = Column(Integer, primary_key=True)
    drawing_id = Column(
        Integer,
        ForeignKey("drawings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page = Column(Integer, nullable=False, default=1)
    northing = Column(Float, nullable=False)
    easting = Column(Float, nullable=False)
    station = Column(String, nullable=True)
    structure_label = Column(String, nullable=True)
    label_bbox_json = Column(JSON, nullable=False)
    northing_bbox_json = Column(JSON, nullable=True)
    easting_bbox_json = Column(JSON, nullable=True)
    ocr_confidence = Column(Float, nullable=False, server_default="1.0")
    source = Column(String, nullable=False)  # auto_index | evidence_extract | manual
    meta_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    drawing = relationship("Drawing", back_populates="survey_points")
