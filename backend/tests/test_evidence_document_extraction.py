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
from ai.pipelines.pdf_link_follower import LinkFollowResult
from services.evidence_document_extraction import (
    InspectionMatchEnqueueContext,
    extract_evidence_file_content,
    ingest_evidence_document_extraction,
    ingest_evidence_upload_only,
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
        index_status="ready",
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


@patch("services.evidence_document_extraction.maybe_enqueue_inspection_match_after_extraction")
def test_ingest_evidence_upload_only_persists_base_text_without_link_follow(
    mock_enqueue,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    project,
) -> None:
    file_path = tmp_path / "report.pdf"
    file_path.write_bytes(b"%PDF-1.4")
    _patch_pdf_text(monkeypatch, ["COLO", "Sewerage"])

    follow_called = False

    def _fail_if_follow(*_args: object, **_kwargs: object) -> LinkFollowResult:
        nonlocal follow_called
        follow_called = True
        return LinkFollowResult()

    monkeypatch.setattr(
        "services.evidence_document_extraction.follow_pdf_links",
        _fail_if_follow,
    )

    storage = StorageService(db_session)
    evidence = storage.create_evidence_record(
        project_id=cast(int, project.id),
        type="inspection_doc",
        trade=None,
        spec_section=None,
        title="Upload Only",
        storage_key="evidence/upload-only.pdf",
        content_type="application/pdf",
    )

    ok = ingest_evidence_upload_only(
        db_session,
        evidence_id=cast(int, evidence.id),
        file_path=file_path,
        match_context=InspectionMatchEnqueueContext(
            project_id=cast(int, project.id),
            master_drawing_id=1,
            inspection_run_id=99,
        ),
    )

    assert ok is True
    assert follow_called is False
    mock_enqueue.assert_called_once()

    db_session.refresh(evidence)
    text_content = cast(str | None, evidence.text_content)
    assert text_content is not None
    assert "COLO" in text_content
    assert "Sewerage" in text_content


@patch("services.evidence_investigation_persistence.run_document_extraction")
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


@patch("services.evidence_investigation_persistence.run_document_extraction")
@patch("ai.agents.tools.pdf_investigation.follow_and_capture_links")
def test_ingest_merges_pdf_link_supplemental_text_and_cross_refs(
    mock_follow,
    mock_run,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    project,
) -> None:
    file_path = tmp_path / "report.pdf"
    file_path.write_bytes(b"%PDF-1.4")
    _patch_pdf_text(monkeypatch, ["Inspection", "summary"])

    supplemental_block = "\n\n--- Linked content (page 2) ---\nLocation: COLO"
    link_cross_ref = {
        "kind": "pdf_internal_link",
        "source_page": 1,
        "target_page": 2,
        "anchor_text": None,
    }

    mock_follow.return_value = LinkFollowResult(
        supplemental_text=supplemental_block,
        cross_refs=[link_cross_ref],
        followed_count=1,
    )

    storage = StorageService(db_session)
    evidence = storage.create_evidence_record(
        project_id=cast(int, project.id),
        type="inspection_doc",
        trade=None,
        spec_section=None,
        title="Linked Report",
        storage_key="evidence/linked-report.pdf",
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

    mock_run.assert_called_once()
    merged_content = mock_run.call_args.kwargs["content"]
    assert "Inspection summary" in merged_content
    assert supplemental_block.strip() in merged_content
    assert "Location: COLO" in merged_content

    db_session.refresh(evidence)
    text_content = cast(str, evidence.text_content)
    assert supplemental_block.strip() in text_content
    assert "Location: COLO" in text_content

    cross_refs = cast(list[dict], evidence.cross_refs_json)
    assert any(
        ref.get("kind") == "pdf_internal_link" and ref.get("target_page") == 2
        for ref in cross_refs
        if isinstance(ref, dict)
    )


@patch("api.routes.evidence.ingest_evidence_upload_only")
def test_upload_inspection_run_evidence_enqueues_match_without_full_extraction(
    mock_upload_only,
    client: TestClient,
    evidence_upload_setup,
) -> None:
    project, master_drawing, run, _storage, db_session = evidence_upload_setup
    master_id = cast(int, master_drawing.id)

    mock_upload_only.return_value = True

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
    body = response.json()
    assert body["evidence_id"] > 0
    assert body["overlays_created"] == 0
    assert body["overlay_ids"] == []

    mock_upload_only.assert_called_once()
    call_kwargs = mock_upload_only.call_args.kwargs
    assert call_kwargs["match_context"].project_id == cast(int, project.id)
    assert call_kwargs["match_context"].master_drawing_id == master_id
    assert call_kwargs["match_context"].inspection_run_id == cast(int, run.id)

    db_session.refresh(run)
    assert run.status == "processing"

    extraction_for_evidence = (
        db_session.query(DocumentExtraction)
        .filter_by(file_id=str(body["evidence_id"]))
        .count()
    )
    assert extraction_for_evidence == 0


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


@patch("services.evidence_investigation_persistence.run_document_extraction")
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
        .filter(
            JobQueue.job_type == JOB_TYPE_INSPECTION_MATCH,
            JobQueue.project_id == cast(int, project.id),
        )
        .count()
    )
    assert job_count == 0
