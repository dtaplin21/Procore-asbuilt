"""Phase 21 — end-to-end UCSF inspection report pipeline test."""

from __future__ import annotations

import uuid
from typing import cast
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ai.pipelines.clue_expander import expand_clue_value
from ai.pipelines.clue_extractor import build_clues
from ai.pipelines.document_extraction_orchestrator import run_document_extraction
from ai.schemas.document_extraction_schemas import DocumentType
from api.schemas.frontend_safe import contains_forbidden_frontend_score_fields
from models.drawing_match_candidate import DrawingMatchCandidate
from models.drawing_overlay import DrawingOverlay
from models.document_clue import DocumentClue
from models.models import Company, Drawing, EvidenceRecord, Project, User, UserCompany
from models.inspection_run import InspectionRun
from services.inspection_matching_jobs import MATCH_SCORE_THRESHOLD, run_inspection_match_job
from services.storage import StorageService
from tests.fixtures.ucsf_inspection_report import (
    UCSF_CLASSIFICATION,
    UCSF_EXPECTED_PERSISTED_CLUE_VALUES,
    UCSF_EXPECTED_SEARCH_TERMS,
    UCSF_INSPECTION_FIELDS,
    UCSF_REPORT_TEXT,
    UCSF_UNIVERSAL_FIELDS,
)


def _unique() -> str:
    return uuid.uuid4().hex[:12]


def _seed_ucsf_run(db: Session) -> tuple[InspectionRun, str, StorageService]:
    company = Company(name=f"Co {_unique()}", procore_company_id=f"pc-{_unique()}")
    db.add(company)
    db.flush()

    project = Project(
        company_id=company.id,
        procore_project_id=f"pp-{_unique()}",
        name="UCSF Test Project",
    )
    db.add(project)
    db.flush()

    user = User(email=f"ucsf-{_unique()}@example.com")
    db.add(user)
    db.flush()
    db.add(UserCompany(user_id=user.id, company_id=company.id))
    db.flush()

    drawing = Drawing(
        project_id=project.id,
        source="upload",
        name="COLO Site Plan",
        storage_key=f"drawings/{_unique()}.pdf",
    )
    db.add(drawing)
    db.flush()

    evidence = EvidenceRecord(
        project_id=project.id,
        type="inspection_doc",
        title="UCSF Underground Sanitary Sewer #1",
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

    storage = StorageService(db)
    storage.create_drawing_region(
        cast(int, drawing.id),
        label="COLO PARKING LOT SANITARY SEWER",
        geometry={"type": "rect", "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
        inspection_type_tags=["Underground Sanitary Sewer #1"],
        location_tags=["COLO", "SS", "SAN"],
    )
    db.commit()

    return run, str(evidence.id), storage


def _ucsf_search_terms_from_clues(clues: list[DocumentClue]) -> set[str]:
    terms: set[str] = set()
    for clue in clues:
        for term in expand_clue_value(cast(str, clue.clue_value)):
            terms.add(term.lower())
    return terms


@patch("ai.pipelines.document_extraction_orchestrator.extract_type_specific_fields")
@patch("ai.pipelines.document_extraction_orchestrator.extract_universal_fields")
@patch("ai.pipelines.document_extraction_orchestrator.classify_document")
def test_ucsf_report_end_to_end_pipeline(
    mock_classify,
    mock_universal,
    mock_type_specific,
    db: Session,
    client: TestClient,
) -> None:
    run, file_id, _storage = _seed_ucsf_run(db)

    mock_classify.return_value = UCSF_CLASSIFICATION
    mock_universal.return_value = UCSF_UNIVERSAL_FIELDS
    mock_type_specific.return_value = UCSF_INSPECTION_FIELDS

    extraction = run_document_extraction(db, file_id, UCSF_REPORT_TEXT)

    assert cast(str, extraction.document_type) == DocumentType.INSPECTION_REPORT.value
    universal = cast(dict, extraction.universal_fields_json)
    assert universal["project_number"] == "02001.161310"
    assert universal["project_name"] == "UCSF Benioff Oakland"
    assert universal["location_text"] == "COLO"
    assert universal["trade"] == "33-Sanitary Sewerage"

    type_specific = cast(dict, extraction.type_specific_fields_json)
    assert type_specific["inspection_name"] == "Underground Sanitary Sewer #1"
    assert any(
        "sanitary sewer inspection prior to backfill" in note.lower()
        for note in type_specific["inspection_notes"]
    )

    clues = (
        db.query(DocumentClue)
        .filter_by(document_extraction_id=cast(int, extraction.id))
        .all()
    )
    assert clues
    persisted_values = {cast(str, clue.clue_value) for clue in clues}
    assert UCSF_EXPECTED_PERSISTED_CLUE_VALUES.issubset(persisted_values)

    built_clues = build_clues(
        DocumentType.INSPECTION_REPORT,
        UCSF_UNIVERSAL_FIELDS,
        UCSF_INSPECTION_FIELDS,
    )
    search_terms = _ucsf_search_terms_from_clues(clues) | {
        term.lower() for clue in built_clues for term in expand_clue_value(clue.value)
    }
    assert UCSF_EXPECTED_SEARCH_TERMS.issubset(search_terms)

    status = run_inspection_match_job(
        {
            "inspection_id": file_id,
            "drawing_id": str(run.master_drawing_id),
            "page": 1,
        },
        db,
    )
    assert status in ("matched", "needs_review", "no_match")

    candidate = (
        db.query(DrawingMatchCandidate)
        .filter(DrawingMatchCandidate.inspection_id == file_id)
        .order_by(DrawingMatchCandidate.rank.asc())
        .first()
    )
    assert candidate is not None
    assert float(cast(float, candidate.score)) > 0

    overlay = (
        db.query(DrawingOverlay)
        .filter(DrawingOverlay.inspection_run_id == run.id)
        .one()
    )
    meta = cast(dict, overlay.meta)
    assert meta["match_status"] in ("matched", "needs_review", "no_match")
    assert "confidence" not in meta
    assert "score" not in meta

    if status == "matched":
        assert float(cast(float, candidate.score)) >= MATCH_SCORE_THRESHOLD

    response = client.get(f"/api/inspections/{file_id}/match-status")
    body = response.json()
    assert response.status_code == 200
    assert body["match_status"] == meta["match_status"]
    assert contains_forbidden_frontend_score_fields(body) == []


def test_ucsf_clue_expansion_covers_drawing_abbreviations() -> None:
    clues = build_clues(
        DocumentType.INSPECTION_REPORT,
        UCSF_UNIVERSAL_FIELDS,
        UCSF_INSPECTION_FIELDS,
    )
    search_terms = {
        term.lower()
        for clue in clues
        for term in expand_clue_value(clue.value)
    }

    assert "ss" in search_terms
    assert "san" in search_terms
    assert "sewer lateral" in search_terms
    assert "cleanout" in search_terms
    assert "manhole" in search_terms
    assert "parking lot" in search_terms
