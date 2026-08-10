"""Ground-truth labels for location-match evaluation (PR-G eval set)."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.sql import func

from .base import Base


class LocationMatchLabel(Base):
    __tablename__ = "location_match_labels"

    label_id = Column(String, primary_key=True)
    suite = Column(String, nullable=False, server_default="default", index=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_id = Column(
        Integer,
        ForeignKey("evidence_records.id", ondelete="SET NULL"),
        nullable=True,
    )
    inspection_run_id = Column(
        Integer,
        ForeignKey("inspection_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    master_drawing_id = Column(
        Integer,
        ForeignKey("drawings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_fixture_path = Column(String, nullable=True)
    master_bbox_json = Column(JSON, nullable=False)
    expected_method = Column(String, nullable=False)
    expected_match_status = Column(String, nullable=False)
    rotation_deg = Column(Integer, nullable=True)
    has_coordinate_signal = Column(Boolean, nullable=False, server_default="false")
    has_station_signal = Column(Boolean, nullable=False, server_default="false")
    has_reference_signal = Column(Boolean, nullable=False, server_default="false")
    evidence_kind = Column(String, nullable=False)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
