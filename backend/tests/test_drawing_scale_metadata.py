"""Tests for Drawing scale_json and page_meta_json (Phase 0b)."""

from __future__ import annotations

from typing import cast

from models.models import Drawing
from services.storage import StorageService


def test_drawing_scale_and_page_meta_json_persist(db_session, project) -> None:
    storage = StorageService(db_session)
    drawing = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="Master.pdf",
        storage_key="projects/2/drawings/master.pdf",
        content_type="application/pdf",
    )
    drawing_id = cast(int, drawing.id)

    scale_json = {
        "raw_text": "1\" = 10'",
        "paper_inches_per_real_foot": 0.1,
        "real_feet_per_paper_inch": 10.0,
        "horizontal": {"numerator": 1, "denominator": 10, "units": "in=ft"},
        "vertical": {"numerator": 1, "denominator": 10, "units": "in=ft"},
        "confidence": 0.85,
        "source_bbox": [0.75, 0.9, 0.95, 0.98],
        "page": 1,
    }
    page_meta_json = [
        {
            "page": 1,
            "width_pt": 3024,
            "height_pt": 2160,
            "width_px": 8400,
            "height_px": 6000,
            "rotation": 0,
        }
    ]

    row = db_session.get(Drawing, drawing_id)
    assert row is not None
    setattr(row, "scale_json", scale_json)
    setattr(row, "page_meta_json", page_meta_json)
    db_session.commit()
    db_session.refresh(row)

    loaded = db_session.get(Drawing, drawing_id)
    assert loaded is not None
    assert loaded.scale_json == scale_json
    assert loaded.page_meta_json == page_meta_json
    assert loaded.scale_json["real_feet_per_paper_inch"] == 10.0
    assert loaded.page_meta_json[0]["width_px"] == 8400
