"""Overlays stay tied to the master index they were placed against."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy.orm import Session

from database import SessionLocal

from models.drawing_overlay import DrawingOverlay
from models.models import Drawing, JobQueue
from services.inspection_match_persistence import persist_inspection_match_overlay
from services.inspection_matching_jobs import (
    JOB_TYPE_INSPECTION_MATCH,
    enqueue_rematch_after_master_reindex,
)
from services.overlay_index_binding import (
    BUILT_FROM_INDEXED_AT_KEY,
    INDEX_STALE_KEY,
    overlay_response_for_index,
)
from tests.test_inspection_matching_jobs import _seed_run


@pytest.fixture
def db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_overlay_response_hides_geometry_from_an_older_index() -> None:
    created = datetime(2026, 10, 1, tzinfo=timezone.utc)
    reindexed = created + timedelta(days=10)
    overlay = SimpleNamespace(
        id=486,
        master_drawing_id=1722,
        inspection_run_id=692,
        region_id=None,
        diff_id=None,
        geometry={
            "page": 1,
            "type": "polyline",
            "points": [[0.16, 0.78], [0.25, 0.78]],
        },
        status="unknown",
        label="Inspection match",
        severity=None,
        confidence_label=None,
        inspection_date=None,
        tags_json=None,
        meta={"match_status": "needs_review"},
        created_at=created,
    )

    response = overlay_response_for_index(overlay, reindexed)

    assert response.geometry == {"page": 1, "type": "none"}
    assert response.meta is not None
    assert response.meta[INDEX_STALE_KEY] is True


def test_persist_stamps_overlay_with_current_index(db: Session) -> None:
    run, file_id = _seed_run(db)
    drawing_id = cast(int, run.master_drawing_id)
    indexed_at = datetime(2026, 10, 11, 20, 31, 14, tzinfo=timezone.utc)
    drawing = db.get(Drawing, drawing_id)
    assert drawing is not None
    drawing.indexed_at = indexed_at  # type: ignore[assignment]
    db.commit()

    overlay_id = persist_inspection_match_overlay(
        db,
        inspection_id=file_id,
        drawing_id=drawing_id,
        status="needs_review",
        bbox=(0.1, 0.2, 0.4, 0.5),
        inspection_run_id=cast(int, run.id),
    )
    assert overlay_id is not None

    overlay = db.get(DrawingOverlay, overlay_id)
    assert overlay is not None
    meta = cast(dict, overlay.meta)
    assert meta[BUILT_FROM_INDEXED_AT_KEY] == "2026-10-11T20:31:14+00:00"

    response = overlay_response_for_index(overlay, indexed_at)
    assert response.geometry["type"] == "rect"
    assert response.meta is None or INDEX_STALE_KEY not in response.meta


def test_reindex_enqueues_one_match_only_job_per_run(db: Session) -> None:
    run, file_id = _seed_run(db)
    drawing_id = cast(int, run.master_drawing_id)
    drawing = db.get(Drawing, drawing_id)
    assert drawing is not None
    drawing.index_status = "ready"  # type: ignore[assignment]
    drawing.indexed_at = datetime(2026, 10, 18, tzinfo=timezone.utc)  # type: ignore[assignment]
    db.commit()

    persist_inspection_match_overlay(
        db,
        inspection_id=file_id,
        drawing_id=drawing_id,
        status="needs_review",
        bbox=(0.1, 0.2, 0.4, 0.5),
        inspection_run_id=cast(int, run.id),
    )

    assert enqueue_rematch_after_master_reindex(db, drawing_id) == 1
    assert enqueue_rematch_after_master_reindex(db, drawing_id) == 0

    jobs = (
        db.query(JobQueue)
        .filter(
            JobQueue.job_type == JOB_TYPE_INSPECTION_MATCH,
            JobQueue.project_id == run.project_id,
        )
        .all()
    )
    assert len(jobs) == 1
    payload = cast(dict, jobs[0].input_data)
    assert payload["match_only"] is True
    assert payload["inspection_run_id"] == cast(int, run.id)
