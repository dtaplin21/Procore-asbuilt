"""Tests for digitize_drawing_page orchestrator (PR-D D-1)."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import cv2  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]

from ai.pipelines.sheet_entity_graph import SheetLine, SheetSymbol
from models.drawing_text_element import DrawingTextElement
from models.drawing_viewport import DrawingViewport
from models.models import Drawing
from services.sheet_digitization import (
    SHEET_ENTITY_GRAPH_KEY,
    digitize_drawing_page,
)
from services.storage import StorageService


def _write_blank_png(path: Path) -> None:
    image = np.full((200, 300), 255, dtype=np.uint8)
    cv2.imwrite(str(path), image)


def test_digitize_drawing_page_builds_graph_and_persists(
    db_session,
    project,
    tmp_path: Path,
    monkeypatch,
) -> None:
    storage = StorageService(db_session)
    drawing = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="Digitize.pdf",
        storage_key="projects/2/drawings/digitize.pdf",
        content_type="application/pdf",
    )
    drawing_id = cast(int, drawing.id)

    db_session.add(
        DrawingViewport(
            drawing_id=drawing_id,
            page=1,
            viewport_id="plan",
            kind="plan",
            bbox_json={"x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 0.8},
            scale_json={
                "raw_text": '1"=10\'',
                "real_feet_per_paper_inch": 10.0,
                "confidence": 0.9,
            },
            source="manual",
        )
    )
    db_session.add(
        DrawingTextElement(
            master_drawing_id=drawing_id,
            page=1,
            text="SSMH",
            text_normalized="ssmh",
            bbox_json={"x0": 0.40, "y0": 0.30, "x1": 0.46, "y1": 0.34},
            ocr_confidence=0.95,
            source="native_pdf",
        )
    )
    db_session.commit()

    png = tmp_path / "page.png"
    _write_blank_png(png)

    fake_line = SheetLine(
        points=((0.1, 0.1), (0.5, 0.5)),
        viewport_id="plan",
        confidence=0.8,
    )
    fake_symbol = SheetSymbol(
        symbol_class="ssmh",
        bbox_fractional=(0.41, 0.36, 0.45, 0.40),
        viewport_id=None,
        confidence=0.9,
        detector="yolo",
    )

    monkeypatch.setattr(
        "ai.pipelines.line_extractor.extract_line_polylines",
        lambda *args, **kwargs: [fake_line],
    )
    monkeypatch.setattr(
        "services.sheet_digitization.detect_symbols",
        lambda *args, **kwargs: [fake_symbol],
    )
    monkeypatch.setattr(
        "services.sheet_digitization.resolve_symbol_detector_weights_path",
        lambda *args, **kwargs: Path("/fake/weights.pt"),
    )

    graph = digitize_drawing_page(db_session, drawing_id, page=1, rendition_png=png)
    db_session.commit()

    assert graph.drawing_id == drawing_id
    assert graph.meta.get("viewport_warning") is False
    assert len(graph.viewports) == 1
    assert len(graph.labels) == 1
    assert graph.labels[0].text == "SSMH"
    assert graph.labels[0].viewport_id == "plan"
    assert len(graph.lines) == 1
    assert len(graph.symbols) == 1
    assert graph.symbols[0].viewport_id == "plan"
    assert len(graph.associations) == 1
    assert graph.associations[0]["label_text"] == "SSMH"

    row = db_session.get(Drawing, drawing_id)
    assert row is not None
    stats = cast(dict, row.index_stats_json)
    assert SHEET_ENTITY_GRAPH_KEY in stats
    assert "1" in stats[SHEET_ENTITY_GRAPH_KEY]
    assert stats[SHEET_ENTITY_GRAPH_KEY]["1"]["labels"][0]["text"] == "SSMH"


def test_digitize_drawing_page_sets_viewport_warning_when_empty(
    db_session,
    project,
    tmp_path: Path,
    monkeypatch,
) -> None:
    storage = StorageService(db_session)
    drawing = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="NoVP.pdf",
        storage_key="projects/2/drawings/novp.pdf",
        content_type="application/pdf",
    )
    drawing_id = cast(int, drawing.id)
    db_session.commit()

    png = tmp_path / "page.png"
    _write_blank_png(png)
    monkeypatch.setattr(
        "ai.pipelines.line_extractor.extract_line_polylines",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "services.sheet_digitization.detect_symbols",
        lambda *args, **kwargs: [],
    )

    graph = digitize_drawing_page(
        db_session,
        drawing_id,
        page=1,
        rendition_png=png,
        persist=False,
    )
    assert graph.meta["viewport_warning"] is True
    assert graph.viewports == ()
    assert graph.symbols == ()
