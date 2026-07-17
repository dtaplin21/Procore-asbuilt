"""Tests for document extraction orchestrator."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import cast
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from ai.pipelines.document_extraction_orchestrator import run_document_extraction
from ai.schemas.document_extraction_schemas import (
    DocumentClassification,
    DocumentType,
    InspectionReportFields,
    UniversalFields,
)
from database import SessionLocal
from models.document_clue import DocumentClue
from models.document_extraction import DocumentExtraction
from models.review_queue_item import ReviewQueueItem

UCSF_REPORT_TEXT = """
Project: UCSF Benioff Oakland
Project Number: 02001.161310
Location: COLO
Trade: 33-Sanitary Sewerage
Inspection: Underground Sanitary Sewer #1
Notes: Sanitary sewer inspection prior to backfill in the Colo parking lot
"""


def _unique_file_id() -> str:
    return f"evidence-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@patch("ai.pipelines.document_extraction_orchestrator.extract_type_specific_fields")
@patch("ai.pipelines.document_extraction_orchestrator.extract_universal_fields")
@patch("ai.pipelines.document_extraction_orchestrator.classify_document")
def test_run_document_extraction_persists_extraction_and_clues(
    mock_classify,
    mock_universal,
    mock_type_specific,
    db: Session,
):
    file_id = _unique_file_id()
    mock_classify.return_value = DocumentClassification(
        document_type=DocumentType.INSPECTION_REPORT,
        confidence=0.91,
    )
    mock_universal.return_value = UniversalFields(
        project_name="UCSF Benioff Oakland",
        project_number="02001.161310",
        location_text="COLO",
        trade="33-Sanitary Sewerage",
        document_title="Underground Sanitary Sewer #1",
    )
    mock_type_specific.return_value = InspectionReportFields(
        inspection_name="Underground Sanitary Sewer #1",
        inspection_notes=[
            "Sanitary sewer inspection prior to backfill in the Colo parking lot"
        ],
    )

    extraction = run_document_extraction(db, file_id, UCSF_REPORT_TEXT)

    assert extraction.id is not None
    assert cast(str, extraction.file_id) == file_id
    assert cast(str, extraction.document_type) == DocumentType.INSPECTION_REPORT.value
    assert cast(float | None, extraction.classification_confidence) == 0.91

    clues = db.query(DocumentClue).filter_by(
        document_extraction_id=cast(int, extraction.id)
    ).all()
    assert len(clues) >= 3

    values = {cast(str, clue.clue_value) for clue in clues}
    assert "COLO" in values
    assert "33-Sanitary Sewerage" in values
    assert any("sanitary sewer" in value.lower() for value in values)

    stored = db.query(DocumentExtraction).filter_by(id=cast(int, extraction.id)).one()
    assert stored.universal_fields_json is not None
    assert stored.type_specific_fields_json is not None


@patch("ai.pipelines.document_extraction_orchestrator.extract_universal_fields")
@patch("ai.pipelines.document_extraction_orchestrator.classify_document")
def test_run_document_extraction_unknown_classification_queues_review(
    mock_classify,
    mock_universal,
    db: Session,
):
    file_id = _unique_file_id()
    mock_classify.return_value = DocumentClassification(
        document_type=DocumentType.UNKNOWN,
        confidence=0.35,
    )
    mock_universal.return_value = UniversalFields(
        location_text="COLO",
        trade="33-Sanitary Sewerage",
    )

    extraction = run_document_extraction(db, file_id, UCSF_REPORT_TEXT)

    queued = (
        db.query(ReviewQueueItem)
        .filter_by(file_id=file_id, reason="low_confidence_classification")
        .one()
    )
    assert cast(str | None, queued.document_type_guess) == DocumentType.UNKNOWN.value
    assert cast(float | None, queued.classification_confidence) == 0.35
    assert cast(str, extraction.document_type) == DocumentType.UNKNOWN.value

    clues = db.query(DocumentClue).filter_by(
        document_extraction_id=cast(int, extraction.id)
    ).all()
    assert len(clues) == 2
