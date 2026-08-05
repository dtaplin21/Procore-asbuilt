"""OCR / PDF text-layer tokens indexed on a master drawing for clue matching.

Each row is one searchable text token with a normalized bounding box on a page.
Legend enrichment fields are populated during master drawing index (Phase 4).
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class DrawingTextElement(Base):
    __tablename__ = "drawing_text_elements"

    id = Column(Integer, primary_key=True)
    master_drawing_id = Column(
        Integer,
        ForeignKey("drawings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page = Column(Integer, nullable=False, default=1)
    text = Column(String, nullable=False)
    text_normalized = Column(String, nullable=False, index=True)
    bbox_json = Column(JSON, nullable=False)
    ocr_confidence = Column(Float, nullable=False, server_default="1.0")
    legend_expansion = Column(Text, nullable=True)
    legend_codes_json = Column(JSON, nullable=True)
    source = Column(String, nullable=False)  # native_pdf | tesseract | openai_vision
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    master_drawing = relationship("Drawing", back_populates="text_elements")
