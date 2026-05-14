"""
Enqueue drawing compare jobs (master vs sub) once page-1 renditions are ready.

``enqueue_drawing_compare_job`` requires both master and sub to have page-1
renditions. :func:`notify_drawing_render_complete` runs from the render pipeline
after ``processing_status -> ready`` so compare is triggered when rasters exist;
when the canonical **master** finishes, it fans out to all
``upload_intent == "sub"`` rows.

``input_data`` uses JSON-serializable values only (ints and bools; no ORM objects).
"""

from __future__ import annotations

from typing import Optional, cast

from sqlalchemy.orm import Session

from api.upload_intent_form import drawing_has_sub_upload_intent
from models.models import Drawing, JobQueue, Project
from observability.workflow_logging import log_job_status_transition
from services.job_input_data import coerce_job_int
from services.storage import StorageService, get_project_master_drawing

DRAWING_COMPARE_JOB_TYPE = "drawing_compare"


def _pending_compare_job_for_sub(
    db: Session, project_id: int, sub_drawing_id: int
) -> Optional[JobQueue]:
    """Return an in-flight compare job for the same sub, if any (idempotent enqueue)."""
    rows = (
        db.query(JobQueue)
        .filter(
            JobQueue.project_id == project_id,
            JobQueue.job_type == DRAWING_COMPARE_JOB_TYPE,
            JobQueue.status.in_(["pending", "processing"]),
        )
        .order_by(JobQueue.id.desc())
        .all()
    )
    for job in rows:
        data = job.input_data if isinstance(job.input_data, dict) else {}
        raw_sub = data.get("sub_drawing_id")
        if raw_sub is None:
            continue
        try:
            if coerce_job_int(raw_sub, "sub_drawing_id") == int(sub_drawing_id):
                return job
        except ValueError:
            continue
    return None


def enqueue_drawing_compare_job(
    db: Session,
    *,
    project_id: int,
    sub_drawing_id: int,
) -> Optional[JobQueue]:
    """
    Queue a ``drawing_compare`` job for a sub drawing against the project master.

    Returns ``None`` if:
    - Sub drawing is missing or not in the project
    - Sub was not uploaded with explicit ``upload_intent == "sub"``
    - Project has no resolvable master

    Otherwise returns a job (new or existing pending/processing for this sub).
    ``input_data`` uses JSON-serializable values (ints, bools).

    Returns ``None`` when page-1 renditions are not ready for **both** drawings;
    re-invoke after render completes (compare defaults to page 1).
    """
    sub = (
        db.query(Drawing)
        .filter(Drawing.id == sub_drawing_id, Drawing.project_id == project_id)
        .first()
    )
    if sub is None or not drawing_has_sub_upload_intent(sub):
        return None

    master = get_project_master_drawing(db, project_id)
    if master is None:
        return None

    master_id = cast(int, master.id)
    if master_id == int(sub_drawing_id):
        return None

    existing = _pending_compare_job_for_sub(db, project_id, sub_drawing_id)
    if existing is not None:
        return existing

    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        return None

    from services.drawing_render_jobs import _resolve_user_id_for_project

    user_id = _resolve_user_id_for_project(db, project_id)
    storage = StorageService(db)
    master_ready = storage.get_drawing_rendition(master_id, 1) is not None
    sub_ready = storage.get_drawing_rendition(sub_drawing_id, 1) is not None
    renditions_ready = bool(master_ready and sub_ready)
    if not renditions_ready:
        return None

    previous_status = None
    job = JobQueue(
        user_id=user_id,
        company_id=cast(int, project.company_id),
        project_id=project_id,
        job_type=DRAWING_COMPARE_JOB_TYPE,
        status="pending",
        input_data={
            "project_id": project_id,
            "master_drawing_id": master_id,
            "sub_drawing_id": int(sub_drawing_id),
            "renditions_ready": True,
        },
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


def notify_drawing_render_complete(db: Session, drawing_id: int) -> None:
    """
    After rasterization succeeds, try to queue compare jobs.

    - If this drawing is an explicit **sub** (``upload_intent == "sub"``), try
      enqueue for that sub (no job until master page-1 is also ready).
    - If this drawing is the project's **canonical master** (see
      :func:`~services.storage.get_project_master_drawing`), try enqueue for
      each row with ``upload_intent == "sub"`` (covers sub rendered before master).
    """
    drawing = db.query(Drawing).filter(Drawing.id == drawing_id).first()
    if drawing is None:
        return
    pid = cast(int, drawing.project_id)

    if drawing_has_sub_upload_intent(drawing):
        enqueue_drawing_compare_job(
            db, project_id=pid, sub_drawing_id=drawing_id
        )
        return

    master = get_project_master_drawing(db, pid)
    if master is None or cast(int, master.id) != drawing_id:
        return

    sub_rows = (
        db.query(Drawing)
        .filter(
            Drawing.project_id == pid,
            Drawing.upload_intent == "sub",
        )
        .all()
    )
    for sub in sub_rows:
        enqueue_drawing_compare_job(
            db, project_id=pid, sub_drawing_id=cast(int, sub.id)
        )
