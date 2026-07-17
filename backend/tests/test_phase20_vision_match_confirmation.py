"""Phase 20 — vision confirmation stores scores internally only."""

from __future__ import annotations

import uuid
from typing import cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ai.pipelines.vision_match_confirmation import apply_vision_confirmation_result
from api.schemas.frontend_safe import contains_forbidden_frontend_score_fields
from models.drawing_match_candidate import DrawingMatchCandidate
from models.drawing_overlay import DrawingOverlay
from models.models import Company, Drawing, EvidenceRecord, Project
from models.inspection_run import InspectionRun
from services.inspection_match_persistence import MATCH_SCORE_THRESHOLD


def _unique() -> str:
    return uuid.uuid4().hex[:12]


def _seed_run(db: Session) -> tuple[InspectionRun, str]:
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
    db.commit()
    db.refresh(run)

    return run, str(evidence.id)


def test_vision_confirmation_persists_score_in_candidate_table_only(db: Session) -> None:
    run, inspection_id = _seed_run(db)

    status = apply_vision_confirmation_result(
        db,
        inspection_id=inspection_id,
        drawing_id=cast(int, run.master_drawing_id),
        internal_score=MATCH_SCORE_THRESHOLD + 0.05,
        bbox=(0.1, 0.2, 0.4, 0.5),
        region_id=77,
    )

    assert status == "matched"

    candidate = (
        db.query(DrawingMatchCandidate)
        .filter_by(inspection_id=inspection_id, source="vision_confirmation")
        .one()
    )
    assert float(cast(float, candidate.score)) >= MATCH_SCORE_THRESHOLD

    overlay = (
        db.query(DrawingOverlay)
        .filter(DrawingOverlay.inspection_run_id == run.id)
        .one()
    )
    meta = cast(dict, overlay.meta)
    assert meta["match_status"] == "matched"
    assert "score" not in meta
    assert "confidence" not in meta


def test_match_status_endpoint_does_not_expose_candidate_score(
    client: TestClient,
    db_session: Session,
) -> None:
    run, inspection_id = _seed_run(db_session)

    apply_vision_confirmation_result(
        db_session,
        inspection_id=inspection_id,
        drawing_id=cast(int, run.master_drawing_id),
        internal_score=MATCH_SCORE_THRESHOLD - 0.1,
        bbox=(0.1, 0.2, 0.4, 0.5),
    )

    response = client.get(f"/api/inspections/{inspection_id}/match-status")
    body = response.json()

    assert response.status_code == 200
    assert body["match_status"] == "needs_review"
    assert contains_forbidden_frontend_score_fields(body) == []
