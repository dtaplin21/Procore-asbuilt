"""Inspection matching job.

Uses the unified location-match orchestrator to resolve evidence on master drawings.
Internal confidence/score values never leave the backend.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional, cast

from sqlalchemy.orm import Session

from ai.pipelines.drawing_location_resolver import ResolutionMethod
from ai.pipelines.location_match_orchestrator import (
    match_status_from_result,
    resolve_evidence_location,
)
from models.drawing_overlay import DrawingOverlay
from models.inspection_run import InspectionRun
from models.models import Drawing, EvidenceRecord, JobQueue, Project, User, UserCompany
from services.inspection_match_persistence import (
    InternalMatchCandidate,
    MatchStatus,
    persist_inspection_match_overlay,
    record_internal_match_candidate,
    resolve_inspection_run_id,
)
from services.master_drawing_index_readiness import get_master_drawing_index_readiness

logger = logging.getLogger(__name__)

JOB_TYPE_INSPECTION_MATCH = "inspection_match"
DEFERRED_MATCH_META_KEY = "deferredInspectionMatch"


@dataclass(frozen=True)
class InspectionMatchRecord:
    match_status: MatchStatus
    bbox: tuple[float, float, float, float] | None = None


def load_inspection_match_status(
    session: Session,
    inspection_id: str,
    *,
    inspection_run_id: int | None = None,
) -> InspectionMatchRecord | None:
    """Load frontend-safe match status from the latest overlay for an inspection."""
    run_id = resolve_inspection_run_id(
        session,
        inspection_id,
        inspection_run_id=inspection_run_id,
    )
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
        if raw_status in ("matched", "needs_review", "no_match", "index_pending")
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


def _parse_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def enqueue_inspection_match_job(
    db: Session,
    *,
    project_id: int,
    inspection_id: str,
    drawing_id: str | int,
    page: int,
    user_id: Optional[int] = None,
    inspection_run_id: Optional[int] = None,
) -> JobQueue:
    if user_id is None:
        user_id = _resolve_user_id_for_project(db, project_id)

    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise ValueError(f"Project {project_id} not found")

    input_data: dict[str, Any] = {
        "inspection_id": str(inspection_id),
        "drawing_id": str(drawing_id),
        "page": int(page),
        "project_id": int(project_id),
    }
    if inspection_run_id is not None:
        input_data["inspection_run_id"] = int(inspection_run_id)

    job = JobQueue(
        user_id=user_id,
        company_id=project.company_id,
        project_id=project_id,
        job_type=JOB_TYPE_INSPECTION_MATCH,
        status="pending",
        input_data=input_data,
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
    inspection_run_id: Optional[int] = None,
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
            inspection_run_id=inspection_run_id,
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


def _defer_inspection_match(
    session: Session,
    *,
    evidence_id: int,
    project_id: int,
    inspection_id: str,
    master_drawing_id: int | str,
    page: int,
    inspection_run_id: int | None,
) -> None:
    evidence = session.query(EvidenceRecord).filter(EvidenceRecord.id == evidence_id).first()
    if evidence is not None:
        meta_raw = getattr(evidence, "meta", None)
        meta = dict(meta_raw) if isinstance(meta_raw, dict) else {}
        meta[DEFERRED_MATCH_META_KEY] = {
            "project_id": project_id,
            "master_drawing_id": int(master_drawing_id),
            "page": page,
            "inspection_run_id": inspection_run_id,
        }
        evidence.meta = meta  # type: ignore[assignment]
        session.flush()

    persist_inspection_match_overlay(
        session,
        inspection_id=inspection_id,
        drawing_id=master_drawing_id,
        status="index_pending",
        bbox=None,
        page=page,
        inspection_run_id=inspection_run_id,
    )


def maybe_enqueue_inspection_match_after_extraction(
    db: Session,
    *,
    evidence_id: int,
    project_id: int,
    inspection_id: str,
    master_drawing_id: int | str,
    page: int = 1,
    user_id: Optional[int] = None,
    inspection_run_id: Optional[int] = None,
) -> JobQueue | None:
    """Enqueue clue matching when the master index is ready; otherwise defer."""
    readiness = get_master_drawing_index_readiness(db, int(master_drawing_id))
    if not readiness.is_ready_for_matching:
        _defer_inspection_match(
            db,
            evidence_id=evidence_id,
            project_id=project_id,
            inspection_id=inspection_id,
            master_drawing_id=master_drawing_id,
            page=page,
            inspection_run_id=inspection_run_id,
        )
        logger.info(
            "inspection_match_deferred_until_index_ready",
            extra={
                "evidence_id": evidence_id,
                "master_drawing_id": master_drawing_id,
                "index_status": readiness.index_status,
                "region_count": readiness.region_count,
            },
        )
        return None

    return maybe_enqueue_inspection_match_job(
        db,
        project_id=project_id,
        inspection_id=inspection_id,
        master_drawing_id=master_drawing_id,
        page=page,
        user_id=user_id,
        inspection_run_id=inspection_run_id,
    )


def flush_deferred_inspection_matches_for_drawing(
    session: Session,
    drawing_id: int,
) -> int:
    """Enqueue match jobs that were deferred while this master drawing indexed."""
    runs = (
        session.query(InspectionRun)
        .filter(InspectionRun.master_drawing_id == drawing_id)
        .order_by(InspectionRun.id.asc())
        .all()
    )
    enqueued = 0
    for run in runs:
        evidence_id = getattr(run, "evidence_id", None)
        if evidence_id is None:
            continue

        evidence = session.query(EvidenceRecord).filter(EvidenceRecord.id == evidence_id).first()
        if evidence is None:
            continue

        meta_raw = getattr(evidence, "meta", None)
        if not isinstance(meta_raw, dict):
            continue

        deferred = meta_raw.get(DEFERRED_MATCH_META_KEY)
        if not isinstance(deferred, dict):
            continue

        project_id = _parse_optional_int(deferred.get("project_id"))
        if project_id is None:
            project_id = _parse_optional_int(getattr(run, "project_id", None))
        if project_id is None:
            continue

        page = _parse_optional_int(deferred.get("page")) or 1
        inspection_run_id = _parse_optional_int(deferred.get("inspection_run_id"))
        if inspection_run_id is None:
            inspection_run_id = cast(int, run.id)

        job = maybe_enqueue_inspection_match_job(
            session,
            project_id=project_id,
            inspection_id=str(evidence_id),
            master_drawing_id=drawing_id,
            page=page,
            inspection_run_id=inspection_run_id,
        )
        if job is None:
            continue

        meta = dict(meta_raw)
        meta.pop(DEFERRED_MATCH_META_KEY, None)
        evidence.meta = meta  # type: ignore[assignment]
        enqueued += 1

    if enqueued:
        session.commit()
    return enqueued


def run_inspection_match_job(payload: dict[str, Any], session: Session) -> MatchStatus:
    inspection_id = str(payload["inspection_id"])
    drawing_id = payload["drawing_id"]
    page = int(payload.get("page", 1))
    run_id_hint = _parse_optional_int(payload.get("inspection_run_id"))
    evidence_id = _parse_optional_int(inspection_id)
    master_drawing_id = _parse_optional_int(drawing_id)

    def _persist(**kwargs: Any) -> None:
        persist_inspection_match_overlay(
            session=session,
            inspection_id=inspection_id,
            drawing_id=drawing_id,
            inspection_run_id=run_id_hint,
            **kwargs,
        )

    if evidence_id is None or master_drawing_id is None:
        _persist(status="needs_review", bbox=None, page=page)
        return "needs_review"

    result = resolve_evidence_location(
        session,
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
        page=page,
    )
    status = match_status_from_result(result)

    if result.method != ResolutionMethod.UNRESOLVED:
        record_internal_match_candidate(
            session,
            inspection_id=inspection_id,
            drawing_id=drawing_id,
            candidate=InternalMatchCandidate(
                score=result.confidence,
                bbox=result.bbox_fractional,
                page=result.page,
                region_id=result.region_id,
                source=result.method.value,
                rank=1,
            ),
            inspection_run_id=run_id_hint,
        )
        session.commit()

    if result.method == ResolutionMethod.UNRESOLVED:
        logger.info(
            "inspection_match_unresolved",
            extra={
                "inspection_id": inspection_id,
                "drawing_id": drawing_id,
                "page": page,
                "evidence_id": evidence_id,
                "notes": result.notes,
            },
        )

    _persist(
        status=status,
        bbox=result.bbox_fractional if status == "matched" else None,
        page=result.page,
        region_id=result.region_id,
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
