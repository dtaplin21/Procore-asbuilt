"""
Async job worker for JobQueue.

Polls for pending jobs and dispatches to type-specific handlers.
Run as a separate process: python -m services.job_worker
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import SessionLocal
from models.models import JobQueue
from observability.workflow_logging import log_job_status_transition
from services.drawing_render_jobs import (
    DRAWING_RENDER_JOB_TYPE,
    process_drawing_render_job,
)

logger = logging.getLogger(__name__)


async def handle_job(job: JobQueue) -> None:
    """Dispatch job to the appropriate handler based on job_type."""
    if job.job_type == DRAWING_RENDER_JOB_TYPE:
        drawing_id = job.input_data.get("drawing_id")
        if drawing_id is None:
            raise ValueError("drawing_render job missing input_data.drawing_id")
        await process_drawing_render_job(int(drawing_id))
        return

    raise ValueError(f"Unknown job_type: {job.job_type}")


def _claim_pending_job(db: Session) -> JobQueue | None:
    """Atomically claim the oldest pending job. Returns None if none available."""
    result = db.execute(
        select(JobQueue)
        .where(JobQueue.status == "pending")
        .order_by(JobQueue.id.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = result.scalars().first()
    if not job:
        return None

    previous_status = job.status
    job.status = "processing"
    job.started_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    log_job_status_transition(
        project_id=job.project_id,
        job_id=job.id,
        status=job.status,
        previous_status=previous_status,
    )
    return job


def _mark_job_completed(db: Session, job_id: int) -> None:
    db.query(JobQueue).filter(JobQueue.id == job_id).update(
        {"status": "completed", "completed_at": datetime.now(timezone.utc)}
    )
    db.commit()


def _mark_job_failed(db: Session, job_id: int, error_message: str) -> None:
    db.query(JobQueue).filter(JobQueue.id == job_id).update(
        {
            "status": "failed",
            "completed_at": datetime.now(timezone.utc),
            "error_message": error_message,
        }
    )
    db.commit()


async def process_one_job() -> bool:
    """Claim and process one pending job. Returns True if a job was processed."""
    db = SessionLocal()
    try:
        job = _claim_pending_job(db)
        if not job:
            return False

        job_id = job.id
        job_type = job.job_type
        logger.info("Processing job %s (type=%s)", job_id, job_type)

        try:
            await handle_job(job)
            _mark_job_completed(db, job_id)
            log_job_status_transition(
                project_id=job.project_id,
                job_id=job.id,
                status="completed",
                previous_status="processing",
            )
            logger.info("Job %s completed", job_id)
        except Exception as exc:
            _mark_job_failed(db, job_id, str(exc))
            log_job_status_transition(
                project_id=job.project_id,
                job_id=job.id,
                status="failed",
                previous_status="processing",
            )
            logger.exception("Job %s failed: %s", job_id, exc)

        return True
    finally:
        db.close()


async def run_worker_loop(poll_interval_seconds: float = 2.0) -> None:
    """Poll for and process jobs until interrupted."""
    logger.info("Job worker started (poll_interval=%s)", poll_interval_seconds)
    while True:
        try:
            processed = await process_one_job()
            if not processed:
                await asyncio.sleep(poll_interval_seconds)
        except asyncio.CancelledError:
            logger.info("Job worker stopped")
            raise
        except Exception:
            logger.exception("Worker loop error")
            await asyncio.sleep(poll_interval_seconds)


def main() -> None:
    import os

    logging.basicConfig(level=logging.INFO)
    poll = float(os.getenv("JOB_WORKER_POLL_SECONDS", "2"))
    asyncio.run(run_worker_loop(poll_interval_seconds=poll))


if __name__ == "__main__":
    main()
