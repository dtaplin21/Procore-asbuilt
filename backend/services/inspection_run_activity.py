"""Inspection run activity labels and stale-run recovery."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

from sqlalchemy.orm import Session

from models.inspection_run import InspectionRun
from models.models import JobQueue
from services.inspection_matching_jobs import JOB_TYPE_INSPECTION_MATCH
from services.storage import StorageService

RunActivity = str  # indexing | matching | investigating | stuck

_STALE_RUN_MESSAGE = (
    "Background job stopped before finishing (check worker logs and disk space)."
)


def _run_id_from_job_input(input_data: dict[str, Any] | None) -> int | None:
    if not isinstance(input_data, dict):
        return None
    raw = input_data.get("inspection_run_id")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def find_active_job_for_run(session: Session, inspection_run_id: int) -> JobQueue | None:
    """Latest pending/processing inspection_match job for this run, if any."""
    candidates = (
        session.query(JobQueue)
        .filter(
            JobQueue.job_type == JOB_TYPE_INSPECTION_MATCH,
            JobQueue.status.in_(("pending", "processing")),
        )
        .order_by(JobQueue.id.desc())
        .limit(100)
        .all()
    )
    for job in candidates:
        if _run_id_from_job_input(cast(dict[str, Any] | None, job.input_data)) == inspection_run_id:
            return job
    return None


def activity_from_job_input(input_data: dict[str, Any] | None) -> RunActivity:
    if not isinstance(input_data, dict):
        return "investigating"
    if input_data.get("index_only"):
        return "indexing"
    if input_data.get("match_only"):
        return "matching"
    return "investigating"


def compute_run_activity(session: Session, run: InspectionRun) -> RunActivity | None:
    status = str(run.status or "").lower()
    if status not in {"queued", "processing"}:
        return None

    job = find_active_job_for_run(session, int(run.id))
    if job is not None:
        return activity_from_job_input(cast(dict[str, Any] | None, job.input_data))

    if status == "processing":
        return "stuck"
    return "investigating"


def heal_stale_inspection_run(session: Session, run: InspectionRun) -> bool:
    """Mark runs stuck in processing/queued with no active job as failed."""
    status = str(run.status or "").lower()
    if status not in {"queued", "processing"}:
        return False
    if status == "queued" and run.evidence_id is None:
        return False
    if find_active_job_for_run(session, int(run.id)) is not None:
        return False

    storage = StorageService(session)
    storage.update_inspection_run_status(
        int(run.id),
        "failed",
        completed_at=datetime.now(timezone.utc),
        error_message=_STALE_RUN_MESSAGE,
    )
    return True


def heal_stale_inspection_runs(session: Session, runs: list[InspectionRun]) -> None:
    for run in runs:
        heal_stale_inspection_run(session, run)


def inspection_run_to_response(session: Session, run: InspectionRun):
    """Build API response with activity label and auto-heal stale processing runs."""
    from models.schemas import InspectionRunResponse

    heal_stale_inspection_run(session, run)
    session.refresh(run)
    base = InspectionRunResponse.model_validate(run)
    activity = compute_run_activity(session, run)
    return base.model_copy(update={"activity": activity})
