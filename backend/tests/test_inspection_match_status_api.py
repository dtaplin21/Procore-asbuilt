"""Tests for GET /api/inspections/{inspection_id}/match-status."""

from __future__ import annotations

import uuid
from typing import cast

import pytest
from sqlalchemy.orm import Session

from models.drawing_overlay import DrawingOverlay
from models.models import Company, Drawing, EvidenceRecord, Project
from models.inspection_run import InspectionRun


def _unique() -> str:
    return uuid.uuid4().hex[:12]


def _seed_run_with_overlay(
    db: Session,
    *,
    match_status: str,
    with_bbox: bool = False,
) -> tuple[int, str]:
    company = Company(name=f"Co {_unique()}", procore_company_id=f"pc-{_unique()}")
    db.add(company)
    db.flush()

    project = Project(
        company_id=company.id,
        procore_project_id=f"pp-{_unique()}",
        name="Test Project",
    )
    db.add(project)
    db.flush()

    drawing = Drawing(
        project_id=project.id,
        source="upload",
        name="Master",
        storage_key=f"drawings/{_unique()}.pdf",
    )
    db.add(drawing)
    db.flush()

    evidence = EvidenceRecord(
        project_id=project.id,
        type="inspection_doc",
        title="Inspection PDF",
        storage_key=f"evidence/{_unique()}.pdf",
    )
    db.add(evidence)
    db.flush()

    run = InspectionRun(
        project_id=project.id,
        master_drawing_id=drawing.id,
        evidence_id=evidence.id,
        status="complete",
    )
    db.add(run)
    db.flush()

    geometry = {"page": 1, "type": "point", "x": 0.0, "y": 0.0}
    if with_bbox:
        geometry = {
            "page": 1,
            "type": "rect",
            "x": 0.1,
            "y": 0.2,
            "width": 0.3,
            "height": 0.4,
            "label": "inspection_match",
        }

    overlay = DrawingOverlay(
        master_drawing_id=drawing.id,
        inspection_run_id=run.id,
        geometry=geometry,
        status="unknown",
        meta={"match_status": match_status, "confidence": 0.91, "score": 0.88},
    )
    db.add(overlay)
    db.commit()

    return cast(int, evidence.id), str(evidence.id)


class TestInspectionMatchStatusApi:
    def test_matched_returns_bbox_without_confidence(self, client, db_session: Session) -> None:
        _, inspection_id = _seed_run_with_overlay(
            db_session,
            match_status="matched",
            with_bbox=True,
        )

        response = client.get(f"/api/inspections/{inspection_id}/match-status")
        assert response.status_code == 200
        body = response.json()

        assert body == {
            "inspection_id": inspection_id,
            "match_status": "matched",
            "bbox": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
        }
        assert "confidence" not in body
        assert "score" not in body
        assert "classification_confidence" not in body

    def test_needs_review_returns_null_bbox(self, client, db_session: Session) -> None:
        _, inspection_id = _seed_run_with_overlay(
            db_session,
            match_status="needs_review",
            with_bbox=False,
        )

        response = client.get(f"/api/inspections/{inspection_id}/match-status")
        assert response.status_code == 200
        body = response.json()

        assert body["match_status"] == "needs_review"
        assert body["bbox"] is None
        assert "confidence" not in body

    def test_unknown_inspection_returns_404(self, client) -> None:
        response = client.get("/api/inspections/does-not-exist/match-status")
        assert response.status_code == 404

    def test_run_without_overlay_returns_no_match(self, client, db_session: Session) -> None:
        company = Company(name=f"Co {_unique()}", procore_company_id=f"pc-{_unique()}")
        db_session.add(company)
        db_session.flush()

        project = Project(
            company_id=company.id,
            procore_project_id=f"pp-{_unique()}",
            name="Test Project",
        )
        db_session.add(project)
        db_session.flush()

        drawing = Drawing(
            project_id=project.id,
            source="upload",
            name="Master",
            storage_key=f"drawings/{_unique()}.pdf",
        )
        db_session.add(drawing)
        db_session.flush()

        evidence = EvidenceRecord(
            project_id=project.id,
            type="inspection_doc",
            title="Inspection PDF",
            storage_key=f"evidence/{_unique()}.pdf",
        )
        db_session.add(evidence)
        db_session.flush()

        run = InspectionRun(
            project_id=project.id,
            master_drawing_id=drawing.id,
            evidence_id=evidence.id,
            status="complete",
        )
        db_session.add(run)
        db_session.commit()

        inspection_id = str(evidence.id)
        response = client.get(f"/api/inspections/{inspection_id}/match-status")
        assert response.status_code == 200
        assert response.json()["match_status"] == "no_match"
        assert response.json()["bbox"] is None


class TestInspectionMatchStatusApiNoScoreLeaks:
    def test_match_status_json_has_no_nested_score_fields(
        self,
        client,
        db_session: Session,
    ) -> None:
        from api.schemas.frontend_safe import contains_forbidden_frontend_score_fields

        _, inspection_id = _seed_run_with_overlay(
            db_session,
            match_status="needs_review",
            with_bbox=False,
        )

        response = client.get(f"/api/inspections/{inspection_id}/match-status")
        body = response.json()

        assert response.status_code == 200
        assert contains_forbidden_frontend_score_fields(body) == []
