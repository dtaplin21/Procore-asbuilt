"""Shape landmarks indexed on drawings for contour matching."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class DrawingLandmark(Base):
    __tablename__ = "drawing_landmarks"

    id = Column(Integer, primary_key=True)
    drawing_id = Column(
        Integer,
        ForeignKey("drawings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page = Column(Integer, nullable=False, default=1)
    landmark_type = Column(String, nullable=False)  # tank | manhole | building | other
    bbox_json = Column(JSON, nullable=False)
    hu_moments_json = Column(JSON, nullable=False)
    ocr_confidence = Column(Float, nullable=False, server_default="1.0")
    source = Column(String, nullable=False)  # auto_index | manual
    meta_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    drawing = relationship("Drawing", back_populates="landmarks")
