"""Tests for drawing_index job type (Phase 1a)."""

from __future__ import annotations

import asyncio
from typing import cast
from unittest.mock import patch

from sqlalchemy.orm import Session

from models.drawing_region import DrawingRegion
from models.drawing_text_element import DrawingTextElement
from models.models import Drawing
from services.drawing_index_jobs import (
    AUTO_INDEX_REGION_SOURCE,
    JOB_TYPE,
    clear_drawing_index_artifacts,
    enqueue_drawing_index_job,
    is_auto_index_region,
    run_drawing_index_job,
)
from services.drawing_render_jobs import process_drawing_render_job


def test_enqueue_drawing_index_job(db_session: Session, seeded_ready_pdf_drawing: Drawing) -> None:
    project_id = cast(int, seeded_ready_pdf_drawing.project_id)
    drawing_id = cast(int, seeded_ready_pdf_drawing.id)

    job = enqueue_drawing_index_job(db_session, project_id, drawing_id)

    assert cast(str, job.job_type) == JOB_TYPE
    assert cast(str, job.status) == "pending"
    assert cast(dict, job.input_data)["drawing_id"] == drawing_id


def test_run_drawing_index_job_sets_ready_status(
    db_session: Session,
    seeded_ready_pdf_drawing: Drawing,
) -> None:
    drawing_id = cast(int, seeded_ready_pdf_drawing.id)

    result = run_drawing_index_job(drawing_id, db_session)

    db_session.refresh(seeded_ready_pdf_drawing)
    assert result.pages >= 1
    assert seeded_ready_pdf_drawing.index_status == "ready"
    assert seeded_ready_pdf_drawing.index_error is None
    assert seeded_ready_pdf_drawing.indexed_at is not None
    assert seeded_ready_pdf_drawing.index_stats_json == {
        "pages": result.pages,
        "text_elements": 0,
        "regions": 0,
        "scale_found": False,
    }


def test_clear_drawing_index_artifacts_keeps_manual_regions(
    db_session: Session,
    seeded_ready_pdf_drawing: Drawing,
) -> None:
    drawing_id = cast(int, seeded_ready_pdf_drawing.id)

    manual = DrawingRegion(
        master_drawing_id=drawing_id,
        label="Manual COLO",
        page=1,
        geometry={"type": "rect", "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
        location_tags=["COLO"],
    )
    auto = DrawingRegion(
        master_drawing_id=drawing_id,
        label="Auto SS cluster",
        page=1,
        geometry={
            "type": "rect",
            "x": 0.3,
            "y": 0.3,
            "width": 0.1,
            "height": 0.1,
            "meta": {"source": AUTO_INDEX_REGION_SOURCE},
        },
        location_tags=["SS"],
    )
    db_session.add_all([manual, auto])
    db_session.add(
        DrawingTextElement(
            master_drawing_id=drawing_id,
            page=1,
            text="SS",
            text_normalized="ss",
            bbox_json={"x0": 0.1, "y0": 0.1, "x1": 0.2, "y1": 0.2},
            ocr_confidence=0.9,
            source="tesseract",
        )
    )
    db_session.commit()

    clear_drawing_index_artifacts(db_session, drawing_id)
    db_session.commit()

    regions = (
        db_session.query(DrawingRegion)
        .filter(DrawingRegion.master_drawing_id == drawing_id)
        .all()
    )
    text_count = (
        db_session.query(DrawingTextElement)
        .filter(DrawingTextElement.master_drawing_id == drawing_id)
        .count()
    )

    assert len(regions) == 1
    assert regions[0].label == "Manual COLO"
    assert not is_auto_index_region(regions[0])
    assert text_count == 0


def test_run_drawing_index_job_is_idempotent(
    db_session: Session,
    seeded_ready_pdf_drawing: Drawing,
) -> None:
    drawing_id = cast(int, seeded_ready_pdf_drawing.id)

    db_session.add(
        DrawingTextElement(
            master_drawing_id=drawing_id,
            page=1,
            text="OLD",
            text_normalized="old",
            bbox_json={"x0": 0.0, "y0": 0.0, "x1": 0.1, "y1": 0.1},
            ocr_confidence=0.5,
            source="tesseract",
        )
    )
    db_session.commit()

    run_drawing_index_job(drawing_id, db_session)

    text_count = (
        db_session.query(DrawingTextElement)
        .filter(DrawingTextElement.master_drawing_id == drawing_id)
        .count()
    )
    assert text_count == 0


def test_process_drawing_render_job_chains_index_job(
    sample_pdf_drawing: Drawing,
) -> None:
    drawing_id = cast(int, sample_pdf_drawing.id)
    project_id = cast(int, sample_pdf_drawing.project_id)

    with patch("services.drawing_render_jobs.run_render_drawing_job"):
        with patch(
            "services.drawing_render_jobs.maybe_enqueue_drawing_index_job"
        ) as mock_enqueue:
            asyncio.run(process_drawing_render_job(drawing_id))
            mock_enqueue.assert_called_once()
            assert mock_enqueue.call_args.kwargs["project_id"] == project_id
            assert mock_enqueue.call_args.kwargs["drawing_id"] == drawing_id
