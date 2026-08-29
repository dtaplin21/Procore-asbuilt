"""Tests for drawing_index job type (Phase 1a)."""

from __future__ import annotations

import asyncio
import io
import uuid
from typing import cast
from unittest.mock import patch

import fitz
from sqlalchemy.orm import Session

from models.drawing_region import DrawingRegion
from models.drawing_text_element import DrawingTextElement
from models.models import Drawing, JobQueue, Project
from services.drawing_index_jobs import (
    AUTO_INDEX_REGION_SOURCE,
    JOB_TYPE,
    clear_drawing_index_artifacts,
    enqueue_drawing_index_job,
    index_linked_attachment_drawing_sync,
    is_auto_index_region,
    run_drawing_index_job,
)
from services.drawing_render_jobs import DRAWING_RENDER_JOB_TYPE, process_drawing_render_job


def _minimal_pdf_bytes() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    page.insert_text((50, 100), "Test PDF")
    out = doc.tobytes()
    doc.close()
    return out


def test_upload_drawing_enqueues_index_job(
    client,
    db_session: Session,
    project: Project,
) -> None:
    """Upload → drawing_render job; render success chains drawing_index (Phase 8)."""
    project_id = cast(int, project.id)
    pdf = _minimal_pdf_bytes()
    files = {"file": ("master.pdf", io.BytesIO(pdf), "application/pdf")}

    response = client.post(
        f"/api/projects/{project_id}/drawings",
        files=files,
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert response.status_code == 200, response.text
    drawing_id = response.json()["id"]

    render_jobs = (
        db_session.query(JobQueue)
        .filter(
            JobQueue.job_type == DRAWING_RENDER_JOB_TYPE,
            JobQueue.project_id == project_id,
        )
        .all()
    )
    matching_render = [
        job
        for job in render_jobs
        if isinstance(job.input_data, dict)
        and int(job.input_data.get("drawing_id", -1)) == drawing_id
    ]
    assert len(matching_render) == 1

    with patch("services.drawing_render_jobs.run_render_drawing_job"):
        with patch(
            "services.drawing_render_jobs.maybe_enqueue_drawing_index_job"
        ) as mock_enqueue:
            asyncio.run(process_drawing_render_job(drawing_id))
            mock_enqueue.assert_called_once()
            assert mock_enqueue.call_args.kwargs["project_id"] == project_id
            assert mock_enqueue.call_args.kwargs["drawing_id"] == drawing_id


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
    assert result.text_elements >= 1
    assert cast(str, seeded_ready_pdf_drawing.index_status) == "ready"
    assert seeded_ready_pdf_drawing.index_error is None
    assert seeded_ready_pdf_drawing.indexed_at is not None
    assert cast(dict[str, object], seeded_ready_pdf_drawing.index_stats_json) == {
        "pages": result.pages,
        "text_elements": result.text_elements,
        "regions": 0,
        "survey_points": result.survey_points,
        "landmarks": result.landmarks,
        "scale_found": False,
    }
    page_meta = cast(list[object], seeded_ready_pdf_drawing.page_meta_json)
    assert len(page_meta) >= 1


def test_run_drawing_index_job_skips_digitization_when_disabled(
    db_session: Session,
    seeded_ready_pdf_drawing: Drawing,
) -> None:
    """SHEET_DIGITIZATION_ENABLED defaults false — index must not call digitize."""
    from services.drawing_index_jobs import maybe_digitize_drawing_after_index

    drawing_id = cast(int, seeded_ready_pdf_drawing.id)
    with patch("services.sheet_digitization.digitize_drawing_page") as mock_digitize:
        maybe_digitize_drawing_after_index(db_session, drawing_id)
        mock_digitize.assert_not_called()

    result = run_drawing_index_job(drawing_id, db_session)
    db_session.refresh(seeded_ready_pdf_drawing)
    assert cast(str, seeded_ready_pdf_drawing.index_status) == "ready"
    assert result.pages >= 1


def test_maybe_digitize_swallows_failures_when_enabled(
    db_session: Session,
    seeded_ready_pdf_drawing: Drawing,
    monkeypatch,
) -> None:
    from config import settings
    from services.drawing_index_jobs import maybe_digitize_drawing_after_index

    monkeypatch.setattr(settings, "sheet_digitization_enabled", True)
    drawing_id = cast(int, seeded_ready_pdf_drawing.id)

    def _boom(*args, **kwargs):
        raise RuntimeError("yolo weights missing simulation")

    with patch("services.sheet_digitization.digitize_drawing_page", side_effect=_boom):
        # Must not raise — index path relies on this being non-blocking.
        maybe_digitize_drawing_after_index(db_session, drawing_id)


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
    assert cast(str, regions[0].label) == "Manual COLO"
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

    rows = (
        db_session.query(DrawingTextElement)
        .filter(DrawingTextElement.master_drawing_id == drawing_id)
        .all()
    )
    assert len(rows) >= 1
    assert all(row.text != "OLD" for row in rows)


def test_index_linked_attachment_drawing_sync_indexes_linked_evidence(
    db_session: Session,
    seeded_ready_pdf_drawing: Drawing,
) -> None:
    linked = seeded_ready_pdf_drawing
    linked.source = "linked_evidence"  # type: ignore[assignment]
    linked.index_status = "pending"  # type: ignore[assignment]
    db_session.commit()

    drawing_id = cast(int, linked.id)
    result = index_linked_attachment_drawing_sync(db_session, drawing_id)

    assert result is not None
    assert result.text_elements >= 1
    db_session.refresh(linked)
    assert cast(str, linked.index_status) == "ready"
    assert cast(str, linked.processing_status) == "ready"


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
