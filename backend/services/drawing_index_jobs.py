"""
Master drawing auto-index job queue integration.

Enqueues index jobs after successful drawing render. OCR ingest and region
building run in :mod:`ai.pipelines.master_drawing_indexer` (Phase 2+).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, cast

from sqlalchemy.orm import Session

from ai.pipelines.master_drawing_indexer import IndexResult, index_master_drawing
from ai.pipelines.master_drawing_region_builder import AUTO_INDEX_REGION_SOURCE
from config import settings
from models.drawing_region import DrawingRegion
from models.drawing_landmark import DrawingLandmark
from models.drawing_survey_point import DrawingSurveyPoint
from models.drawing_text_element import DrawingTextElement
from models.models import Drawing, DrawingRendition, JobQueue, Project, User, UserCompany
from observability.workflow_logging import log_job_status_transition
from services.inspection_matching_jobs import (
    flush_deferred_inspection_matches_for_drawing,
    flush_inspection_matches_for_linked_auxiliary_drawing,
)
from services.storage import open_storage_path

logger = logging.getLogger(__name__)

JOB_TYPE = "drawing_index"
_LINKED_DRAWING_SOURCE = "linked_evidence"


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

    session.query(DrawingSurveyPoint).filter(
        DrawingSurveyPoint.drawing_id == drawing_id,
        DrawingSurveyPoint.source == "auto_index",
    ).delete(synchronize_session=False)

    session.query(DrawingLandmark).filter(
        DrawingLandmark.drawing_id == drawing_id,
        DrawingLandmark.source == "auto_index",
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


def ensure_linked_attachment_ready_for_index(session: Session, drawing: Drawing) -> bool:
    """Mark linked attachment drawings ready for OCR when the PDF is already on disk."""
    if cast(str, drawing.processing_status) == "ready":
        return True

    storage_key = cast(str | None, drawing.storage_key)
    if not storage_key:
        return False

    source_path = open_storage_path(storage_key)
    if not source_path.exists():
        return False

    drawing.processing_status = "ready"  # type: ignore[assignment]
    session.flush()
    return True


def index_linked_attachment_drawing_sync(
    session: Session,
    drawing_id: int,
) -> IndexResult | None:
    """Run full positioned OCR index synchronously for one linked attachment."""
    if not settings.drawing_index_enabled:
        return None

    drawing = session.get(Drawing, drawing_id)
    if drawing is None:
        return None
    if cast(str | None, drawing.source) != _LINKED_DRAWING_SOURCE:
        return None
    if cast(str, drawing.index_status) == "ready":
        return None

    if not ensure_linked_attachment_ready_for_index(session, drawing):
        logger.warning(
            "linked_attachment_sync_index_not_ready",
            extra={"drawing_id": drawing_id},
        )
        return None

    drawing.index_status = "processing"  # type: ignore[assignment]
    drawing.index_error = None  # type: ignore[assignment]
    session.flush()

    try:
        clear_drawing_index_artifacts(session, drawing_id)
        result = index_master_drawing(drawing_id, session)
        _apply_index_result(drawing, result)
        session.flush()
        maybe_digitize_drawing_after_index(session, drawing_id)
        flush_inspection_matches_for_linked_auxiliary_drawing(session, drawing_id)
        return result
    except Exception as exc:
        drawing.index_status = "failed"  # type: ignore[assignment]
        drawing.index_error = str(exc)  # type: ignore[assignment]
        session.flush()
        logger.exception(
            "linked_attachment_sync_index_failed",
            extra={"drawing_id": drawing_id},
        )
        return None


def index_linked_attachment_drawings_sync(
    session: Session,
    drawing_ids: list[int],
) -> list[int]:
    """OCR-index every linked attachment; return ids that reached index_status=ready."""
    indexed: list[int] = []
    for drawing_id in drawing_ids:
        result = index_linked_attachment_drawing_sync(session, drawing_id)
        if result is not None:
            indexed.append(drawing_id)
    return indexed


def _apply_index_result(drawing: Drawing, result: IndexResult) -> None:
    drawing.index_status = "ready"  # type: ignore[assignment]
    drawing.index_error = None  # type: ignore[assignment]
    drawing.indexed_at = datetime.now(timezone.utc)  # type: ignore[assignment]
    drawing.index_stats_json = result.to_stats_json()  # type: ignore[assignment]
    if result.scale_json is not None:
        drawing.scale_json = result.scale_json  # type: ignore[assignment]
    if result.page_meta_json is not None:
        drawing.page_meta_json = result.page_meta_json  # type: ignore[assignment]


def _rendition_png_for_page(session: Session, drawing_id: int, page: int) -> Path | None:
    """Return absolute Path to a ready page PNG, or None."""
    rendition = (
        session.query(DrawingRendition)
        .filter(
            DrawingRendition.drawing_id == int(drawing_id),
            DrawingRendition.page_number == int(page),
            DrawingRendition.render_status == "ready",
        )
        .one_or_none()
    )
    if rendition is None:
        return None
    key = cast(str | None, rendition.image_storage_key)
    if not key:
        return None
    path = open_storage_path(key)
    return path if path.exists() else None


def maybe_digitize_drawing_after_index(session: Session, drawing_id: int) -> None:
    """Optionally digitize pages after OCR index (non-blocking for the index job).

    Controlled by ``SHEET_DIGITIZATION_ENABLED`` (default false). Failures are
    logged and never raised to the caller — missing YOLO weights must not fail index.
    """
    if not settings.sheet_digitization_enabled:
        return

    from services.sheet_digitization import digitize_drawing_page

    try:
        renditions = (
            session.query(DrawingRendition)
            .filter(
                DrawingRendition.drawing_id == int(drawing_id),
                DrawingRendition.render_status == "ready",
            )
            .order_by(DrawingRendition.page_number.asc())
            .all()
        )
        pages = [cast(int, r.page_number) for r in renditions] or [1]

        for page in pages:
            png_path = _rendition_png_for_page(session, drawing_id, page)
            if png_path is None:
                logger.info(
                    "sheet_digitization_skipped_no_rendition",
                    extra={"drawing_id": drawing_id, "page": page},
                )
                continue
            graph = digitize_drawing_page(
                session,
                int(drawing_id),
                page=int(page),
                rendition_png=png_path,
                persist=True,
            )
            logger.info(
                "sheet_digitization_complete",
                extra={
                    "drawing_id": drawing_id,
                    "page": page,
                    "viewports": len(graph.viewports),
                    "labels": len(graph.labels),
                    "symbols": len(graph.symbols),
                    "lines": len(graph.lines),
                    "associations": len(graph.associations),
                    "viewport_warning": bool(graph.meta.get("viewport_warning")),
                },
            )
        session.commit()
    except Exception:
        logger.exception(
            "sheet_digitization_failed",
            extra={"drawing_id": drawing_id},
        )
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass


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
        maybe_digitize_drawing_after_index(session, drawing_id)
        flush_deferred_inspection_matches_for_drawing(session, drawing_id)
        flush_inspection_matches_for_linked_auxiliary_drawing(session, drawing_id)
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
