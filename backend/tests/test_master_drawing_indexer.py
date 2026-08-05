"""Tests for master drawing OCR ingest (Phase 2)."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from ai.pipelines.document_text_extraction import (
    BoundingBox,
    ExtractedDocument,
    PositionedWord,
    SourceFormat,
)
from ai.pipelines.master_drawing_indexer import (
    IndexResult,
    build_page_meta_json,
    extract_drawing_document,
    index_master_drawing,
    normalize_token_text,
    persist_text_elements,
    word_bbox_json,
)
from models.drawing_text_element import DrawingTextElement
from models.models import Drawing


def _word(text: str, page_index: int = 0) -> PositionedWord:
    return PositionedWord(
        text=text,
        bbox=BoundingBox(
            x=61.2,
            y=158.4,
            width=40.0,
            height=12.0,
            page_width=612.0,
            page_height=792.0,
        ),
        page_index=page_index,
        ocr_confidence=0.95,
    )


def test_normalize_token_text() -> None:
    assert normalize_token_text("  SS-3  ") == "ss-3"


def test_word_bbox_json_uses_fractional_corners() -> None:
    assert word_bbox_json(_word("SS")) == pytest.approx(
        {"x0": 0.1, "y0": 0.2, "x1": 0.1 + 40 / 612, "y1": 0.2 + 12 / 792}
    )


def test_extract_drawing_document_respects_max_pages(tmp_path: Path) -> None:
    fake_doc = ExtractedDocument(
        source_format=SourceFormat.NATIVE_PDF,
        page_count=3,
        words=[
            _word("A", page_index=0),
            _word("B", page_index=1),
            _word("C", page_index=2),
        ],
    )
    pdf_path = tmp_path / "master.pdf"
    pdf_path.write_bytes(b"%PDF")

    with patch(
        "ai.pipelines.master_drawing_indexer.extract_document",
        return_value=fake_doc,
    ):
        with patch(
            "ai.pipelines.master_drawing_indexer._index_max_pages",
            return_value=2,
        ):
            extracted = extract_drawing_document(pdf_path)

    assert extracted.page_count == 2
    assert [word.text for word in extracted.words] == ["A", "B"]


def test_persist_text_elements(db_session: Session, seeded_ready_pdf_drawing: Drawing) -> None:
    drawing_id = cast(int, seeded_ready_pdf_drawing.id)
    words = [_word("SS"), _word("COLO")]

    count = persist_text_elements(
        db_session,
        drawing_id,
        words,
        SourceFormat.NATIVE_PDF,
    )
    db_session.commit()

    rows = (
        db_session.query(DrawingTextElement)
        .filter(DrawingTextElement.master_drawing_id == drawing_id)
        .order_by(DrawingTextElement.text.asc())
        .all()
    )

    assert count == 2
    assert [row.text for row in rows] == ["COLO", "SS"]
    assert rows[0].text_normalized == "colo"
    assert rows[0].source == "native_pdf"
    assert rows[0].bbox_json["x0"] == pytest.approx(0.1)


def test_master_drawing_indexer_persists_elements(
    db_session: Session,
    seeded_ready_pdf_drawing: Drawing,
) -> None:
    drawing_id = cast(int, seeded_ready_pdf_drawing.id)

    result = index_master_drawing(drawing_id, db_session)
    db_session.commit()

    rows = (
        db_session.query(DrawingTextElement)
        .filter(DrawingTextElement.master_drawing_id == drawing_id)
        .all()
    )

    assert isinstance(result, IndexResult)
    assert result.pages >= 1
    assert result.text_elements == len(rows)
    assert result.text_elements >= 1
    assert any("test" in row.text_normalized for row in rows)


def test_build_page_meta_json_uses_pdf_and_renditions(
    db_session: Session,
    seeded_ready_pdf_drawing: Drawing,
) -> None:
    drawing_id = cast(int, seeded_ready_pdf_drawing.id)
    storage_key = cast(str, seeded_ready_pdf_drawing.storage_key)
    from services.storage import open_storage_path

    page_meta = build_page_meta_json(
        db_session,
        drawing_id,
        open_storage_path(storage_key),
        page_count=cast(int, seeded_ready_pdf_drawing.page_count or 1),
    )

    assert len(page_meta) >= 1
    assert page_meta[0]["page"] == 1
    assert page_meta[0]["width_pt"] == pytest.approx(200.0)
    assert page_meta[0]["height_pt"] == pytest.approx(200.0)
    rendition = seeded_ready_pdf_drawing.renditions[0]
    assert page_meta[0]["width_px"] == rendition.width_px
    assert page_meta[0]["height_px"] == rendition.height_px
