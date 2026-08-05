"""Tests for master drawing legend tagger (Phase 4)."""

from __future__ import annotations

from typing import cast

from models.drawing_text_element import DrawingTextElement
from models.models import Drawing
from scripts.seed_legend_reference import seed
from services.master_drawing_legend_tagger import (
    enrich_text_element,
    enrich_text_elements_with_legend,
    is_single_token,
    legend_tags_for_text_element,
)
from services.storage import StorageService


def test_is_single_token() -> None:
    assert is_single_token("SS") is True
    assert is_single_token("SANITARY SEWER") is False


def test_enrich_single_token_ss(db_session, project) -> None:
    seed(db_session, project_id=None)
    project_id = cast(int, project.id)

    row = DrawingTextElement(
        master_drawing_id=1,
        page=1,
        text="SS",
        text_normalized="ss",
        bbox_json={"x0": 0.1, "y0": 0.1, "x1": 0.12, "y1": 0.12},
        ocr_confidence=0.9,
        source="native_pdf",
    )

    assert enrich_text_element(db_session, row, project_id=project_id) is True
    assert row.legend_expansion == "SANITARY SEWER"
    assert row.legend_codes_json is not None
    assert "SS" in row.legend_codes_json
    assert "SSMH" in row.legend_codes_json


def test_enrich_phrase_sanitary_sewer(db_session, project) -> None:
    seed(db_session, project_id=None)
    project_id = cast(int, project.id)

    row = DrawingTextElement(
        master_drawing_id=1,
        page=1,
        text="SANITARY SEWER",
        text_normalized="sanitary sewer",
        bbox_json={"x0": 0.1, "y0": 0.1, "x1": 0.2, "y1": 0.12},
        ocr_confidence=0.9,
        source="native_pdf",
    )

    assert enrich_text_element(db_session, row, project_id=project_id) is True
    assert row.legend_expansion is None
    assert row.legend_codes_json is not None
    assert "SS" in row.legend_codes_json


def test_enrich_unknown_token_leaves_null(db_session, project) -> None:
    seed(db_session, project_id=None)
    project_id = cast(int, project.id)

    row = DrawingTextElement(
        master_drawing_id=1,
        page=1,
        text="XYZZY",
        text_normalized="xyzzy",
        bbox_json={"x0": 0.1, "y0": 0.1, "x1": 0.12, "y1": 0.12},
        ocr_confidence=0.9,
        source="native_pdf",
    )

    assert enrich_text_element(db_session, row, project_id=project_id) is False
    assert row.legend_expansion is None
    assert row.legend_codes_json is None


def test_legend_tags_for_text_element(db_session, project) -> None:
    seed(db_session, project_id=None)
    project_id = cast(int, project.id)

    row = DrawingTextElement(
        master_drawing_id=1,
        page=1,
        text="SS",
        text_normalized="ss",
        bbox_json={"x0": 0.1, "y0": 0.1, "x1": 0.12, "y1": 0.12},
        ocr_confidence=0.9,
        source="native_pdf",
    )
    enrich_text_element(db_session, row, project_id=project_id)

    tags = legend_tags_for_text_element(row)
    assert "SS" in tags
    assert "SANITARY SEWER" in tags
    assert "SSMH" in tags


def test_enrich_text_elements_with_legend(db_session, project) -> None:
    seed(db_session, project_id=None)
    storage = StorageService(db_session)
    drawing = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="Master.pdf",
        storage_key="projects/2/drawings/master.pdf",
        content_type="application/pdf",
    )
    drawing_id = cast(int, drawing.id)

    db_session.add_all(
        [
            DrawingTextElement(
                master_drawing_id=drawing_id,
                page=1,
                text="SS",
                text_normalized="ss",
                bbox_json={"x0": 0.1, "y0": 0.1, "x1": 0.12, "y1": 0.12},
                ocr_confidence=0.9,
                source="native_pdf",
            ),
            DrawingTextElement(
                master_drawing_id=drawing_id,
                page=1,
                text="SANITARY SEWER",
                text_normalized="sanitary sewer",
                bbox_json={"x0": 0.2, "y0": 0.1, "x1": 0.3, "y1": 0.12},
                ocr_confidence=0.9,
                source="native_pdf",
            ),
        ]
    )
    db_session.commit()

    enriched = enrich_text_elements_with_legend(
        db_session,
        drawing_id,
        cast(int, project.id),
    )
    db_session.commit()

    rows = (
        db_session.query(DrawingTextElement)
        .filter(DrawingTextElement.master_drawing_id == drawing_id)
        .order_by(DrawingTextElement.text.asc())
        .all()
    )

    assert enriched == 2
    assert rows[0].legend_expansion is None
    assert rows[0].legend_codes_json is not None
    assert "SS" in rows[0].legend_codes_json
    assert rows[1].legend_expansion == "SANITARY SEWER"
    assert rows[1].legend_codes_json is not None

    master = db_session.get(Drawing, drawing_id)
    assert master is not None
