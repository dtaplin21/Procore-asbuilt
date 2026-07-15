"""Phase 2 — layered document extraction schema tests."""

import pytest
from pydantic import ValidationError

from ai.schemas.document_extraction_schemas import (
    Clue,
    DocumentClassification,
    DocumentType,
    FieldPhotoFields,
    InspectionReportFields,
    MasterDrawingFields,
    TYPE_SPECIFIC_SCHEMAS,
    UniversalFields,
)


def test_import_all_schema_symbols():
    """Plan verification: module imports without error."""
    from ai.schemas.document_extraction_schemas import (  # noqa: F401
        Clue,
        DocumentClassification,
        DocumentType,
        FieldPhotoFields,
        InspectionReportFields,
        MasterDrawingFields,
        TYPE_SPECIFIC_SCHEMAS,
        UniversalFields,
    )


def test_document_type_enum_only_supported_values():
    assert {t.value for t in DocumentType} == {
        "inspection_report",
        "field_photo",
        "master_drawing",
        "unknown",
    }


def test_ucsf_inspection_report_partial_fields_validate():
    """Plan manual example — no validation errors; missing optionals are None/empty."""
    universal = UniversalFields(
        project_name="UCSF Benioff Oakland",
        project_number="02001.161310",
        location_text="COLO",
        trade="33-Sanitary Sewerage",
    )

    inspection = InspectionReportFields(
        inspection_name="Underground Sanitary Sewer #1",
        inspection_notes=[
            "Sanitary sewer inspection prior to backfill in the Colo parking lot"
        ],
    )

    assert universal.project_name == "UCSF Benioff Oakland"
    assert universal.project_number == "02001.161310"
    assert universal.location_text == "COLO"
    assert universal.trade == "33-Sanitary Sewerage"
    assert universal.date is None
    assert universal.contractor is None
    assert universal.document_title is None

    assert inspection.inspection_name == "Underground Sanitary Sewer #1"
    assert len(inspection.inspection_notes) == 1
    assert inspection.items_inspected == []
    assert inspection.pass_fail_result is None
    assert inspection.assignees == []


def test_field_photo_fields_accept_partial_data():
    photo = FieldPhotoFields(
        utility_type="sanitary sewer",
        visible_objects=["trench", "pipe"],
    )

    assert photo.utility_type == "sanitary sewer"
    assert photo.visible_objects == ["trench", "pipe"]
    assert photo.visible_text == []
    assert photo.environment is None
    assert photo.possible_location_clues == []


def test_master_drawing_fields_accept_partial_data():
    drawing = MasterDrawingFields(
        sheet_number="U1.C4.31",
        areas_or_zones=["COLO parking lot"],
    )

    assert drawing.sheet_number == "U1.C4.31"
    assert drawing.areas_or_zones == ["COLO parking lot"]
    assert drawing.drawing_labels == []
    assert drawing.discipline is None


def test_type_specific_schemas_map_supported_document_types():
    assert set(TYPE_SPECIFIC_SCHEMAS.keys()) == {
        DocumentType.INSPECTION_REPORT,
        DocumentType.FIELD_PHOTO,
        DocumentType.MASTER_DRAWING,
    }
    assert TYPE_SPECIFIC_SCHEMAS[DocumentType.INSPECTION_REPORT] is InspectionReportFields
    assert TYPE_SPECIFIC_SCHEMAS[DocumentType.FIELD_PHOTO] is FieldPhotoFields
    assert TYPE_SPECIFIC_SCHEMAS[DocumentType.MASTER_DRAWING] is MasterDrawingFields


def test_document_classification_stores_backend_only_confidence():
    classification = DocumentClassification(
        document_type=DocumentType.INSPECTION_REPORT,
        confidence=0.92,
    )

    assert classification.document_type == DocumentType.INSPECTION_REPORT
    assert classification.confidence == 0.92


def test_clue_defaults_location_relevant_true():
    clue = Clue(
        type="location_text",
        value="COLO",
        source="inspection_report",
        confidence=0.9,
    )

    assert clue.location_relevant is True
    assert clue.value == "COLO"


def test_inspection_report_rejects_wrong_list_shape():
    with pytest.raises(ValidationError):
        InspectionReportFields.model_validate({"items_inspected": "not a list"})


def test_field_photo_rejects_wrong_list_shape():
    with pytest.raises(ValidationError):
        FieldPhotoFields.model_validate({"visible_objects": "trench"})
