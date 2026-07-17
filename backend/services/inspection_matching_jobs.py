"""Inspection matching job.

Uses extracted clues to find candidate master drawing locations.
Internal confidence/score values never leave the backend.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Literal, Optional, cast

from sqlalchemy.orm import Session

from ai.pipelines.candidate_tile_selector import (
    CandidateTile,
    compute_tile_match_score,
    find_candidate_tiles_from_clues,
)
from models.drawing_overlay import DrawingOverlay
from models.document_clue import DocumentClue
from models.document_extraction import DocumentExtraction
from models.models import JobQueue, Project, User, UserCompany
from services.inspection_match_persistence import (
    MATCH_SCORE_THRESHOLD,
    InternalMatchCandidate,
    MatchStatus,
    match_status_from_internal_score,
    persist_inspection_match_overlay,
    record_internal_match_candidate,
    resolve_inspection_run_id,
)

logger = logging.getLogger(__name__)

JOB_TYPE_INSPECTION_MATCH = "inspection_match"


@dataclass(frozen=True)
class InspectionMatchRecord:
    match_status: MatchStatus
    bbox: tuple[float, float, float, float] | None = None


def load_inspection_match_status(
    session: Session,
    inspection_id: str,
) -> InspectionMatchRecord | None:
    """Load frontend-safe match status from the latest overlay for an inspection."""
    run_id = resolve_inspection_run_id(session, inspection_id)
    if run_id is None:
        return None

    overlay = (
        session.query(DrawingOverlay)
        .filter(DrawingOverlay.inspection_run_id == run_id)
        .order_by(DrawingOverlay.id.desc())
        .first()
    )
    if overlay is None:
        return InspectionMatchRecord(match_status="no_match")

    meta = overlay.meta if isinstance(overlay.meta, dict) else {}
    raw_status = meta.get("match_status", "needs_review")
    status: MatchStatus = (
        raw_status
        if raw_status in ("matched", "needs_review", "no_match")
        else "needs_review"
    )

    bbox: tuple[float, float, float, float] | None = None
    if status == "matched" and isinstance(overlay.geometry, dict):
        geometry = cast(dict[str, Any], overlay.geometry)
        if geometry.get("type") == "rect":
            try:
                bbox = (
                    float(geometry["x"]),
                    float(geometry["y"]),
                    float(geometry["width"]),
                    float(geometry["height"]),
                )
            except (KeyError, TypeError, ValueError):
                bbox = None

    return InspectionMatchRecord(match_status=status, bbox=bbox)


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
        raise ValueError("No users in database; cannot enqueue inspection match job")
    return cast(int, user.id)


def enqueue_inspection_match_job(
    db: Session,
    *,
    project_id: int,
    inspection_id: str,
    drawing_id: str | int,
    page: int,
    user_id: Optional[int] = None,
) -> JobQueue:
    if user_id is None:
        user_id = _resolve_user_id_for_project(db, project_id)

    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise ValueError(f"Project {project_id} not found")

    job = JobQueue(
        user_id=user_id,
        company_id=project.company_id,
        project_id=project_id,
        job_type=JOB_TYPE_INSPECTION_MATCH,
        status="pending",
        input_data={
            "inspection_id": str(inspection_id),
            "drawing_id": str(drawing_id),
            "page": int(page),
        },
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def maybe_enqueue_inspection_match_job(
    db: Session,
    *,
    project_id: int | None,
    inspection_id: str | None,
    master_drawing_id: int | str | None,
    page: int = 1,
    user_id: Optional[int] = None,
) -> JobQueue | None:
    """Enqueue clue-based matching when project, inspection, and master drawing are known."""
    if project_id is None or not inspection_id or master_drawing_id is None:
        return None

    safe_page = page if page >= 1 else 1

    try:
        return enqueue_inspection_match_job(
            db,
            project_id=project_id,
            inspection_id=str(inspection_id),
            drawing_id=master_drawing_id,
            page=safe_page,
            user_id=user_id,
        )
    except Exception:
        logger.exception(
            "inspection_match_enqueue_failed",
            extra={
                "project_id": project_id,
                "inspection_id": inspection_id,
                "master_drawing_id": master_drawing_id,
                "page": safe_page,
            },
        )
        return None


def run_inspection_match_job(payload: dict[str, Any], session: Session) -> MatchStatus:
    inspection_id = str(payload["inspection_id"])
    drawing_id = payload["drawing_id"]
    page = int(payload.get("page", 1))

    extraction = (
        session.query(DocumentExtraction)
        .filter_by(file_id=inspection_id)
        .order_by(DocumentExtraction.created_at.desc())
        .first()
    )

    if extraction is None:
        persist_inspection_match_overlay(
            session=session,
            inspection_id=inspection_id,
            drawing_id=drawing_id,
            status="needs_review",
            bbox=None,
            page=page,
        )
        return "needs_review"

    clues = (
        session.query(DocumentClue)
        .filter_by(document_extraction_id=extraction.id)
        .all()
    )

    candidates = find_candidate_tiles_from_clues(
        session=session,
        drawing_id=drawing_id,
        page=page,
        clues=clues,
        limit=20,
    )

    if not candidates:
        persist_inspection_match_overlay(
            session=session,
            inspection_id=inspection_id,
            drawing_id=drawing_id,
            status="needs_review",
            bbox=None,
            page=page,
        )
        return "needs_review"

    scored_candidates: list[tuple[float, CandidateTile]] = []
    for rank, tile in enumerate(candidates, start=1):
        internal_score = compute_tile_match_score(tile, clues)
        scored_candidates.append((internal_score, tile))
        record_internal_match_candidate(
            session,
            inspection_id=inspection_id,
            drawing_id=drawing_id,
            candidate=InternalMatchCandidate(
                score=internal_score,
                bbox=tile.bbox_normalized,
                page=tile.page,
                region_id=tile.region_id,
                source="clue_match",
                rank=rank,
            ),
        )
    session.commit()

    best_score, best = max(scored_candidates, key=lambda item: item[0])
    status = match_status_from_internal_score(best_score)
    persist_inspection_match_overlay(
        session,
        inspection_id=inspection_id,
        drawing_id=drawing_id,
        status=status,
        bbox=best.bbox_normalized if status == "matched" else None,
        page=best.page,
        region_id=best.region_id,
    )
    return status


async def process_inspection_match_job(payload: dict[str, Any]) -> MatchStatus:
    """Run inspection match job in a worker thread (sync SQLAlchemy session)."""

    def _run() -> MatchStatus:
        from database import SessionLocal

        db = SessionLocal()
        try:
            return run_inspection_match_job(payload, db)
        finally:
            db.close()

    return await asyncio.to_thread(_run)
