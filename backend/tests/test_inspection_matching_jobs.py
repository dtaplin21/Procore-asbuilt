"""Tests for inspection matching jobs."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import cast
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from ai.pipelines.candidate_tile_selector import CandidateTile
from database import SessionLocal
from models.drawing_overlay import DrawingOverlay
from models.drawing_match_candidate import DrawingMatchCandidate
from models.document_clue import DocumentClue
from models.document_extraction import DocumentExtraction
from models.models import Company, Drawing, EvidenceRecord, Project
from models.inspection_run import InspectionRun
from services.inspection_matching_jobs import (
    MATCH_SCORE_THRESHOLD,
    run_inspection_match_job,
)


def _unique() -> str:
    return uuid.uuid4().hex[:12]


@pytest.fixture
def db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


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

    file_id = str(evidence.id)
    extraction = DocumentExtraction(
        file_id=file_id,
        document_type="inspection_report",
        classification_confidence=0.9,
        universal_fields_json={"location_text": "COLO"},
        type_specific_fields_json={"inspection_name": "Underground Sanitary Sewer #1"},
    )
    db.add(extraction)
    db.flush()
    db.add_all(
        [
            DocumentClue(
                document_extraction_id=extraction.id,
                clue_type="location_text",
                clue_value="COLO",
                source="inspection_report",
                confidence=0.90,
                location_relevant=True,
            ),
            DocumentClue(
                document_extraction_id=extraction.id,
                clue_type="trade",
                clue_value="33-Sanitary Sewerage",
                source="inspection_report",
                confidence=0.85,
                location_relevant=True,
            ),
        ]
    )
    db.commit()

    return run, file_id


def _candidate(confidence: float = 0.75) -> CandidateTile:
    return CandidateTile(
        drawing_id="1",
        page=1,
        text="COLO PARKING LOT SANITARY SEWER",
        confidence=confidence,
        bbox_normalized=(0.1, 0.2, 0.4, 0.5),
        region_id=99,
    )


@patch("services.inspection_matching_jobs.compute_tile_match_score")
@patch("services.inspection_matching_jobs.find_candidate_tiles_from_clues")
def test_run_inspection_match_job_matched(mock_find, mock_score, db: Session):
    run, file_id = _seed_run(db)
    mock_find.return_value = [_candidate()]
    mock_score.return_value = MATCH_SCORE_THRESHOLD + 0.1

    status = run_inspection_match_job(
        {
            "inspection_id": file_id,
            "drawing_id": str(run.master_drawing_id),
            "page": 1,
        },
        db,
    )

    assert status == "matched"
    overlay = (
        db.query(DrawingOverlay)
        .filter(DrawingOverlay.inspection_run_id == run.id)
        .one()
    )
    meta = cast(dict, overlay.meta)
    assert meta["match_status"] == "matched"
    assert "confidence" not in meta
    assert overlay.geometry is not None

    candidate = (
        db.query(DrawingMatchCandidate)
        .filter(DrawingMatchCandidate.inspection_id == file_id)
        .order_by(DrawingMatchCandidate.rank.asc())
        .first()
    )
    assert candidate is not None
    assert float(cast(float, candidate.score)) >= MATCH_SCORE_THRESHOLD


@patch("services.inspection_matching_jobs.compute_tile_match_score")
@patch("services.inspection_matching_jobs.find_candidate_tiles_from_clues")
def test_run_inspection_match_job_weak_clues_needs_review(mock_find, mock_score, db: Session):
    run, file_id = _seed_run(db)
    mock_find.return_value = [_candidate(confidence=0.2)]
    mock_score.return_value = MATCH_SCORE_THRESHOLD - 0.2

    status = run_inspection_match_job(
        {
            "inspection_id": file_id,
            "drawing_id": str(run.master_drawing_id),
            "page": 1,
        },
        db,
    )

    assert status == "needs_review"
    overlay = (
        db.query(DrawingOverlay)
        .filter(DrawingOverlay.inspection_run_id == run.id)
        .one()
    )
    meta = cast(dict, overlay.meta)
    assert meta["match_status"] == "needs_review"


@patch("services.inspection_matching_jobs.find_candidate_tiles_from_clues")
def test_run_inspection_match_job_no_candidates_needs_review(mock_find, db: Session):
    run, file_id = _seed_run(db)
    mock_find.return_value = []

    status = run_inspection_match_job(
        {
            "inspection_id": file_id,
            "drawing_id": str(run.master_drawing_id),
            "page": 1,
        },
        db,
    )

    assert status == "needs_review"
    overlay = (
        db.query(DrawingOverlay)
        .filter(DrawingOverlay.inspection_run_id == run.id)
        .one()
    )
    meta = cast(dict, overlay.meta)
    assert meta["match_status"] == "needs_review"
