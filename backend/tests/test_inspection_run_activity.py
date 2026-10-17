"""Tests for inspection run activity labels and stale-run healing."""

from __future__ import annotations

import uuid
from typing import cast

from sqlalchemy.orm import Session

from models.inspection_run import InspectionRun
from models.models import Drawing, EvidenceRecord, JobQueue, Project, User, UserCompany
from services.inspection_matching_jobs import JOB_TYPE_INSPECTION_MATCH
from services.inspection_run_activity import (
    activity_from_job_input,
    compute_run_activity,
    heal_stale_inspection_run,
    inspection_run_to_response,
)


def _seed_processing_run(db: Session, project: Project) -> InspectionRun:
    suffix = uuid.uuid4().hex[:8]
    project_id = cast(int, project.id)
    drawing = Drawing(
        project_id=project_id,
        source="upload",
        name="Master",
        storage_key=f"drawings/{suffix}.pdf",
    )
    db.add(drawing)
    db.flush()
    evidence = EvidenceRecord(
        project_id=project_id,
        type="inspection_doc",
        title="Inspection",
        storage_key=f"evidence/{suffix}.pdf",
    )
    db.add(evidence)
    db.flush()
    run = InspectionRun(
        project_id=project_id,
        master_drawing_id=drawing.id,
        evidence_id=evidence.id,
        status="processing",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def test_activity_from_job_input() -> None:
    assert activity_from_job_input({"index_only": True}) == "indexing"
    assert activity_from_job_input({"match_only": True}) == "matching"
    assert activity_from_job_input({}) == "investigating"


def test_compute_run_activity_uses_pending_job(db_session: Session, project: Project) -> None:
    run = _seed_processing_run(db_session, project)
    user = User(email=f"activity-{uuid.uuid4().hex[:8]}@example.com")
    db_session.add(user)
    db_session.flush()
    db_session.add(UserCompany(user_id=user.id, company_id=project.company_id))
    db_session.commit()

    job = JobQueue(
        user_id=user.id,
        company_id=cast(int, project.company_id),
        project_id=cast(int, project.id),
        job_type=JOB_TYPE_INSPECTION_MATCH,
        status="pending",
        input_data={
            "inspection_run_id": run.id,
            "index_only": True,
            "inspection_id": str(run.evidence_id),
            "drawing_id": str(run.master_drawing_id),
        },
    )
    db_session.add(job)
    db_session.commit()

    assert compute_run_activity(db_session, run) == "indexing"


def test_heal_stale_run_without_active_job(db_session: Session, project: Project) -> None:
    run = _seed_processing_run(db_session, project)

    healed = heal_stale_inspection_run(db_session, run)
    assert healed is True

    db_session.refresh(run)
    assert run.status == "failed"
    assert run.error_message is not None


def test_list_response_heals_stale_run(db_session: Session, project: Project) -> None:
    run = _seed_processing_run(db_session, project)

    response = inspection_run_to_response(db_session, run)

    assert response.status == "failed"
    assert response.activity is None
