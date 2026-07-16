"""Persisted document classification and field extraction results."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class DocumentExtraction(Base):
    __tablename__ = "document_extractions"

    id = Column(Integer, primary_key=True)
    file_id = Column(String, nullable=False, index=True)
    document_type = Column(String, nullable=False)
    classification_confidence = Column(Float, nullable=True)  # BACKEND ONLY
    universal_fields_json = Column(JSON, nullable=True)
    type_specific_fields_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    clues = relationship(
        "DocumentClue",
        back_populates="extraction",
        cascade="all, delete-orphan",
    )
