"""Tests for match-time evidence investigation persistence."""

from __future__ import annotations

import uuid
from typing import cast
from unittest.mock import patch

from sqlalchemy.orm import Session

from ai.agents.tools.pdf_investigation import EvidenceInvestigationPayload
from ai.pipelines.pdf_link_follower import LinkFollowResult
from ai.schemas.document_extraction_schemas import DocumentType
from models.document_extraction import DocumentExtraction
from services.evidence_investigation_persistence import persist_evidence_investigation
from services.storage import StorageService


@patch("services.evidence_investigation_persistence.register_linked_pdfs_as_auxiliary_drawings")
@patch("services.evidence_investigation_persistence.run_document_extraction")
@patch("services.evidence_investigation_persistence.extract_survey_points_from_evidence")
@patch("services.evidence_investigation_persistence.replace_evidence_drawing_links")
def test_persist_evidence_investigation_writes_match_investigation_meta(
    mock_replace_links,
    mock_survey,
    mock_run_extraction,
    mock_register_linked,
    db_session: Session,
    project,
    tmp_path,
) -> None:
    link_result = LinkFollowResult(
        supplemental_text="Location: COLO STA 10+50",
        cross_refs=[{"kind": "pdf_internal_link", "target_page": 2}],
        followed_count=1,
        skipped_count=0,
        errors=[],
    )
    payload = EvidenceInvestigationPayload(
        link_result=link_result,
        merged_text="Location: COLO STA 10+50\nInspection summary",
        base_text="Inspection summary",
        summaries=(),
        links_followed=1,
        pages_rendered=0,
        ocr_word_counts={},
        errors=(),
    )

    mock_register_linked.return_value = [101, 102]
    mock_survey.return_value = ([], None)
    extraction = DocumentExtraction(
        file_id="pending",
        document_type=DocumentType.INSPECTION_REPORT.value,
        classification_confidence=0.9,
    )
    extraction.id = 999
    mock_run_extraction.return_value = extraction

    storage = StorageService(db_session)
    evidence = storage.create_evidence_record(
        project_id=cast(int, project.id),
        type="inspection_doc",
        trade=None,
        spec_section=None,
        title=f"Investigation {uuid.uuid4().hex[:6]}",
        storage_key="evidence/investigation.pdf",
        content_type="application/pdf",
    )
    db_session.flush()
    extraction.file_id = str(evidence.id)

    file_path = tmp_path / "report.pdf"
    file_path.write_bytes(b"%PDF-1.4")

    result = persist_evidence_investigation(
        db_session,
        evidence_id=cast(int, evidence.id),
        file_path=file_path,
        project_id=cast(int, project.id),
        payload=payload,
        text_content_max_chars=None,
    )

    mock_register_linked.assert_called_once()
    register_kwargs = mock_register_linked.call_args.kwargs
    assert register_kwargs["link_result"] is link_result
    assert register_kwargs["project_id"] == cast(int, project.id)
    assert register_kwargs["evidence_id"] == cast(int, evidence.id)

    mock_replace_links.assert_called_once()
    mock_survey.assert_called_once()
    mock_run_extraction.assert_called_once()
    extraction_kwargs = mock_run_extraction.call_args.kwargs
    assert extraction_kwargs["content"] == payload.merged_text
    assert extraction_kwargs["classification_content"] == payload.base_text

    assert result.linked_drawing_ids == [101, 102]
    assert result.survey_point_count == 0
    assert result.extraction_id == 999

    db_session.refresh(evidence)
    meta = cast(dict, evidence.meta)
    investigation = meta.get("matchInvestigation")
    assert investigation is not None
    assert investigation["followed"] == 1
    assert investigation["skipped"] == 0
    assert investigation["linked_drawing_ids"] == [101, 102]
    assert investigation["at"]

    cross_refs = cast(list[dict], evidence.cross_refs_json)
    assert any(ref.get("target_page") == 2 for ref in cross_refs)

    text_content = cast(str, evidence.text_content)
    assert "Location: COLO STA 10+50" in text_content
    assert "Inspection summary" in text_content
