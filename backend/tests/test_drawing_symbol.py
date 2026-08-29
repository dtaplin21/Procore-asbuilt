"""Tests for DrawingSymbol persistence (sheet digitization S-3)."""

from __future__ import annotations

from typing import cast

from ai.pipelines.sheet_entity_graph import SheetSymbol
from models.drawing_symbol import DrawingSymbol
from services.sheet_digitization import load_drawing_symbols, upsert_drawing_symbols
from services.storage import StorageService


def test_drawing_symbol_insert_read_roundtrip(db_session, project) -> None:
    storage = StorageService(db_session)
    drawing = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="C4.20.pdf",
        storage_key="projects/2/drawings/c420_symbols.pdf",
        content_type="application/pdf",
    )
    drawing_id = cast(int, drawing.id)

    row = DrawingSymbol(
        drawing_id=drawing_id,
        page=1,
        symbol_class="ssmh",
        bbox_json={"x0": 0.25, "y0": 0.20, "x1": 0.28, "y1": 0.24},
        viewport_id="plan",
        confidence=1.0,
        detector="manual",
        meta_json={"note": "seed"},
    )
    db_session.add(row)
    db_session.commit()

    loaded = (
        db_session.query(DrawingSymbol)
        .filter_by(drawing_id=drawing_id, symbol_class="ssmh")
        .one()
    )
    assert loaded.viewport_id == "plan"
    assert loaded.bbox_json["x0"] == 0.25
    assert loaded.detector == "manual"
    assert loaded.meta_json == {"note": "seed"}


def test_upsert_drawing_symbols_replaces_by_detector(db_session, project) -> None:
    storage = StorageService(db_session)
    drawing = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="Symbols.pdf",
        storage_key="projects/2/drawings/symbols.pdf",
        content_type="application/pdf",
    )
    drawing_id = cast(int, drawing.id)

    first = [
        SheetSymbol(
            symbol_class="ssmh",
            bbox_fractional=(0.1, 0.1, 0.12, 0.12),
            viewport_id="plan",
            confidence=0.9,
            detector="yolo",
        )
    ]
    assert upsert_drawing_symbols(db_session, drawing_id, first, replace_detector="yolo") == 1
    db_session.commit()

    second = [
        SheetSymbol(
            symbol_class="ssco",
            bbox_fractional=(0.2, 0.2, 0.22, 0.22),
            viewport_id="plan",
            confidence=0.8,
            detector="yolo",
        ),
        SheetSymbol(
            symbol_class="north_arrow",
            bbox_fractional=(0.7, 0.05, 0.75, 0.12),
            viewport_id="plan",
            confidence=0.7,
            detector="yolo",
        ),
    ]
    assert upsert_drawing_symbols(db_session, drawing_id, second, replace_detector="yolo") == 2
    db_session.commit()

    yolo_rows = load_drawing_symbols(db_session, drawing_id, detector="yolo")
    assert len(yolo_rows) == 2
    assert {cast(str, r.symbol_class) for r in yolo_rows} == {"ssco", "north_arrow"}
