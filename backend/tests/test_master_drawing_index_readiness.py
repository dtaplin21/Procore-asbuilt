"""Tests for master drawing index readiness (Phase 6c)."""

from __future__ import annotations

from typing import cast

from models.drawing_region import DrawingRegion
from models.models import Drawing
from services.master_drawing_index_readiness import get_master_drawing_index_readiness
from services.storage import StorageService


def test_readiness_pending_when_index_not_ready(db_session, project) -> None:
    storage = StorageService(db_session)
    drawing = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="Master.pdf",
        storage_key="projects/1/drawings/master.pdf",
        content_type="application/pdf",
    )
    drawing_id = cast(int, drawing.id)

    readiness = get_master_drawing_index_readiness(db_session, drawing_id)

    assert readiness.index_status == "pending"
    assert readiness.region_count == 0
    assert readiness.is_ready_for_matching is False
    assert readiness.upload_response_status == "pending"


def test_readiness_ready_when_indexed_with_regions(db_session, project) -> None:
    storage = StorageService(db_session)
    drawing = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="Master.pdf",
        storage_key="projects/1/drawings/master-ready.pdf",
        content_type="application/pdf",
    )
    drawing_id = cast(int, drawing.id)
    row = db_session.get(Drawing, drawing_id)
    assert row is not None
    setattr(row, "index_status", "ready")
    storage.create_drawing_region(
        drawing_id,
        label="COLO",
        geometry={"type": "rect", "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
        location_tags=["COLO"],
    )
    db_session.commit()

    readiness = get_master_drawing_index_readiness(db_session, drawing_id)

    assert readiness.is_ready_for_matching is True
    assert readiness.upload_response_status == "ready"
    assert readiness.region_count == 1


def test_readiness_not_ready_when_index_ready_but_no_regions(db_session, project) -> None:
    storage = StorageService(db_session)
    drawing = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="Master.pdf",
        storage_key="projects/1/drawings/master-empty.pdf",
        content_type="application/pdf",
    )
    drawing_id = cast(int, drawing.id)
    row = db_session.get(Drawing, drawing_id)
    assert row is not None
    setattr(row, "index_status", "ready")
    db_session.commit()

    readiness = get_master_drawing_index_readiness(db_session, drawing_id)

    assert readiness.is_ready_for_matching is False
    assert readiness.upload_response_status == "pending"
