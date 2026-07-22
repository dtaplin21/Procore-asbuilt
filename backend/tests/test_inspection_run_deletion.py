"""Tests for DELETE /api/projects/{project_id}/inspections/runs/{run_id}."""

from __future__ import annotations

from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models.document_extraction import DocumentExtraction
from models.drawing_overlay import DrawingOverlay
from models.inspection_run import InspectionRun
from models.models import EvidenceRecord, JobQueue, User, UserCompany
from services.inspection_matching_jobs import JOB_TYPE_INSPECTION_MATCH
from services.storage import StorageService


@pytest.fixture
def delete_run_setup(db_session: Session, project):
    from models.models import Drawing

    storage = StorageService(db_session)
    drawing = Drawing(
        project_id=project.id,
        source="upload",
        name="Master.pdf",
        storage_key=f"drawings/{project.id}/master.pdf",
    )
    db_session.add(drawing)
    db_session.commit()
    db_session.refresh(drawing)

    run = storage.create_inspection_run(
        project_id=cast(int, project.id),
        master_drawing_id=cast(int, drawing.id),
    )
    return project, drawing, run, storage, db_session


class TestDeleteInspectionRun:
    def test_delete_run_removes_run_evidence_and_pipeline_rows(
        self,
        client: TestClient,
        delete_run_setup,
    ) -> None:
        project, drawing, run, storage, db_session = delete_run_setup
        project_id = cast(int, project.id)
        run_id = cast(int, run.id)
        master_id = cast(int, drawing.id)

        evidence = storage.create_evidence_record(
            project_id=project_id,
            type="inspection_doc",
            title="report.pdf",
            storage_key=f"projects/{project_id}/evidence/{run_id}.pdf",
            content_type="application/pdf",
        )
        evidence_id = cast(int, evidence.id)
        setattr(run, "evidence_id", evidence_id)
        db_session.commit()

        extraction = DocumentExtraction(
            file_id=str(evidence_id),
            document_type="inspection_report",
            classification_confidence=0.9,
        )
        db_session.add(extraction)
        db_session.commit()

        overlay = DrawingOverlay(
            master_drawing_id=master_id,
            inspection_run_id=run_id,
            geometry={"type": "point", "x": 0.1, "y": 0.2, "page": 1},
            status="unknown",
            meta={"match_status": "needs_review"},
        )
        db_session.add(overlay)
        db_session.commit()

        response = client.delete(f"/api/projects/{project_id}/inspections/runs/{run_id}")
        assert response.status_code == 200
        assert response.json() == {"ok": True}

        db_session.expire_all()
        assert db_session.query(InspectionRun).filter_by(id=run_id).first() is None
        assert db_session.query(EvidenceRecord).filter_by(id=evidence_id).first() is None
        assert (
            db_session.query(DrawingOverlay)
            .filter(DrawingOverlay.inspection_run_id == run_id)
            .count()
            == 0
        )
        assert (
            db_session.query(DocumentExtraction)
            .filter(DocumentExtraction.file_id == str(evidence_id))
            .count()
            == 0
        )

    def test_delete_unknown_run_returns_404(
        self,
        client: TestClient,
        delete_run_setup,
    ) -> None:
        project, _, _, _, _ = delete_run_setup
        response = client.delete(
            f"/api/projects/{cast(int, project.id)}/inspections/runs/999999"
        )
        assert response.status_code == 404

    def test_delete_run_removes_pending_match_jobs(
        self,
        client: TestClient,
        delete_run_setup,
        db_session: Session,
    ) -> None:
        project, drawing, run, storage, db_session = delete_run_setup
        project_id = cast(int, project.id)
        run_id = cast(int, run.id)

        evidence = storage.create_evidence_record(
            project_id=project_id,
            type="inspection_doc",
            title="Queued report.pdf",
            storage_key=f"evidence/{run_id}.pdf",
            content_type="application/pdf",
        )
        setattr(run, "evidence_id", cast(int, evidence.id))
        db_session.commit()

        import uuid

        user = User(email=f"delete-test-{uuid.uuid4().hex[:8]}@example.com")
        db_session.add(user)
        db_session.flush()
        db_session.add(UserCompany(user_id=user.id, company_id=project.company_id))
        db_session.commit()

        job = JobQueue(
            user_id=user.id,
            company_id=project.company_id,
            project_id=project_id,
            job_type=JOB_TYPE_INSPECTION_MATCH,
            status="pending",
            input_data={
                "inspection_id": str(evidence.id),
                "drawing_id": str(drawing.id),
                "page": 1,
            },
        )
        db_session.add(job)
        db_session.commit()
        job_id = cast(int, job.id)

        response = client.delete(f"/api/projects/{project_id}/inspections/runs/{run_id}")
        assert response.status_code == 200

        db_session.expire_all()
        assert db_session.query(JobQueue).filter_by(id=job_id).first() is None
