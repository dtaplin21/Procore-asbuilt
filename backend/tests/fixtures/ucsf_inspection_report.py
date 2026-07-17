"""Shared UCSF inspection report fixtures for end-to-end pipeline tests."""

from __future__ import annotations

from ai.schemas.document_extraction_schemas import (
    DocumentClassification,
    DocumentType,
    InspectionReportFields,
    UniversalFields,
)

UCSF_REPORT_TEXT = """
Project: UCSF Benioff Oakland
Project Number: 02001.161310
Location: COLO
Trade: 33-Sanitary Sewerage
Inspection: Underground Sanitary Sewer #1
Notes: Sanitary sewer inspection prior to backfill in the Colo parking lot
"""

UCSF_CLASSIFICATION = DocumentClassification(
    document_type=DocumentType.INSPECTION_REPORT,
    confidence=0.91,
)

UCSF_UNIVERSAL_FIELDS = UniversalFields(
    project_name="UCSF Benioff Oakland",
    project_number="02001.161310",
    location_text="COLO",
    trade="33-Sanitary Sewerage",
    document_title="Underground Sanitary Sewer #1",
)

UCSF_INSPECTION_FIELDS = InspectionReportFields(
    inspection_name="Underground Sanitary Sewer #1",
    inspection_notes=[
        "Sanitary sewer inspection prior to backfill in the Colo parking lot"
    ],
)

UCSF_EXPECTED_PERSISTED_CLUE_VALUES = {
    "COLO",
    "33-Sanitary Sewerage",
    "Underground Sanitary Sewer #1",
    "Sanitary sewer inspection prior to backfill in the Colo parking lot",
}

UCSF_EXPECTED_SEARCH_TERMS = {
    "colo",
    "33-sanitary sewerage",
    "underground sanitary sewer #1",
    "sanitary sewer inspection prior to backfill in the colo parking lot",
    "sanitary sewer",
    "ss",
    "san",
    "sewer lateral",
    "cleanout",
    "manhole",
    "parking lot",
}
