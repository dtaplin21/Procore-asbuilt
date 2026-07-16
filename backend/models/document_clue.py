"""Searchable clues derived from document extraction."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class DocumentClue(Base):
    __tablename__ = "document_clues"

    id = Column(Integer, primary_key=True)
    document_extraction_id = Column(
        Integer,
        ForeignKey("document_extractions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    clue_type = Column(String, nullable=False)
    clue_value = Column(String, nullable=False, index=True)
    source = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)  # BACKEND ONLY
    location_relevant = Column(Boolean, nullable=False, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    extraction = relationship("DocumentExtraction", back_populates="clues")
