"""Phase 7 — clue extraction from universal and type-specific fields."""

from ai.pipelines.clue_extractor import build_clues
from ai.schemas.document_extraction_schemas import (
    DocumentType,
    FieldPhotoFields,
    InspectionReportFields,
    MasterDrawingFields,
    UniversalFields,
)


def test_inspection_report_produces_location_trade_and_note_clues():
    universal = UniversalFields(
        location_text="COLO",
        trade="33-Sanitary Sewerage",
        document_title="Underground Sanitary Sewer #1",
    )

    type_specific = InspectionReportFields(
        inspection_name="Underground Sanitary Sewer #1",
        inspection_notes=[
            "Sanitary sewer inspection prior to backfill in the Colo parking lot"
        ],
    )

    clues = build_clues(DocumentType.INSPECTION_REPORT, universal, type_specific)

    clue_types = [c.type for c in clues]
    clue_values = [c.value for c in clues]

    assert "location_text" in clue_types
    assert "trade" in clue_types
    assert "inspection_note" in clue_types
    assert "inspection_name" in clue_types
    assert "document_title" in clue_types
    assert "COLO" in clue_values
    assert "33-Sanitary Sewerage" in clue_values
    assert (
        "Sanitary sewer inspection prior to backfill in the Colo parking lot"
        in clue_values
    )


def test_inspection_report_clues_include_backend_only_confidence():
    universal = UniversalFields(location_text="COLO", trade="33-Sanitary Sewerage")
    type_specific = InspectionReportFields(
        inspection_notes=["Colo parking lot trench inspection"]
    )

    clues = build_clues(DocumentType.INSPECTION_REPORT, universal, type_specific)

    assert all(0.0 < c.confidence <= 1.0 for c in clues)
    location = next(c for c in clues if c.type == "location_text")
    assert location.confidence == 0.90
    assert location.location_relevant is True


def test_contractor_clue_is_not_location_relevant():
    universal = UniversalFields(contractor="ABC Construction")
    clues = build_clues(DocumentType.INSPECTION_REPORT, universal, None)

    contractor = next(c for c in clues if c.type == "contractor")
    assert contractor.location_relevant is False
    assert contractor.confidence == 0.60


def test_field_photo_produces_visible_and_location_clues():
    universal = UniversalFields()
    type_specific = FieldPhotoFields(
        utility_type="sanitary sewer",
        visible_objects=["trench", "pipe"],
        visible_text=["SS"],
        possible_location_clues=["parking lot", "utility trench"],
    )

    clues = build_clues(DocumentType.FIELD_PHOTO, universal, type_specific)
    clue_types = [c.type for c in clues]

    assert "utility_type" in clue_types
    assert "visible_object" in clue_types
    assert "visible_text" in clue_types
    assert "location_hint" in clue_types
    assert all(c.source == "field_photo" for c in clues if c.type != "contractor")


def test_master_drawing_area_clues_are_location_relevant():
    universal = UniversalFields()
    type_specific = MasterDrawingFields(
        drawing_labels=["SAN"],
        utility_symbols=["MH"],
        areas_or_zones=["COLO parking lot"],
    )

    clues = build_clues(DocumentType.MASTER_DRAWING, universal, type_specific)

    area = next(c for c in clues if c.type == "area_or_zone")
    label = next(c for c in clues if c.type == "drawing_label")
    symbol = next(c for c in clues if c.type == "utility_symbol")

    assert area.location_relevant is True
    assert area.value == "COLO parking lot"
    assert label.location_relevant is False
    assert symbol.location_relevant is False


def test_unknown_type_still_emits_universal_clues():
    universal = UniversalFields(location_text="COLO", trade="33-Sanitary Sewerage")

    clues = build_clues(DocumentType.UNKNOWN, universal, None)

    assert len(clues) == 2
    assert {c.type for c in clues} == {"location_text", "trade"}
    assert all(c.source == DocumentType.UNKNOWN.value for c in clues)
