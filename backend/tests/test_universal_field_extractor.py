from unittest.mock import patch

from ai.pipelines.universal_field_extractor import (
    _parse_extraction_payload,
    _sanitize_universal_fields_dict,
    extract_universal_fields,
)
from ai.schemas.document_extraction_schemas import UniversalFields

UCSF_REPORT_TEXT = """
Project: UCSF Benioff Oakland
Project Number: 02001.161310
Location: COLO
Trade: 33-Sanitary Sewerage
Inspection: Underground Sanitary Sewer #1
Notes: Sanitary sewer inspection prior to backfill in the Colo parking lot
"""


def test_parse_extraction_payload_ucsf_fields():
    payload = _parse_extraction_payload(
        """{
          "project_name": "UCSF Benioff Oakland",
          "project_number": "02001.161310",
          "location_text": "COLO",
          "trade": "33-Sanitary Sewerage",
          "document_title": "Underground Sanitary Sewer #1",
          "date": null,
          "contractor": null
        }"""
    )

    fields = UniversalFields(**payload)

    assert fields.project_name == "UCSF Benioff Oakland"
    assert fields.project_number == "02001.161310"
    assert fields.location_text == "COLO"
    assert fields.trade == "33-Sanitary Sewerage"
    assert fields.document_title == "Underground Sanitary Sewer #1"
    assert fields.date is None
    assert fields.contractor is None


def test_sanitize_universal_fields_ignores_unknown_keys():
    payload = _sanitize_universal_fields_dict(
        {
            "project_name": "UCSF Benioff Oakland",
            "unexpected": "ignored",
        }
    )

    assert set(payload.keys()) == {
        "project_name",
        "project_number",
        "location_text",
        "date",
        "trade",
        "contractor",
        "document_title",
    }
    assert payload["project_name"] == "UCSF Benioff Oakland"
    assert payload["contractor"] is None


def test_parse_extraction_payload_empty_string_returns_all_none():
    payload = _parse_extraction_payload("")
    fields = UniversalFields(**payload)

    assert fields.project_name is None
    assert fields.project_number is None
    assert fields.location_text is None
    assert fields.date is None
    assert fields.trade is None
    assert fields.contractor is None
    assert fields.document_title is None


@patch("ai.pipelines.universal_field_extractor._call_extraction_llm")
def test_extract_universal_fields_uses_llm_payload(mock_llm):
    mock_llm.return_value = {
        "project_name": "UCSF Benioff Oakland",
        "project_number": "02001.161310",
        "location_text": "COLO",
        "trade": "33-Sanitary Sewerage",
        "document_title": "Underground Sanitary Sewer #1",
        "date": None,
        "contractor": None,
    }

    fields = extract_universal_fields(UCSF_REPORT_TEXT)

    assert fields.project_name == "UCSF Benioff Oakland"
    assert fields.project_number == "02001.161310"
    assert fields.location_text == "COLO"
    assert fields.trade == "33-Sanitary Sewerage"
    assert fields.document_title == "Underground Sanitary Sewer #1"
    mock_llm.assert_called_once_with(UCSF_REPORT_TEXT)


@patch("ai.pipelines.universal_field_extractor._call_extraction_llm")
def test_extract_universal_fields_invalid_payload_returns_empty(mock_llm):
    mock_llm.return_value = {"project_name": {"bad": "shape"}}

    fields = extract_universal_fields("some document")

    assert fields == UniversalFields()
