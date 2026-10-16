"""Tests for inspection run reprocess API."""

from __future__ import annotations

import uuid
from typing import cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models.inspection_run import InspectionRun
from models.models import Drawing, EvidenceRecord, JobQueue, Project
from services.inspection_matching_jobs import JOB_TYPE_INSPECTION_MATCH


def _seed_run_with_evidence(db: Session, project: Project) -> tuple[int, int, int, int]:
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
        meta={"matchInvestigation": {"at": "2026-01-01T00:00:00+00:00"}},
    )
    db.add(evidence)
    db.flush()

    run = InspectionRun(
        project_id=project_id,
        master_drawing_id=drawing.id,
        evidence_id=evidence.id,
        status="complete",
        error_message="old error",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    return (
        project_id,
        cast(int, run.id),
        cast(int, evidence.id),
        cast(int, drawing.id),
    )


def test_reprocess_inspection_run_enqueues_job(
    client: TestClient, db_session: Session, project: Project
) -> None:
    project_id, run_id, evidence_id, master_id = _seed_run_with_evidence(
        db_session, project
    )

    response = client.post(
        f"/api/projects/{project_id}/inspections/runs/{run_id}/reprocess",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["inspection_run_id"] == run_id
    assert body["status"] == "processing"

    db_session.expire_all()
    run = db_session.get(InspectionRun, run_id)
    assert run is not None
    assert run.status == "processing"
    assert run.error_message is None

    job = (
        db_session.query(JobQueue)
        .filter(
            JobQueue.job_type == JOB_TYPE_INSPECTION_MATCH,
            JobQueue.project_id == project_id,
        )
        .order_by(JobQueue.id.desc())
        .first()
    )
    assert job is not None
    input_data = cast(dict, job.input_data)
    assert input_data["inspection_id"] == str(evidence_id)
    assert input_data["drawing_id"] == str(master_id)
    assert input_data["force_investigate"] is True
    assert input_data["inspection_run_id"] == run_id
