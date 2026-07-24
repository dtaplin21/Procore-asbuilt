"""Tests for evidence upload document extraction integration."""

from __future__ import annotations

import uuid
from io import BytesIO
from typing import cast
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ai.pipelines import document_text_extraction as dte
from ai.pipelines.document_text_extraction import (
    BoundingBox,
    ExtractedDocument,
    PositionedWord,
    SourceFormat,
)
from ai.schemas.document_extraction_schemas import (
    DocumentClassification,
    DocumentType,
    InspectionReportFields,
    UniversalFields,
)
from models.document_clue import DocumentClue
from models.document_extraction import DocumentExtraction
from models.models import Company, JobQueue, Project, User, UserCompany
from services.evidence_document_extraction import (
    InspectionMatchEnqueueContext,
    extract_evidence_file_content,
    ingest_evidence_document_extraction,
)
from services.inspection_matching_jobs import (
    JOB_TYPE_INSPECTION_MATCH,
    maybe_enqueue_inspection_match_job,
)
from services.storage import StorageService


def _upload_url(project_id: int, run_id: int) -> str:
    return f"/api/projects/{project_id}/inspections/runs/{run_id}/evidence"


def _insert_region(
    storage: StorageService,
    master_drawing_id: int,
    label: str,
    *,
    inspection_type_tags: list[str] | None = None,
    location_tags: list[str] | None = None,
) -> None:
    storage.create_drawing_region(
        master_drawing_id,
        label=label,
        geometry={"type": "rect", "x": 0.05, "y": 0.06, "width": 0.08, "height": 0.09},
        inspection_type_tags=inspection_type_tags,
        location_tags=location_tags,
    )


@pytest.fixture
def evidence_upload_setup(
    db_session: Session,
    project,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    from models.models import Drawing
    from services import evidence_file_storage

    monkeypatch.setattr(evidence_file_storage, "EVIDENCE_STORAGE_ROOT", tmp_path)

    user = User(email=f"test-{uuid.uuid4().hex[:8]}@example.com")
    db_session.add(user)
    db_session.flush()
    db_session.add(UserCompany(user_id=user.id, company_id=project.company_id))
    db_session.commit()

    drawing = Drawing(
        project_id=project.id,
        source="upload",
        name="master.pdf",
        storage_key=None,
        content_type="application/pdf",
    )
    db_session.add(drawing)
    db_session.commit()
    db_session.refresh(drawing)

    storage = StorageService(db_session)
    run = storage.create_inspection_run(
        project_id=cast(int, project.id),
        master_drawing_id=cast(int, drawing.id),
        evidence_id=None,
        inspection_type="fire_protection",
    )
    return project, drawing, run, storage, db_session


def _word(text: str, x: float = 0.0) -> PositionedWord:
    return PositionedWord(
        text=text,
        bbox=BoundingBox(
            x=x,
            y=100,
            width=10 * len(text),
            height=14,
            page_width=1000,
            page_height=1000,
        ),
        page_index=0,
    )


def _patch_pdf_text(monkeypatch: pytest.MonkeyPatch, words: list[str]) -> None:
    positioned = [_word(word, x=idx * 50.0) for idx, word in enumerate(words)]
    fake_doc = ExtractedDocument(
        source_format=SourceFormat.NATIVE_PDF,
        page_count=1,
        words=positioned,
    )
    monkeypatch.setattr(dte, "_pdf_has_text_layer", lambda p: True)
    monkeypatch.setattr(dte, "_pdf_text_layer", lambda p: fake_doc)


@patch("services.evidence_document_extraction.run_document_extraction")
def test_ingest_evidence_document_extraction_persists_text_and_runs_orchestrator(
    mock_run,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    file_path = tmp_path / "report.pdf"
    file_path.write_bytes(b"%PDF-1.4")
    _patch_pdf_text(
        monkeypatch,
        ["COLO", "33-Sanitary", "Sewerage", "Underground", "Sanitary", "Sewer"],
    )

    company = Company(name=f"Co {uuid.uuid4().hex[:8]}", procore_company_id=f"pc-{uuid.uuid4().hex[:8]}")
    db_session.add(company)
    db_session.flush()

    project = Project(
        company_id=company.id,
        procore_project_id=f"pp-{uuid.uuid4().hex[:8]}",
        name="Test",
    )
    db_session.add(project)
    db_session.flush()

    storage = StorageService(db_session)
    evidence = storage.create_evidence_record(
        project_id=cast(int, project.id),
        type="inspection_doc",
        trade=None,
        spec_section=None,
        title="UCSF Report",
        storage_key="evidence/report.pdf",
        content_type="application/pdf",
    )

    content = extract_evidence_file_content(file_path)
    assert "COLO" in content
    assert "Sewerage" in content

    mock_run.return_value = DocumentExtraction(
        file_id=str(evidence.id),
        document_type=DocumentType.INSPECTION_REPORT.value,
        classification_confidence=0.9,
    )

    ingest_evidence_document_extraction(
        db_session,
        evidence_id=cast(int, evidence.id),
        file_path=file_path,
    )

    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["file_id"] == str(evidence.id)
    assert "COLO" in call_kwargs["content"]
    assert "Sewerage" in call_kwargs["content"]

    db_session.refresh(evidence)
    assert cast(str | None, evidence.text_content) is not None
    assert "COLO" in cast(str, evidence.text_content)


@patch("ai.pipelines.document_extraction_orchestrator.extract_type_specific_fields")
@patch("ai.pipelines.document_extraction_orchestrator.extract_universal_fields")
@patch("ai.pipelines.document_extraction_orchestrator.classify_document")
def test_upload_inspection_run_evidence_triggers_document_extraction(
    mock_classify,
    mock_universal,
    mock_type_specific,
    client: TestClient,
    evidence_upload_setup,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, master_drawing, run, storage, db_session = evidence_upload_setup
    master_id = cast(int, master_drawing.id)

    _insert_region(
        storage,
        master_id,
        "Colo Parking",
        inspection_type_tags=["Underground Sanitary Sewer #1"],
        location_tags=["COLO"],
    )

    _patch_pdf_text(
        monkeypatch,
        [
            "COLO",
            "33-Sanitary",
            "Sewerage",
            "Underground",
            "Sanitary",
            "Sewer",
            "at",
            "COLO",
        ],
    )

    mock_classify.return_value = DocumentClassification(
        document_type=DocumentType.INSPECTION_REPORT,
        confidence=0.91,
    )
    mock_universal.return_value = UniversalFields(
        location_text="COLO",
        trade="33-Sanitary Sewerage",
    )
    mock_type_specific.return_value = InspectionReportFields(
        inspection_name="Underground Sanitary Sewer #1",
    )

    response = client.post(
        _upload_url(cast(int, project.id), cast(int, run.id)),
        files={
            "file": (
                "ucsf-report.pdf",
                BytesIO(b"%PDF-1.4 fake pdf bytes"),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 200
    evidence_id = response.json()["evidence_id"]

    extraction = (
        db_session.query(DocumentExtraction)
        .filter_by(file_id=str(evidence_id))
        .order_by(DocumentExtraction.created_at.desc())
        .first()
    )
    assert extraction is not None

    clues = (
        db_session.query(DocumentClue)
        .filter_by(document_extraction_id=cast(int, extraction.id))
        .all()
    )
    values = {cast(str, clue.clue_value) for clue in clues}
    assert "COLO" in values
    assert "33-Sanitary Sewerage" in values

    job = (
        db_session.query(JobQueue)
        .filter(JobQueue.job_type == JOB_TYPE_INSPECTION_MATCH)
        .order_by(JobQueue.id.desc())
        .first()
    )
    assert job is not None
    input_data = cast(dict, job.input_data)
    assert input_data["inspection_id"] == str(evidence_id)
    assert input_data["drawing_id"] == str(master_id)
    assert input_data["page"] == 1
    assert input_data["inspection_run_id"] == cast(int, run.id)


def test_maybe_enqueue_inspection_match_job_skips_without_master_drawing(
    db_session: Session,
    project,
) -> None:
    job = maybe_enqueue_inspection_match_job(
        db_session,
        project_id=cast(int, project.id),
        inspection_id="123",
        master_drawing_id=None,
    )
    assert job is None


@patch("services.evidence_document_extraction.run_document_extraction")
def test_ingest_without_match_context_does_not_enqueue(
    mock_run,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    project,
) -> None:
    file_path = tmp_path / "report.pdf"
    file_path.write_bytes(b"%PDF-1.4")
    _patch_pdf_text(monkeypatch, ["COLO"])

    storage = StorageService(db_session)
    evidence = storage.create_evidence_record(
        project_id=cast(int, project.id),
        type="inspection_doc",
        trade=None,
        spec_section=None,
        title="Report",
        storage_key="evidence/report.pdf",
        content_type="application/pdf",
    )

    mock_run.return_value = DocumentExtraction(
        file_id=str(evidence.id),
        document_type=DocumentType.INSPECTION_REPORT.value,
        classification_confidence=0.9,
    )

    ingest_evidence_document_extraction(
        db_session,
        evidence_id=cast(int, evidence.id),
        file_path=file_path,
    )

    job_count = (
        db_session.query(JobQueue)
        .filter(JobQueue.job_type == JOB_TYPE_INSPECTION_MATCH)
        .count()
    )
    assert job_count == 0
