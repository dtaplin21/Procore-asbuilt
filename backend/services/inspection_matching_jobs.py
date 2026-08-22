"""Inspection matching job.

Uses the Inspection Location Agent to resolve evidence on master drawings.
Internal confidence/score values never leave the backend.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Optional, cast

from sqlalchemy.orm import Session

from ai.agents.inspection_location_agent import InspectionLocationAgent
from models.drawing_overlay import DrawingOverlay
from models.inspection_run import InspectionRun
from models.models import (
    Drawing,
    EvidenceDrawingLink,
    EvidenceRecord,
    JobQueue,
    Project,
    User,
    UserCompany,
)
from services.inspection_match_persistence import (
    AgentMatchResult,
    MatchStatus,
    persist_inspection_match_overlay,
    resolve_inspection_run_id,
)
from services.master_drawing_index_readiness import get_master_drawing_index_readiness
from observability.location_match_logging import (
    log_inspection_match_persisted,
    log_inspection_match_result,
    log_inspection_match_started,
    log_inspection_upload_match_summary,
)

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
        log_inspection_upload_match_summary(
            evidence_id=evidence_id,
            project_id=project_id,
            master_drawing_id=int(master_drawing_id),
            inspection_run_id=inspection_run_id or 0,
            master_index_ready=False,
            master_index_status=readiness.upload_response_status,
            match_deferred=True,
            index_status=readiness.index_status,
            region_count=readiness.region_count,
        )
        return None

    job = maybe_enqueue_inspection_match_job(
        db,
        project_id=project_id,
        inspection_id=inspection_id,
        master_drawing_id=master_drawing_id,
        page=page,
        user_id=user_id,
        inspection_run_id=inspection_run_id,
    )
    if job is not None and inspection_run_id is not None:
        log_inspection_upload_match_summary(
            evidence_id=evidence_id,
            project_id=project_id,
            master_drawing_id=int(master_drawing_id),
            inspection_run_id=inspection_run_id,
            master_index_ready=True,
            master_index_status=readiness.upload_response_status,
            match_job_id=int(cast(int, job.id)),
            match_deferred=False,
            index_status=readiness.index_status,
            region_count=readiness.region_count,
        )
    return job


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


def flush_inspection_matches_for_linked_auxiliary_drawing(
    session: Session,
    auxiliary_drawing_id: int,
) -> int:
    """Re-enqueue inspection matches after an auxiliary install sheet finishes indexing."""
    drawing = session.get(Drawing, auxiliary_drawing_id)
    if drawing is None or cast(str, drawing.index_status) != "ready":
        return 0

    project_id = cast(int, drawing.project_id)
    project = session.get(Project, project_id)
    master_drawing_id = getattr(project, "master_drawing_id", None) if project else None
    if master_drawing_id is not None and int(master_drawing_id) == auxiliary_drawing_id:
        return 0

    links = (
        session.query(EvidenceDrawingLink)
        .filter(EvidenceDrawingLink.drawing_id == auxiliary_drawing_id)
        .all()
    )
    if not links:
        return 0

    enqueued = 0
    seen_runs: set[int] = set()

    for link in links:
        evidence_id = cast(int, link.evidence_id)
        runs = (
            session.query(InspectionRun)
            .filter(
                InspectionRun.project_id == project_id,
                InspectionRun.evidence_id == evidence_id,
            )
            .order_by(InspectionRun.id.desc())
            .all()
        )
        for run in runs:
            run_id = cast(int, run.id)
            if run_id in seen_runs:
                continue
            seen_runs.add(run_id)

            master_id = cast(int, run.master_drawing_id)
            readiness = get_master_drawing_index_readiness(session, master_id)
            if not readiness.is_ready_for_matching:
                continue

            job = maybe_enqueue_inspection_match_job(
                session,
                project_id=project_id,
                inspection_id=str(evidence_id),
                master_drawing_id=master_id,
                page=1,
                inspection_run_id=run_id,
            )
            if job is not None:
                enqueued += 1

    if enqueued:
        session.commit()
    return enqueued


def _bbox_from_agent_result(
    result: AgentMatchResult,
) -> tuple[float, float, float, float] | None:
    scope = result.scope
    if scope is not None:
        if (
            scope.type == "rect"
            and scope.x is not None
            and scope.y is not None
            and scope.width is not None
            and scope.height is not None
        ):
            return (
                scope.x,
                scope.y,
                scope.x + scope.width,
                scope.y + scope.height,
            )
        if scope.type == "polyline" and scope.points:
            xs = [point[0] for point in scope.points]
            ys = [point[1] for point in scope.points]
            return (min(xs), min(ys), max(xs), max(ys))

    return None


def _agent_result_for_logging(result: AgentMatchResult) -> SimpleNamespace:
    return SimpleNamespace(
        method=SimpleNamespace(value="inspection_location_agent"),
        confidence=float(result.fused_score or 0.0),
        bbox_fractional=_bbox_from_agent_result(result),
        page=result.page,
        region_id=result.region_id,
        notes=result.rationale,
    )


def _latest_overlay_id(
    session: Session,
    *,
    inspection_id: str,
    inspection_run_id: int | None,
) -> int | None:
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
        return None
    return cast(int, overlay.id)


def run_inspection_match_job(payload: dict[str, Any], session: Session) -> MatchStatus:
    inspection_id = str(payload["inspection_id"])
    drawing_id = payload["drawing_id"]
    page = int(payload.get("page", 1))
    run_id_hint = _parse_optional_int(payload.get("inspection_run_id"))
    project_id = _parse_optional_int(payload.get("project_id"))
    job_id = _parse_optional_int(payload.get("job_id"))
    evidence_id = _parse_optional_int(inspection_id)
    master_drawing_id = _parse_optional_int(drawing_id)

    def _persist(**kwargs: Any) -> int | None:
        return persist_inspection_match_overlay(
            session=session,
            inspection_id=inspection_id,
            drawing_id=drawing_id,
            inspection_run_id=run_id_hint,
            **kwargs,
        )

    if evidence_id is None or master_drawing_id is None:
        overlay_id = _persist(status="needs_review", bbox=None, page=page)
        log_inspection_match_persisted(
            evidence_id=evidence_id or 0,
            master_drawing_id=master_drawing_id or 0,
            match_status="needs_review",
            overlay_id=overlay_id,
            bbox=None,
            page=page,
            inspection_run_id=run_id_hint,
        )
        return "needs_review"

    log_inspection_match_started(
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
        page=page,
        inspection_run_id=run_id_hint,
        project_id=project_id,
        job_id=job_id,
    )

    agent = InspectionLocationAgent()
    result = agent.run(
        session,
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
        page=page,
        inspection_run_id=run_id_hint,
    )
    status = result.status

    log_inspection_match_result(
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
        result=_agent_result_for_logging(result),
        match_status=status,
        inspection_run_id=run_id_hint,
    )

    overlay_id = _latest_overlay_id(
        session,
        inspection_id=inspection_id,
        inspection_run_id=run_id_hint,
    )
    log_bbox = _bbox_from_agent_result(result)
    log_inspection_match_persisted(
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
        match_status=status,
        overlay_id=overlay_id,
        bbox=log_bbox if status in ("matched", "needs_review") else None,
        page=result.page,
        inspection_run_id=run_id_hint,
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
