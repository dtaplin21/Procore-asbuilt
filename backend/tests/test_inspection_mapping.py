"""
Automated tests for run_inspection_mapping pipeline.

Mocks LLM calls (_classify_inspection_type_llm, _extract_outcomes_llm) to lock in
behavior without external API calls.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from ai.pipelines.inspection_mapping import run_inspection_mapping
from database import SessionLocal
from models.models import Company, Drawing, EvidenceRecord, InspectionRun, Project
from services.storage import StorageService


def _unique_id() -> str:
    """Return a unique string for test isolation (avoid DB collisions across tests)."""
    return uuid.uuid4().hex[:12]


@pytest.fixture
def db() -> Session:
    """Provide a DB session. Rolls back after each test to avoid polluting the database."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def company(db: Session) -> Company:
    """Create a minimal company for project scope."""
    company = Company(name="Test Co", procore_company_id=f"pc-{_unique_id()}")
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@pytest.fixture
def project(db: Session, company: Company) -> Project:
    """Create a minimal project."""
    proj = Project(
        company_id=company.id,
        name="Test Project",
        procore_project_id=f"pp-{_unique_id()}",
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return proj


@pytest.fixture
def master_drawing(db: Session, project: Project) -> Drawing:
    """Create a master drawing (no storage_key to avoid file resolution)."""
    drawing = Drawing(
        project_id=project.id,
        source="upload",
        name="master.pdf",
        storage_key=None,  # avoid get_file_path; pipeline handles None
        content_type="application/pdf",
    )
    db.add(drawing)
    db.commit()
    db.refresh(drawing)
    return drawing


@pytest.fixture
def evidence_record(db: Session, project: Project) -> EvidenceRecord:
    """Create evidence with trade for lookup (no LLM needed for type)."""
    evidence = EvidenceRecord(
        project_id=project.id,
        type="inspection_doc",
        title="HVAC Inspection Report",
        trade="hvac",
        spec_section="15830 - HVAC Controls",
        storage_key=None,
        content_type="application/pdf",
        text_content="All units passed inspection.",
    )
    db.add(evidence)
    db.commit()
    db.refresh(evidence)
    return evidence


@pytest.fixture
def inspection_run(
    db: Session,
    project: Project,
    master_drawing: Drawing,
    evidence_record: EvidenceRecord,
) -> InspectionRun:
    """Create an inspection run in queued status."""
    storage = StorageService(db)
    run = storage.create_inspection_run(
        project_id=project.id,
        master_drawing_id=master_drawing.id,
        evidence_id=evidence_record.id,
        inspection_type=None,
    )
    return run


@patch("ai.pipelines.inspection_mapping._extract_outcomes_llm")
@patch("ai.pipelines.inspection_mapping._classify_inspection_type_llm")
def test_run_inspection_mapping_complete_success(
    mock_classify_llm: object,
    mock_extract_llm: object,
    db: Session,
    project: Project,
    master_drawing: Drawing,
    evidence_record: EvidenceRecord,
    inspection_run: InspectionRun,
) -> None:
    """
    Pipeline runs to completion when evidence has trade (lookup) and LLM returns pass.
    - Inspection type from trade lookup (hvac)
    - Outcome from mocked LLM (pass)
    - Overlay created with unmapped geometry (no region in evidence meta)
    - No finding (outcome is pass)
    - Run status = complete
    """
    # Trade lookup will find "hvac" from evidence.trade; LLM not called for type
    mock_extract_llm.return_value = ("pass", "All units passed.")

    ctx = run_inspection_mapping(db, inspection_run)

    assert ctx.get("error") is None
    assert ctx["inspection_type"] == "hvac"
    assert ctx["inspection_result"] is not None
    assert getattr(ctx["inspection_result"], "outcome", None) == "pass"
    assert len(ctx["drawing_overlays"]) >= 1
    assert ctx["finding"] is None

    # Run should be complete
    db.refresh(inspection_run)
    assert getattr(inspection_run, "status", None) == "complete"
    assert getattr(inspection_run, "inspection_type", None) == "hvac"


@patch("ai.pipelines.inspection_mapping._extract_outcomes_llm")
@patch("ai.pipelines.inspection_mapping._classify_inspection_type_llm")
@patch("ai.pipelines.inspection_mapping._lookup_inspection_type_from_evidence")
def test_run_inspection_mapping_llm_classify_when_no_lookup(
    mock_lookup: object,
    mock_classify_llm: object,
    mock_extract_llm: object,
    db: Session,
    project: Project,
    master_drawing: Drawing,
    evidence_record: EvidenceRecord,
    inspection_run: InspectionRun,
) -> None:
    """
    When lookup returns None, LLM is used for inspection type classification.
    """
    mock_lookup.return_value = None
    mock_classify_llm.return_value = "electrical"
    mock_extract_llm.return_value = ("pass", "OK")

    ctx = run_inspection_mapping(db, inspection_run)

    assert ctx.get("error") is None
    assert ctx["inspection_type"] == "electrical"
    mock_classify_llm.assert_called_once()


@patch("ai.pipelines.inspection_mapping._extract_outcomes_llm")
@patch("ai.pipelines.inspection_mapping._classify_inspection_type_llm")
def test_run_inspection_mapping_fail_creates_finding(
    mock_classify_llm: object,
    mock_extract_llm: object,
    db: Session,
    project: Project,
    master_drawing: Drawing,
    evidence_record: EvidenceRecord,
    inspection_run: InspectionRun,
) -> None:
    """
    When outcome is fail, a finding is created and attached to overlays.
    """
    mock_extract_llm.return_value = ("fail", "Critical defect found.")

    ctx = run_inspection_mapping(db, inspection_run)

    assert ctx.get("error") is None
    assert ctx["inspection_result"] is not None
    assert getattr(ctx["inspection_result"], "outcome", None) == "fail"
    assert ctx["finding"] is not None
    assert len(ctx["drawing_overlays"]) >= 1


@patch("ai.pipelines.inspection_mapping._load_evidence_and_master")
@patch("ai.pipelines.inspection_mapping._extract_outcomes_llm")
@patch("ai.pipelines.inspection_mapping._classify_inspection_type_llm")
def test_run_inspection_mapping_master_drawing_not_found(
    mock_classify_llm: object,
    mock_extract_llm: object,
    mock_load: object,
    db: Session,
    project: Project,
    master_drawing: Drawing,
) -> None:
    """
    When master drawing is missing (Step 1 returns error), pipeline marks run failed.
    Uses patch to simulate load failure (FK prevents creating run with invalid drawing_id).
    """
    mock_load.return_value = {
        "run": None,
        "error": "Master drawing not found",
    }
    storage = StorageService(db)
    run = storage.create_inspection_run(
        project_id=project.id,
        master_drawing_id=master_drawing.id,
        evidence_id=None,
    )
    mock_load.return_value = {
        "run": run,
        "error": "Master drawing not found",
    }

    ctx = run_inspection_mapping(db, run)

    assert ctx.get("error") == "Master drawing not found"
    db.refresh(run)
    assert getattr(run, "status", None) == "failed"
    assert getattr(run, "error_message", None) == "Master drawing not found"


@patch("ai.pipelines.inspection_mapping._extract_outcomes_llm")
@patch("ai.pipelines.inspection_mapping._classify_inspection_type_llm")
def test_run_inspection_mapping_no_evidence_uses_unknown(
    mock_classify_llm: object,
    mock_extract_llm: object,
    db: Session,
    project: Project,
    master_drawing: Drawing,
) -> None:
    """
    When no evidence is linked, outcome is unknown and inspection_type is unknown.
    """
    storage = StorageService(db)
    run = storage.create_inspection_run(
        project_id=project.id,
        master_drawing_id=master_drawing.id,
        evidence_id=None,
    )

    ctx = run_inspection_mapping(db, run)

    assert ctx.get("error") is None
    assert ctx["inspection_type"] == "unknown"
    assert ctx["inspection_result"] is not None
    assert getattr(ctx["inspection_result"], "outcome", None) == "unknown"
    assert getattr(ctx["inspection_result"], "notes", None) == "No evidence document linked"
