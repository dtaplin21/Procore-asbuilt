"""Tests for auto viewport seeding after OCR index."""

from __future__ import annotations

from typing import cast
from unittest.mock import patch

from models.drawing_text_element import DrawingTextElement
from models.drawing_viewport import DrawingViewport
from models.models import Drawing
from services.viewport_seeding import (
    has_manual_viewports,
    maybe_seed_viewports_after_index,
    seed_viewports_for_page,
)


def _add_plan_profile_tokens(db_session, drawing_id: int) -> None:
    db_session.add_all(
        [
            DrawingTextElement(
                master_drawing_id=drawing_id,
                page=1,
                text="PLAN",
                text_normalized="plan",
                bbox_json={"x0": 0.10, "y0": 0.08, "x1": 0.18, "y1": 0.12},
                ocr_confidence=0.9,
                source="tesseract",
            ),
            DrawingTextElement(
                master_drawing_id=drawing_id,
                page=1,
                text='1"=10\'',
                text_normalized='1"=10\'',
                bbox_json={"x0": 0.20, "y0": 0.08, "x1": 0.28, "y1": 0.11},
                ocr_confidence=0.9,
                source="tesseract",
            ),
            DrawingTextElement(
                master_drawing_id=drawing_id,
                page=1,
                text="PROFILE",
                text_normalized="profile",
                bbox_json={"x0": 0.10, "y0": 0.55, "x1": 0.20, "y1": 0.60},
                ocr_confidence=0.9,
                source="tesseract",
            ),
            DrawingTextElement(
                master_drawing_id=drawing_id,
                page=1,
                text='1"=1\' VERTICAL',
                text_normalized='1"=1\' vertical',
                bbox_json={"x0": 0.20, "y0": 0.55, "x1": 0.35, "y1": 0.58},
                ocr_confidence=0.9,
                source="tesseract",
            ),
        ]
    )
    db_session.commit()


def test_seed_viewports_from_ocr_after_index(
    db_session,
    seeded_ready_pdf_drawing: Drawing,
) -> None:
    drawing_id = cast(int, seeded_ready_pdf_drawing.id)
    _add_plan_profile_tokens(db_session, drawing_id)

    result = seed_viewports_for_page(db_session, drawing_id, page=1)
    db_session.commit()

    assert result.written >= 2
    assert result.source == "ocr"
    rows = (
        db_session.query(DrawingViewport)
        .filter(DrawingViewport.drawing_id == drawing_id)
        .all()
    )
    kinds = {cast(str, row.kind) for row in rows}
    assert "plan" in kinds
    assert "profile" in kinds or "section" in kinds


def test_seed_skips_when_manual_viewports_exist(
    db_session,
    seeded_ready_pdf_drawing: Drawing,
) -> None:
    drawing_id = cast(int, seeded_ready_pdf_drawing.id)
    db_session.add(
        DrawingViewport(
            drawing_id=drawing_id,
            page=1,
            viewport_id="plan",
            kind="plan",
            bbox_json={"x0": 0.1, "y0": 0.1, "x1": 0.5, "y1": 0.5},
            scale_json=None,
            source="manual",
        )
    )
    db_session.commit()
    _add_plan_profile_tokens(db_session, drawing_id)

    result = seed_viewports_for_page(db_session, drawing_id, page=1)

    assert result.source == "skipped_manual"
    assert result.written == 0
    assert has_manual_viewports(db_session, drawing_id)


def test_layout_fallback_for_linked_evidence_without_kind_hits(
    db_session,
    seeded_ready_pdf_drawing: Drawing,
) -> None:
    drawing = seeded_ready_pdf_drawing
    drawing.source = "linked_evidence"  # type: ignore[assignment]
    drawing.scale_json = {  # type: ignore[assignment]
        "raw_text": '1"=10\'',
        "real_feet_per_paper_inch": 10.0,
        "confidence": 0.8,
        "page": 1,
    }
    db_session.commit()
    drawing_id = cast(int, drawing.id)

    db_session.add(
        DrawingTextElement(
            master_drawing_id=drawing_id,
            page=1,
            text="SCALES: 1 IN = 10 FT",
            text_normalized="scales: 1 in = 10 ft",
            bbox_json={"x0": 0.1, "y0": 0.96, "x1": 0.4, "y1": 0.99},
            ocr_confidence=0.9,
            source="tesseract",
        )
    )
    db_session.commit()

    result = seed_viewports_for_page(db_session, drawing_id, page=1)
    db_session.commit()

    assert result.source == "layout_fallback"
    assert result.written == 2
    rows = (
        db_session.query(DrawingViewport)
        .filter(DrawingViewport.drawing_id == drawing_id)
        .order_by(DrawingViewport.viewport_id.asc())
        .all()
    )
    assert len(rows) == 2
    assert cast(str, rows[0].source) == "layout_fallback"


def test_layout_fallback_skipped_on_page_2_multi_page_linked(
    db_session,
    seeded_ready_pdf_drawing: Drawing,
) -> None:
    """78-page UMR-style attachments must not layout-fallback every page."""
    drawing = seeded_ready_pdf_drawing
    drawing.source = "linked_evidence"  # type: ignore[assignment]
    drawing.page_count = 2  # type: ignore[assignment]
    drawing.scale_json = {  # type: ignore[assignment]
        "raw_text": '1"=10\'',
        "real_feet_per_paper_inch": 10.0,
        "confidence": 0.8,
        "page": 1,
    }
    db_session.commit()
    drawing_id = cast(int, drawing.id)

    db_session.add(
        DrawingTextElement(
            master_drawing_id=drawing_id,
            page=2,
            text="DETAIL A - MANHOLE RING",
            text_normalized="detail a - manhole ring",
            bbox_json={"x0": 0.1, "y0": 0.96, "x1": 0.4, "y1": 0.99},
            ocr_confidence=0.9,
            source="tesseract",
        )
    )
    db_session.commit()

    with patch(
        "services.viewport_seeding.propose_viewports_from_ocr",
        return_value=(),
    ):
        result = seed_viewports_for_page(db_session, drawing_id, page=2)

    assert result.source == "none"
    assert result.written == 0
    assert (
        db_session.query(DrawingViewport)
        .filter(DrawingViewport.drawing_id == drawing_id, DrawingViewport.page == 2)
        .count()
        == 0
    )


def test_viewports_survive_session_rollback_after_seed(
    db_session,
    seeded_ready_pdf_drawing: Drawing,
) -> None:
    """Per-page commits must persist viewports when digitization rolls back."""
    drawing = seeded_ready_pdf_drawing
    drawing.source = "linked_evidence"  # type: ignore[assignment]
    drawing.scale_json = {  # type: ignore[assignment]
        "raw_text": '1"=10\'',
        "real_feet_per_paper_inch": 10.0,
        "confidence": 0.8,
        "page": 1,
    }
    db_session.commit()
    drawing_id = cast(int, drawing.id)

    db_session.add(
        DrawingTextElement(
            master_drawing_id=drawing_id,
            page=1,
            text="SCALES: 1 IN = 10 FT",
            text_normalized="scales: 1 in = 10 ft",
            bbox_json={"x0": 0.1, "y0": 0.96, "x1": 0.4, "y1": 0.99},
            ocr_confidence=0.9,
            source="tesseract",
        )
    )
    db_session.commit()

    maybe_seed_viewports_after_index(db_session, drawing_id)
    db_session.rollback()

    rows = (
        db_session.query(DrawingViewport)
        .filter(DrawingViewport.drawing_id == drawing_id)
        .all()
    )
    assert len(rows) == 2


def test_run_drawing_index_job_calls_viewport_seed(
    db_session,
    seeded_ready_pdf_drawing: Drawing,
) -> None:
    from services.drawing_index_jobs import run_drawing_index_job

    drawing_id = cast(int, seeded_ready_pdf_drawing.id)
    with patch("services.drawing_index_jobs.maybe_seed_viewports_after_index") as mock_seed:
        run_drawing_index_job(drawing_id, db_session)
        mock_seed.assert_called_once_with(db_session, drawing_id)
