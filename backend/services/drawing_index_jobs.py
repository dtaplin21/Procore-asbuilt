"""
Master drawing auto-index job queue integration.

Enqueues index jobs after successful drawing render. OCR ingest and region
building run in :mod:`ai.pipelines.master_drawing_indexer` (Phase 2+).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional, cast

from sqlalchemy.orm import Session

from ai.pipelines.master_drawing_indexer import IndexResult, index_master_drawing
from config import settings
from models.drawing_region import DrawingRegion
from models.drawing_text_element import DrawingTextElement
from models.models import Drawing, JobQueue, Project, User, UserCompany
from observability.workflow_logging import log_job_status_transition

logger = logging.getLogger(__name__)

JOB_TYPE = "drawing_index"
AUTO_INDEX_REGION_SOURCE = "auto_index"


def region_geometry_source(geometry: object) -> str | None:
    if not isinstance(geometry, dict):
        return None
    meta = geometry.get("meta")
    if not isinstance(meta, dict):
        return None
    source = meta.get("source")
    return str(source) if source is not None else None


def is_auto_index_region(region: DrawingRegion) -> bool:
    return region_geometry_source(region.geometry) == AUTO_INDEX_REGION_SOURCE


def _resolve_user_id_for_project(db: Session, project_id: int) -> int:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise ValueError(f"Project {project_id} not found")

    uc = (
        db.query(UserCompany)
        .filter(UserCompany.company_id == project.company_id)
        .first()
    )
    if uc is not None:
        return cast(int, uc.user_id)

    user = db.query(User).order_by(User.id.asc()).first()
    if user is None:
        raise ValueError("No users in database; cannot enqueue drawing index job")
    return cast(int, user.id)


def clear_drawing_index_artifacts(session: Session, drawing_id: int) -> None:
    """Remove indexed text elements and auto-generated regions before re-index."""
    session.query(DrawingTextElement).filter(
        DrawingTextElement.master_drawing_id == drawing_id
    ).delete(synchronize_session=False)

    auto_regions = [
        region
        for region in session.query(DrawingRegion)
        .filter(DrawingRegion.master_drawing_id == drawing_id)
        .all()
        if is_auto_index_region(region)
    ]
    for region in auto_regions:
        session.delete(region)


def enqueue_drawing_index_job(
    db: Session,
    project_id: int,
    drawing_id: int,
    user_id: Optional[int] = None,
) -> JobQueue:
    """Enqueue a master drawing index job."""
    if not settings.drawing_index_enabled:
        raise ValueError("Drawing index is disabled (DRAWING_INDEX_ENABLED=false)")

    if user_id is None:
        user_id = _resolve_user_id_for_project(db, project_id)

    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise ValueError(f"Project {project_id} not found")

    drawing = (
        db.query(Drawing)
        .filter(Drawing.id == drawing_id, Drawing.project_id == project_id)
        .first()
    )
    if drawing is None:
        raise ValueError(
            f"Drawing {drawing_id} not found for project {project_id}; cannot enqueue index job"
        )

    previous_status = None
    job = JobQueue(
        user_id=user_id,
        company_id=project.company_id,
        project_id=project_id,
        job_type=JOB_TYPE,
        status="pending",
        input_data={"drawing_id": int(drawing_id)},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    log_job_status_transition(
        project_id=project_id,
        job_id=cast(int, job.id),
        status=cast(str | None, job.status),
        previous_status=previous_status,
    )
    return job


def maybe_enqueue_drawing_index_job(
    db: Session,
    project_id: int,
    drawing_id: int,
    user_id: Optional[int] = None,
) -> JobQueue | None:
    """Enqueue index job when enabled; swallow errors so render success is preserved."""
    if not settings.drawing_index_enabled:
        return None

    try:
        return enqueue_drawing_index_job(
            db,
            project_id=project_id,
            drawing_id=drawing_id,
            user_id=user_id,
        )
    except Exception:
        logger.exception(
            "drawing_index_enqueue_failed",
            extra={"project_id": project_id, "drawing_id": drawing_id},
        )
        return None


def _apply_index_result(drawing: Drawing, result: IndexResult) -> None:
    drawing.index_status = "ready"  # type: ignore[assignment]
    drawing.index_error = None  # type: ignore[assignment]
    drawing.indexed_at = datetime.now(timezone.utc)  # type: ignore[assignment]
    drawing.index_stats_json = result.to_stats_json()  # type: ignore[assignment]
    if result.scale_json is not None:
        drawing.scale_json = result.scale_json  # type: ignore[assignment]
    if result.page_meta_json is not None:
        drawing.page_meta_json = result.page_meta_json  # type: ignore[assignment]


def run_drawing_index_job(drawing_id: int, session: Session) -> IndexResult:
    """Index a master drawing: clear prior auto-index data, run pipeline, persist status."""
    drawing = session.get(Drawing, drawing_id)
    if drawing is None:
        raise ValueError(f"Drawing {drawing_id} not found")

    if not settings.drawing_index_enabled:
        logger.info(
            "drawing_index_skipped_disabled",
            extra={"drawing_id": drawing_id},
        )
        return IndexResult()

    if cast(str, drawing.processing_status) != "ready":
        raise ValueError(
            f"Drawing {drawing_id} is not ready for index "
            f"(processing_status={drawing.processing_status})"
        )

    drawing.index_status = "processing"  # type: ignore[assignment]
    drawing.index_error = None  # type: ignore[assignment]
    session.commit()

    try:
        clear_drawing_index_artifacts(session, drawing_id)
        session.commit()

        result = index_master_drawing(drawing_id, session)
        _apply_index_result(drawing, result)
        session.commit()
        return result
    except Exception as exc:
        drawing.index_status = "failed"  # type: ignore[assignment]
        drawing.index_error = str(exc)  # type: ignore[assignment]
        session.commit()
        raise


async def process_drawing_index_job(drawing_id: int) -> None:
    """Async wrapper for run_drawing_index_job (CPU-bound work in a thread)."""
    from database import SessionLocal

    def _run() -> None:
        db = SessionLocal()
        try:
            run_drawing_index_job(drawing_id, db)
        finally:
            db.close()

    await asyncio.to_thread(_run)
