"""Tests for match-time evidence investigation persistence."""

from __future__ import annotations

import uuid
from typing import cast
from unittest.mock import patch

from sqlalchemy.orm import Session

from ai.agents.tools.pdf_investigation import EvidenceInvestigationPayload
from ai.pipelines.pdf_link_follower import LinkFollowResult
from ai.pipelines.survey_point_extractor import SurveyPointRecord
from ai.schemas.document_extraction_schemas import DocumentType
from ai.pipelines.station_range_extractor import StationRangeResult
from models.document_extraction import DocumentExtraction
from models.models import Drawing
from services.evidence_investigation_persistence import persist_evidence_investigation
from services.storage import StorageService


@patch("services.evidence_investigation_persistence.extract_station_range_for_drawings")
@patch("services.evidence_investigation_persistence.register_linked_pdfs_as_auxiliary_drawings")
@patch("services.evidence_investigation_persistence.run_document_extraction")
@patch("services.evidence_investigation_persistence.extract_survey_points_from_evidence")
@patch("services.evidence_investigation_persistence.replace_evidence_drawing_links")
def test_persist_evidence_investigation_writes_match_investigation_meta(
    mock_replace_links,
    mock_survey,
    mock_run_extraction,
    mock_register_linked,
    mock_station_range,
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
    mock_station_range.return_value = StationRangeResult(station_from=None, station_to=None)
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


@patch("services.evidence_investigation_persistence.classify_and_persist_evidence_kind")
@patch("services.evidence_investigation_persistence.extract_station_range_for_drawings")
@patch("services.evidence_investigation_persistence.register_linked_pdfs_as_auxiliary_drawings")
@patch("services.evidence_investigation_persistence.run_document_extraction")
@patch("services.evidence_investigation_persistence.extract_survey_points_from_evidence")
@patch("services.evidence_investigation_persistence.replace_evidence_drawing_links")
def test_persist_evidence_investigation_preserves_survey_points_in_meta(
    mock_replace_links,
    mock_survey,
    mock_run_extraction,
    mock_register_linked,
    mock_station_range,
    mock_classify_kind,
    db_session: Session,
    project,
    tmp_path,
) -> None:
    survey_point = SurveyPointRecord(
        page=1,
        northing=2131764.84,
        easting=6051541.82,
        station="11+14.23",
        structure_label=None,
        label_bbox_json={"x": 0.1, "y": 0.2, "width": 0.05, "height": 0.02},
        northing_bbox_json=None,
        easting_bbox_json=None,
        ocr_confidence=0.9,
        meta_json={"scale_source": "evidence_text_fallback"},
    )
    link_result = LinkFollowResult(
        supplemental_text="N 2131764.84 E 6051541.82",
        cross_refs=[],
        followed_count=1,
        skipped_count=0,
        errors=[],
    )
    payload = EvidenceInvestigationPayload(
        link_result=link_result,
        merged_text="N 2131764.84 E 6051541.82",
        base_text="",
        summaries=(),
        links_followed=1,
        pages_rendered=0,
        ocr_word_counts={},
        errors=(),
    )

    mock_register_linked.return_value = [1084]
    mock_station_range.return_value = StationRangeResult(station_from=None, station_to=None)
    mock_survey.return_value = ([survey_point], None)
    extraction = DocumentExtraction(
        file_id="pending",
        document_type=DocumentType.INSPECTION_REPORT.value,
        classification_confidence=0.9,
    )
    db_session.add(extraction)
    db_session.flush()
    mock_run_extraction.return_value = extraction

    storage = StorageService(db_session)
    evidence = storage.create_evidence_record(
        project_id=cast(int, project.id),
        type="inspection_doc",
        trade=None,
        spec_section=None,
        title=f"Survey meta {uuid.uuid4().hex[:6]}",
        storage_key="evidence/survey.pdf",
        content_type="application/pdf",
    )
    db_session.flush()

    file_path = tmp_path / "report.pdf"
    file_path.write_bytes(b"%PDF-1.4")

    persist_evidence_investigation(
        db_session,
        evidence_id=cast(int, evidence.id),
        file_path=file_path,
        project_id=cast(int, project.id),
        payload=payload,
        text_content_max_chars=None,
    )

    db_session.refresh(evidence)
    meta = cast(dict, evidence.meta)
    assert meta.get("matchInvestigation") is not None
    raw_points = meta.get("survey_points")
    assert isinstance(raw_points, list)
    assert len(raw_points) == 1
    assert raw_points[0]["northing"] == 2131764.84
    assert raw_points[0]["easting"] == 6051541.82


@patch("services.evidence_investigation_persistence.classify_and_persist_evidence_kind")
@patch("services.evidence_investigation_persistence.register_linked_pdfs_as_auxiliary_drawings")
@patch("services.evidence_investigation_persistence.run_document_extraction")
@patch("services.evidence_investigation_persistence.extract_survey_points_from_evidence")
@patch("services.evidence_investigation_persistence.replace_evidence_drawing_links")
@patch("services.evidence_investigation_persistence.enqueue_linked_drawing_index_jobs")
def test_persist_evidence_investigation_persists_aux_station_range(
    mock_enqueue_index,
    mock_replace_links,
    mock_survey,
    mock_run_extraction,
    mock_register_linked,
    mock_classify_kind,
    db_session: Session,
    project,
    tmp_path,
) -> None:
    from models.document_clue import DocumentClue
    from models.drawing_text_element import DrawingTextElement

    aux = Drawing(
        project_id=project.id,
        source="linked_evidence",
        name="c4-20.pdf",
        storage_key=f"linked/{uuid.uuid4().hex[:8]}.pdf",
        content_type="application/pdf",
        processing_status="ready",
        index_status="ready",
    )
    db_session.add(aux)
    db_session.flush()
    aux_id = cast(int, aux.id)

    db_session.add_all(
        [
            DrawingTextElement(
                master_drawing_id=aux_id,
                page=1,
                text="SAN STA 10+00",
                text_normalized="san sta 10+00",
                bbox_json={"x0": 0.08, "y0": 0.18, "x1": 0.12, "y1": 0.22},
                source="tesseract",
            ),
            DrawingTextElement(
                master_drawing_id=aux_id,
                page=1,
                text="10+90.95",
                text_normalized="10+90.95",
                bbox_json={"x0": 0.27, "y0": 0.26, "x1": 0.31, "y1": 0.28},
                source="tesseract",
            ),
            DrawingTextElement(
                master_drawing_id=aux_id,
                page=1,
                text="10+00",
                text_normalized="10+00",
                bbox_json={"x0": 0.08, "y0": 0.94, "x1": 0.12, "y1": 0.96},
                source="tesseract",
            ),
        ]
    )
    db_session.commit()

    link_result = LinkFollowResult(
        supplemental_text="7/20-7/24 Trench and Install Sanitary Sewer Lines",
        cross_refs=[],
        followed_count=1,
        skipped_count=0,
        errors=[],
    )
    payload = EvidenceInvestigationPayload(
        link_result=link_result,
        merged_text="7/20-7/24 Trench and Install Sanitary Sewer Lines",
        base_text="",
        summaries=(),
        links_followed=1,
        pages_rendered=0,
        ocr_word_counts={},
        errors=(),
    )

    mock_register_linked.return_value = [aux_id]
    mock_enqueue_index.return_value = []
    mock_survey.return_value = ([], None)
    extraction = DocumentExtraction(
        file_id="pending",
        document_type=DocumentType.INSPECTION_REPORT.value,
        classification_confidence=0.9,
    )
    db_session.add(extraction)
    db_session.flush()
    extraction_id = cast(int, extraction.id)
    mock_run_extraction.return_value = extraction

    storage = StorageService(db_session)
    evidence = storage.create_evidence_record(
        project_id=cast(int, project.id),
        type="inspection_doc",
        trade=None,
        spec_section=None,
        title=f"Station range {uuid.uuid4().hex[:6]}",
        storage_key="evidence/station-range.pdf",
        content_type="application/pdf",
    )
    db_session.flush()
    extraction.file_id = str(evidence.id)

    file_path = tmp_path / "report.pdf"
    file_path.write_bytes(b"%PDF-1.4")

    persist_evidence_investigation(
        db_session,
        evidence_id=cast(int, evidence.id),
        file_path=file_path,
        project_id=cast(int, project.id),
        payload=payload,
        text_content_max_chars=None,
    )

    db_session.refresh(evidence)
    meta = cast(dict, evidence.meta)
    assert meta["station_from"] == "10+00"
    assert meta["station_to"] == "10+90.95"
    assert meta["station_range_source_drawing_id"] == aux_id

    clues = (
        db_session.query(DocumentClue)
        .filter(DocumentClue.document_extraction_id == extraction_id)
        .order_by(DocumentClue.clue_type.asc())
        .all()
    )
    assert [(clue.clue_type, clue.clue_value, clue.source) for clue in clues] == [
        ("station_from", "10+00", "aux_station_ocr"),
        ("station_to", "10+90.95", "aux_station_ocr"),
    ]


def test_enqueue_linked_drawing_index_jobs_enqueues_render_for_unprocessed_drawing(
    db_session: Session,
    project,
) -> None:
    from models.models import JobQueue
    from services.drawing_render_jobs import DRAWING_RENDER_JOB_TYPE
    from services.evidence_investigation_persistence import enqueue_linked_drawing_index_jobs

    aux = Drawing(
        project_id=project.id,
        source="linked_evidence",
        name="Install.pdf",
        storage_key=f"linked/{uuid.uuid4().hex[:8]}.pdf",
        content_type="application/pdf",
        processing_status="pending",
        index_status="pending",
    )
    db_session.add(aux)
    db_session.commit()

    needing = enqueue_linked_drawing_index_jobs(
        db_session,
        project_id=cast(int, project.id),
        linked_drawing_ids=[cast(int, aux.id)],
    )

    assert needing == [cast(int, aux.id)]
    render_jobs = (
        db_session.query(JobQueue)
        .filter(
            JobQueue.project_id == project.id,
            JobQueue.job_type == DRAWING_RENDER_JOB_TYPE,
        )
        .count()
    )
    assert render_jobs == 1
