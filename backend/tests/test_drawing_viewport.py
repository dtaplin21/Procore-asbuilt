"""Tests for DrawingViewport persistence (sheet digitization V-2)."""

from __future__ import annotations

from typing import cast

from models.drawing_viewport import DrawingViewport
from services.storage import StorageService


def test_drawing_viewport_persists_with_unique_viewport_id(db_session, project) -> None:
    storage = StorageService(db_session)
    drawing = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="C4.20.pdf",
        storage_key="projects/2/drawings/c420.pdf",
        content_type="application/pdf",
    )
    drawing_id = cast(int, drawing.id)

    scale_json = {
        "raw_text": '1"=20\'',
        "real_feet_per_paper_inch": 20.0,
        "confidence": 0.9,
    }
    vp = DrawingViewport(
        drawing_id=drawing_id,
        page=1,
        viewport_id="plan",
        kind="plan",
        bbox_json={"x0": 0.05, "y0": 0.1, "x1": 0.6, "y1": 0.85},
        scale_json=scale_json,
        source="manual",
        notes="main plan view",
    )
    db_session.add(vp)
    db_session.commit()

    loaded = (
        db_session.query(DrawingViewport)
        .filter_by(drawing_id=drawing_id, page=1, viewport_id="plan")
        .one()
    )
    assert loaded.kind == "plan"
    assert loaded.bbox_json["x0"] == 0.05
    assert loaded.scale_json == scale_json
    assert loaded.source == "manual"
    assert loaded.notes == "main plan view"
