"""
backend/models/base.py

Single shared SQLAlchemy declarative base for every model in this
pipeline (DrawingRegion, DrawingOverlay, UnresolvedEvidence,
InspectionRun, ...). Cross-file foreign keys (e.g.
DrawingOverlay.region_id -> DrawingRegion.id) only resolve correctly when
both models' tables are registered against the SAME metadata — each
model file calling declarative_base() independently creates separate,
unconnected registries, which breaks any FK between them at
mapper-configuration time.

All model files in backend/models/ should import Base from here rather
than calling declarative_base() themselves.
"""

from __future__ import annotations

from sqlalchemy.orm import declarative_base

Base = declarative_base()
