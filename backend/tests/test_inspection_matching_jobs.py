"""Tests for inspection matching jobs."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import cast
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from ai.pipelines.drawing_location_resolver import ResolutionMethod
from ai.pipelines.location_match_orchestrator import LocationMatchResult
from database import SessionLocal
from models.drawing_overlay import DrawingOverlay
from models.drawing_match_candidate import DrawingMatchCandidate
from models.document_clue import DocumentClue
from models.document_extraction import DocumentExtraction
from models.models import Company, Drawing, EvidenceRecord, JobQueue, Project
from models.inspection_run import InspectionRun
from services.inspection_match_persistence import MATCH_SCORE_THRESHOLD
from services.inspection_matching_jobs import (
    DEFERRED_MATCH_META_KEY,
    JOB_TYPE_INSPECTION_MATCH,
    flush_deferred_inspection_matches_for_drawing,
    maybe_enqueue_inspection_match_after_extraction,
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


def _matched_result(master_drawing_id: int) -> LocationMatchResult:
    return LocationMatchResult(
        master_drawing_id=master_drawing_id,
        method=ResolutionMethod.COORDINATE_LOOKUP,
        confidence=MATCH_SCORE_THRESHOLD + 0.1,
        bbox_fractional=(0.1, 0.2, 0.4, 0.5),
        page=1,
        region_id=99,
    )


@patch("services.inspection_matching_jobs.resolve_evidence_location")
def test_run_inspection_match_job_calls_orchestrator(
    mock_resolve,
    db: Session,
):
    run, file_id = _seed_run(db)
    master_drawing_id = cast(int, run.master_drawing_id)
    mock_resolve.return_value = _matched_result(master_drawing_id)

    status = run_inspection_match_job(
        {
            "inspection_id": file_id,
            "drawing_id": str(master_drawing_id),
            "page": 1,
            "project_id": cast(int, run.project_id),
        },
        db,
    )

    assert status == "matched"
    mock_resolve.assert_called_once_with(
        db,
        evidence_id=int(file_id),
        master_drawing_id=master_drawing_id,
        page=1,
    )


@patch("services.inspection_matching_jobs.resolve_evidence_location")
def test_run_inspection_match_job_matched(mock_resolve, db: Session):
    run, file_id = _seed_run(db)
    master_drawing_id = cast(int, run.master_drawing_id)
    mock_resolve.return_value = _matched_result(master_drawing_id)

    status = run_inspection_match_job(
        {
            "inspection_id": file_id,
            "drawing_id": str(master_drawing_id),
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
    assert cast(str, candidate.source) == ResolutionMethod.COORDINATE_LOOKUP.value


@patch("services.inspection_matching_jobs.resolve_evidence_location")
def test_run_inspection_match_job_weak_match_needs_review(mock_resolve, db: Session):
    run, file_id = _seed_run(db)
    master_drawing_id = cast(int, run.master_drawing_id)
    mock_resolve.return_value = LocationMatchResult(
        master_drawing_id=master_drawing_id,
        method=ResolutionMethod.REFERENCE_LOOKUP,
        confidence=MATCH_SCORE_THRESHOLD - 0.2,
        bbox_fractional=(0.1, 0.2, 0.4, 0.5),
        page=1,
    )

    status = run_inspection_match_job(
        {
            "inspection_id": file_id,
            "drawing_id": str(master_drawing_id),
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


@patch("services.inspection_matching_jobs.resolve_evidence_location")
def test_run_inspection_match_job_unresolved_is_no_match(mock_resolve, db: Session):
    run, file_id = _seed_run(db)
    master_drawing_id = cast(int, run.master_drawing_id)
    mock_resolve.return_value = LocationMatchResult.unresolved(master_drawing_id)

    status = run_inspection_match_job(
        {
            "inspection_id": file_id,
            "drawing_id": str(master_drawing_id),
            "page": 1,
            "inspection_run_id": run.id,
        },
        db,
    )

    assert status == "no_match"
    overlay = (
        db.query(DrawingOverlay)
        .filter(DrawingOverlay.inspection_run_id == run.id)
        .one()
    )
    meta = cast(dict, overlay.meta)
    assert meta["match_status"] == "no_match"


@patch("services.inspection_matching_jobs.resolve_evidence_location")
def test_run_inspection_match_job_uses_explicit_run_id_over_id_collision(
    mock_resolve,
    db: Session,
):
    """Evidence id equal to an older run id must not attach overlays to that run."""
    mock_resolve.return_value = LocationMatchResult.unresolved(1)
    target_id = 80000 + int(uuid.uuid4().hex[:4], 16) % 10000

    company = Company(name=f"Co {uuid.uuid4().hex[:8]}", procore_company_id=f"pc-{uuid.uuid4().hex[:8]}")
    db.add(company)
    db.flush()

    project = Project(
        company_id=company.id,
        procore_project_id=f"pp-{uuid.uuid4().hex[:8]}",
        name="Collision",
    )
    db.add(project)
    db.flush()

    drawing = Drawing(
        project_id=project.id,
        source="upload",
        name="Master",
        storage_key="drawings/collision.pdf",
    )
    db.add(drawing)
    db.flush()

    old_evidence = EvidenceRecord(
        project_id=project.id,
        type="inspection_doc",
        title="Old",
        storage_key="evidence/old.pdf",
    )
    db.add(old_evidence)
    db.flush()

    old_run = InspectionRun(
        id=target_id,
        project_id=project.id,
        master_drawing_id=drawing.id,
        evidence_id=old_evidence.id,
        status="complete",
    )
    db.add(old_run)
    db.flush()

    new_evidence = EvidenceRecord(
        id=target_id,
        project_id=project.id,
        type="inspection_doc",
        title="New",
        storage_key="evidence/new.pdf",
    )
    db.add(new_evidence)
    db.flush()

    new_run = InspectionRun(
        project_id=project.id,
        master_drawing_id=drawing.id,
        evidence_id=new_evidence.id,
        status="complete",
    )
    db.add(new_run)
    db.flush()

    extraction = DocumentExtraction(
        file_id=str(new_evidence.id),
        document_type="inspection_report",
        classification_confidence=0.9,
    )
    db.add(extraction)
    db.commit()

    assert cast(int, old_run.id) == cast(int, new_evidence.id)

    status = run_inspection_match_job(
        {
            "inspection_id": str(new_evidence.id),
            "drawing_id": str(drawing.id),
            "page": 1,
            "inspection_run_id": new_run.id,
        },
        db,
    )

    assert status == "no_match"
    assert (
        db.query(DrawingOverlay)
        .filter(DrawingOverlay.inspection_run_id == new_run.id)
        .count()
        == 1
    )
    assert (
        db.query(DrawingOverlay)
        .filter(DrawingOverlay.inspection_run_id == old_run.id)
        .count()
        == 0
    )


def _match_job_count_for_inspection(db: Session, inspection_id: str) -> int:
    jobs = (
        db.query(JobQueue)
        .filter(JobQueue.job_type == JOB_TYPE_INSPECTION_MATCH)
        .all()
    )
    count = 0
    for job in jobs:
        input_data = getattr(job, "input_data", None)
        if isinstance(input_data, dict) and str(input_data.get("inspection_id")) == inspection_id:
            count += 1
    return count


def test_maybe_enqueue_inspection_match_after_extraction_defers_when_index_not_ready(
    db: Session,
) -> None:
    run, file_id = _seed_run(db)
    drawing_id = cast(int, run.master_drawing_id)
    project_id = cast(int, run.project_id)
    evidence_id = int(file_id)

    job = maybe_enqueue_inspection_match_after_extraction(
        db,
        evidence_id=evidence_id,
        project_id=project_id,
        inspection_id=file_id,
        master_drawing_id=drawing_id,
        inspection_run_id=cast(int, run.id),
    )

    assert job is None
    evidence = db.query(EvidenceRecord).filter(EvidenceRecord.id == evidence_id).one()
    meta = cast(dict, evidence.meta)
    assert DEFERRED_MATCH_META_KEY in meta

    overlay = (
        db.query(DrawingOverlay)
        .filter(DrawingOverlay.inspection_run_id == run.id)
        .one()
    )
    overlay_meta = cast(dict, overlay.meta)
    assert overlay_meta["match_status"] == "index_pending"
    assert _match_job_count_for_inspection(db, file_id) == 0


def test_flush_deferred_inspection_matches_enqueues_after_index(db: Session) -> None:
    run, file_id = _seed_run(db)
    drawing_id = cast(int, run.master_drawing_id)
    project_id = cast(int, run.project_id)
    evidence_id = int(file_id)

    maybe_enqueue_inspection_match_after_extraction(
        db,
        evidence_id=evidence_id,
        project_id=project_id,
        inspection_id=file_id,
        master_drawing_id=drawing_id,
        inspection_run_id=cast(int, run.id),
    )

    drawing = db.query(Drawing).filter(Drawing.id == drawing_id).one()
    setattr(drawing, "index_status", "ready")
    from services.storage import StorageService

    storage = StorageService(db)
    storage.create_drawing_region(
        drawing_id,
        label="COLO",
        geometry={"type": "rect", "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
        location_tags=["COLO"],
    )
    db.commit()

    before = _match_job_count_for_inspection(db, file_id)
    enqueued = flush_deferred_inspection_matches_for_drawing(db, drawing_id)

    assert enqueued == 1
    evidence = db.query(EvidenceRecord).filter(EvidenceRecord.id == evidence_id).one()
    meta = cast(dict, evidence.meta or {})
    assert DEFERRED_MATCH_META_KEY not in meta
    assert _match_job_count_for_inspection(db, file_id) == before + 1
