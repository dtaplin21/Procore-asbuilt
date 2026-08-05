"""Tests for DrawingTextElement model (Phase 0a master drawing auto-index)."""

from __future__ import annotations

from typing import cast

from models.drawing_text_element import DrawingTextElement
from models.models import Drawing
from services.storage import StorageService


def test_drawing_text_element_persists(db_session, project) -> None:
    storage = StorageService(db_session)
    drawing = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="Master.pdf",
        storage_key="projects/2/drawings/master.pdf",
        content_type="application/pdf",
    )
    master_drawing_id = cast(int, drawing.id)

    row = DrawingTextElement(
        master_drawing_id=master_drawing_id,
        page=1,
        text="SS",
        text_normalized="ss",
        bbox_json={"x": 0.1, "y": 0.2, "width": 0.01, "height": 0.005},
        ocr_confidence=0.92,
        legend_expansion="SANITARY SEWER",
        legend_codes_json=["SS", "SSMH"],
        source="tesseract",
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)

    loaded = (
        db_session.query(DrawingTextElement)
        .filter(DrawingTextElement.master_drawing_id == master_drawing_id)
        .one()
    )
    assert loaded.text == "SS"
    assert loaded.legend_expansion == "SANITARY SEWER"
    assert loaded.legend_codes_json == ["SS", "SSMH"]

    master = db_session.get(Drawing, master_drawing_id)
    assert master is not None
    assert len(master.text_elements) == 1
