"""
Persistence models for the output of the inspection-mapping pipeline:

  - DrawingOverlay: a resolved finding, pinned to a location on a master
    drawing. This is what client/src/hooks/use-inspection-runs.ts's
    useDrawingOverlays() reads, and what DrawingViewer renders (per the
    drawing-workspace refactor plan, PR2).
  - UnresolvedEvidence: evidence that could not be placed automatically —
    surfaced to a human reviewer rather than silently dropped.

Each DrawingOverlay carries TWO distinct timestamps, intentionally not
collapsed into one column:
  - inspection_date: the date the inspection was PERFORMED, as stated in
    the source document (extracted by date_extractor.py). Nullable — not
    every document states one.
  - created_at (uploaded_at in refactor docs): when this record was created
    in our system. Always set. This is what lets two submissions be told
    apart even if they resolve to the same location/label (e.g. a
    re-inspection of the same spot later).

``region_id`` (migration b7e2a4f91c36, PR1 of the region-visibility spec)
links a resolved overlay back to the specific drawing_regions row it
matched, via drawing_location_resolver.py's MasterRegion.region_id.
Nullable, ON DELETE SET NULL: deleting the region a historical overlay
once pointed at must not delete the inspection record itself.

Reconciled with the existing Postgres schema: integer PKs/FKs,
``master_drawing_id``, ``geometry`` JSON (not separate bbox columns),
``tags_json`` as JSONB-compatible JSON, and ``created_at`` as the upload
timestamp column name.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base

# Register drawing_regions before region_id FK is declared.
from .drawing_region import DrawingRegion  # noqa: F401


class DrawingOverlay(Base):
    """Overlay on a master drawing from the inspection-mapping pipeline."""

    __tablename__ = "drawing_overlays"
    __table_args__ = (
        CheckConstraint(
            "status in ('pass','fail','unknown')",
            name="ck_drawing_overlays_status",
        ),
        CheckConstraint(
            "inspection_run_id IS NOT NULL",
            name="ck_drawing_overlays_inspection_run_required",
        ),
        Index("ix_drawing_overlays_master_drawing_id", "master_drawing_id"),
        Index("ix_drawing_overlays_inspection_run_id", "inspection_run_id"),
        Index("ix_drawing_overlays_region_id", "region_id"),
        Index("ix_drawing_overlays_status", "status"),
        Index("ix_drawing_overlays_master_drawing_id_created_at", "master_drawing_id", "created_at"),
        Index("ix_drawing_overlays_inspection_date", "inspection_date"),
    )

    id = Column(Integer, primary_key=True, index=True)

    master_drawing_id = Column(
        Integer,
        ForeignKey("drawings.id", ondelete="CASCADE"),
        nullable=False,
    )
    inspection_run_id = Column(
        Integer,
        ForeignKey("inspection_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    region_id = Column(
        Integer,
        ForeignKey("drawing_regions.id", ondelete="SET NULL"),
        nullable=True,
    )

    geometry = Column(JSON, nullable=False)
    status = Column(String, nullable=False, server_default="unknown")  # pass | fail | unknown

    label = Column(String(length=255), nullable=True)
    severity = Column(String(length=32), nullable=True)  # high | medium | info
    confidence_label = Column(String(length=64), nullable=True)
    inspection_date = Column(Date, nullable=True)
    tags_json = Column(JSON, nullable=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    master_drawing = relationship("Drawing", back_populates="overlays")
    inspection_run = relationship("InspectionRun", back_populates="overlays")
    region = relationship("DrawingRegion", back_populates="overlays")
    inspection_reviews = relationship(
        "DrawingInspectionReview",
        back_populates="overlay",
        passive_deletes=True,
    )

    @property
    def uploaded_at(self) -> datetime:
        """When this overlay row was created (upload timestamp)."""
        return self.created_at


class UnresolvedEvidence(Base):
    """Evidence map_document_to_overlays() could not place on the master drawing."""

    __tablename__ = "unresolved_evidence"

    id = Column(Integer, primary_key=True, index=True)
    evidence_id = Column(
        Integer,
        ForeignKey("evidence_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    inspection_run_id = Column(
        Integer,
        ForeignKey("inspection_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    master_drawing_id = Column(
        Integer,
        ForeignKey("drawings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reason = Column(Text, nullable=False)
    extracted_terms_json = Column(JSON, nullable=False)
    resolved_by_human = Column(Boolean, nullable=False, server_default=text("false"))
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    evidence = relationship("EvidenceRecord", back_populates="unresolved_placements")
    inspection_run = relationship("InspectionRun", back_populates="unresolved_evidence")
    master_drawing = relationship("Drawing", back_populates="unresolved_evidence")

    @property
    def uploaded_at(self) -> datetime:
        return self.created_at
