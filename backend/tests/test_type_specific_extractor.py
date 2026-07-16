"""Tests for type-specific document field extraction."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import cast
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ai.pipelines.type_specific_extractor import extract_type_specific_fields
from ai.schemas.document_extraction_schemas import (
    DocumentType,
    FieldPhotoFields,
    InspectionReportFields,
    MasterDrawingFields,
)
from database import SessionLocal
from models.review_queue_item import ReviewQueueItem


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


def test_inspection_report_schema_accepts_partial_data():
    fields = InspectionReportFields(inspection_name="Underground Sanitary Sewer #1")

    assert fields.inspection_name == "Underground Sanitary Sewer #1"
    assert fields.items_inspected == []
    assert fields.pass_fail_result is None


def test_inspection_report_schema_rejects_wrong_shape():
    with pytest.raises(ValidationError):
        InspectionReportFields.model_validate({"items_inspected": "not a list"})


def test_unknown_document_type_returns_none_without_llm(db: Session):
    with patch("ai.pipelines.type_specific_extractor._call_extraction_llm") as mock_llm:
        result = extract_type_specific_fields(
            DocumentType.UNKNOWN,
            "some content",
            db,
            _unique_file_id(),
        )

    assert result is None
    mock_llm.assert_not_called()


@patch("ai.pipelines.type_specific_extractor._call_extraction_llm")
def test_extract_inspection_report_fields(mock_llm, db: Session):
    mock_llm.return_value = {
        "inspection_name": "Underground Sanitary Sewer #1",
        "inspection_notes": [
            "Sanitary sewer inspection prior to backfill in the Colo parking lot"
        ],
        "items_inspected": [],
        "assignees": [],
    }

    result = extract_type_specific_fields(
        DocumentType.INSPECTION_REPORT,
        "inspection report text",
        db,
        _unique_file_id(),
    )

    assert isinstance(result, InspectionReportFields)
    assert result.inspection_name == "Underground Sanitary Sewer #1"
    assert len(result.inspection_notes) == 1


@patch("ai.pipelines.type_specific_extractor._call_extraction_llm")
def test_extract_field_photo_fields(mock_llm, db: Session):
    mock_llm.return_value = {
        "visible_objects": ["trench", "pipe"],
        "utility_type": "sanitary sewer",
        "visible_text": [],
        "possible_location_clues": ["parking lot"],
    }

    result = extract_type_specific_fields(
        DocumentType.FIELD_PHOTO,
        "field photo description",
        db,
        _unique_file_id(),
    )

    assert isinstance(result, FieldPhotoFields)
    assert result.utility_type == "sanitary sewer"
    assert "trench" in result.visible_objects


@patch("ai.pipelines.type_specific_extractor._call_extraction_llm")
def test_extract_master_drawing_fields(mock_llm, db: Session):
    mock_llm.return_value = {
        "sheet_number": "U1.C4.31",
        "areas_or_zones": ["COLO parking lot"],
        "drawing_labels": [],
        "utility_symbols": [],
    }

    result = extract_type_specific_fields(
        DocumentType.MASTER_DRAWING,
        "master drawing OCR text",
        db,
        _unique_file_id(),
    )

    assert isinstance(result, MasterDrawingFields)
    assert result.sheet_number == "U1.C4.31"
    assert "COLO parking lot" in result.areas_or_zones


@patch("ai.pipelines.type_specific_extractor._call_extraction_llm")
def test_validation_failure_routes_to_review_queue(mock_llm, db: Session):
    file_id = _unique_file_id()
    mock_llm.return_value = {"items_inspected": "not a list"}

    result = extract_type_specific_fields(
        DocumentType.INSPECTION_REPORT,
        "bad extraction payload",
        db,
        file_id,
    )

    assert result is None

    queued = (
        db.query(ReviewQueueItem)
        .filter_by(file_id=file_id, reason="extraction_validation_failed")
        .one()
    )
    assert cast(str | None, queued.document_type_guess) == DocumentType.INSPECTION_REPORT.value
