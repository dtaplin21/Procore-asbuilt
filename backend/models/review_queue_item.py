"""Backend-only review queue for low-confidence classification or failed extraction."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, text
from sqlalchemy.sql import func

from .base import Base


class ReviewQueueItem(Base):
    __tablename__ = "review_queue_items"

    id = Column(Integer, primary_key=True)
    file_id = Column(String, nullable=False, index=True)
    reason = Column(String, nullable=False)
    document_type_guess = Column(String, nullable=True)
    classification_confidence = Column(Float, nullable=True)  # BACKEND ONLY
    resolved = Column(Boolean, nullable=False, server_default=text("false"), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
