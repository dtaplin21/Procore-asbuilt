"""
Drawing render job queue integration.

Enqueues render jobs to the DB-backed job queue. The actual PDF rendering
is CPU-bound and runs via asyncio.to_thread() or a worker process.
"""

from __future__ import annotations

import asyncio
from typing import Optional, cast

from sqlalchemy.orm import Session

from models.models import JobQueue, Project, User, UserCompany
from observability.workflow_logging import log_job_status_transition
from services.drawing_rendering import run_render_drawing_job

DRAWING_RENDER_JOB_TYPE = "drawing_render"


def _resolve_user_id_for_project(db: Session, project_id: int) -> int:
    """Get a valid user_id for job creation (project's company member or first user)."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"Project {project_id} not found")

    uc = (
        db.query(UserCompany)
        .filter(UserCompany.company_id == project.company_id)
        .first()
    )
    if uc:
        return cast(int, uc.user_id)

    user = db.query(User).order_by(User.id.asc()).first()
    if not user:
        raise ValueError("No users in database; cannot enqueue drawing render job")
    return cast(int, user.id)


def enqueue_drawing_render_job(
    db: Session,
    project_id: int,
    drawing_id: int,
    user_id: Optional[int] = None,
) -> JobQueue:
    """Enqueue a drawing render job. Uses DB-backed JobQueue."""
    if user_id is None:
        user_id = _resolve_user_id_for_project(db, project_id)

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"Project {project_id} not found")

    previous_status = None
    job = JobQueue(
        user_id=user_id,
        company_id=project.company_id,
        project_id=project_id,
        job_type=DRAWING_RENDER_JOB_TYPE,
        status="pending",
        input_data={"drawing_id": drawing_id},
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


async def process_drawing_render_job(drawing_id: int) -> None:
    """
    Async wrapper for run_render_drawing_job. PyMuPDF rendering is CPU-bound,
    so we offload to a thread via asyncio.to_thread().
    """
    await asyncio.to_thread(run_render_drawing_job, drawing_id)
