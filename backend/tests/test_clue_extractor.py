from ai.pipelines.clue_extractor import build_clues
from ai.schemas.document_extraction_schemas import (
    DocumentType,
    InspectionReportFields,
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
    assert "COLO" in clue_values
