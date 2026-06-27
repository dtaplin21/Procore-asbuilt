"""
The InspectionRun model — referenced throughout the merge plan and the
region-visibility spec (e.g. inspection_runs: run id, inspection_type,
optional procore_inspection_id).

Created by POST .../inspections/runs (client createInspectionRun) before
evidence upload; joined by region_inspection_summary for hover tooltips.

``procore_inspection_id`` is nullable: set only after Procore writeback sync.
Most runs will not have one yet.

Reconciled with the existing Postgres schema (94abb60704c6): integer PK/FK,
evidence_id, started_at/completed_at/error_message, status values
queued|processing|complete|failed — not the reference's string IDs or
pending-only status.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InspectionRun(Base):
    __tablename__ = "inspection_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('queued','processing','complete','failed')",
            name="ck_inspection_runs_status",
        ),
        Index("ix_inspection_runs_project_id", "project_id"),
        Index("ix_inspection_runs_master_drawing_id", "master_drawing_id"),
        Index("ix_inspection_runs_evidence_id", "evidence_id"),
        Index("ix_inspection_runs_status", "status"),
        Index("ix_inspection_runs_project_id_created_at", "project_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    master_drawing_id = Column(
        Integer,
        ForeignKey("drawings.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_id = Column(
        Integer,
        ForeignKey("evidence_records.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Selected at run creation (upload form) — may differ from tags extracted later.
    inspection_type = Column(String, nullable=True)
    status = Column(String, nullable=False, server_default="queued")

    # Set after successful Procore writeback; nullable until synced.
    procore_inspection_id = Column(String, nullable=True, index=True)

    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=_utcnow,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=_utcnow,
        default=_utcnow,
    )

    project = relationship("Project", back_populates="inspection_runs")
    master_drawing = relationship("Drawing", back_populates="inspection_runs")
    evidence = relationship("EvidenceRecord", back_populates="inspection_runs")
    results = relationship(
        "InspectionResult",
        back_populates="inspection_run",
        cascade="all, delete-orphan",
    )
    overlays = relationship(
        "DrawingOverlay",
        back_populates="inspection_run",
        passive_deletes=True,
    )
    unresolved_evidence = relationship(
        "UnresolvedEvidence",
        back_populates="inspection_run",
        cascade="all, delete-orphan",
    )
    inspection_reviews = relationship(
        "DrawingInspectionReview",
        back_populates="inspection_run",
        cascade="all, delete-orphan",
    )
