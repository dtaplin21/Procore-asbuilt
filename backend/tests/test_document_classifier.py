from unittest.mock import patch

from ai.pipelines.document_classifier import (
    CLASSIFICATION_CONFIDENCE_THRESHOLD,
    classify_document,
    normalize_classification,
    _parse_classifier_payload,
)
from ai.schemas.document_extraction_schemas import DocumentClassification, DocumentType


def test_low_confidence_should_be_forced_to_unknown():
    raw = {"document_type": "inspection_report", "confidence": 0.4}
    classification = DocumentClassification(**raw)

    result = normalize_classification(classification)

    assert result.document_type == DocumentType.UNKNOWN
    assert result.confidence == 0.4


def test_high_confidence_preserves_document_type():
    classification = DocumentClassification(
        document_type=DocumentType.INSPECTION_REPORT,
        confidence=0.85,
    )

    result = normalize_classification(classification)

    assert result.document_type == DocumentType.INSPECTION_REPORT
    assert result.confidence == 0.85


def test_threshold_boundary_is_inclusive_for_unknown():
    at_threshold = DocumentClassification(
        document_type=DocumentType.FIELD_PHOTO,
        confidence=CLASSIFICATION_CONFIDENCE_THRESHOLD,
    )

    result = normalize_classification(at_threshold)

    assert result.document_type == DocumentType.FIELD_PHOTO


def test_parse_classifier_payload_from_json_block():
    payload = _parse_classifier_payload(
        '```json\n{"document_type": "master_drawing", "confidence": 0.91}\n```'
    )

    assert payload == {"document_type": "master_drawing", "confidence": 0.91}


def test_parse_classifier_payload_invalid_type_becomes_unknown():
    payload = _parse_classifier_payload(
        '{"document_type": "submittal", "confidence": 0.95}'
    )

    assert payload["document_type"] == DocumentType.UNKNOWN.value


@patch("ai.pipelines.document_classifier._call_classifier_llm")
def test_classify_document_applies_low_confidence_fallback(mock_llm):
    mock_llm.return_value = {"document_type": "inspection_report", "confidence": 0.35}

    result = classify_document("Underground sanitary sewer inspection at COLO")

    assert result.document_type == DocumentType.UNKNOWN
    assert result.confidence == 0.35
    mock_llm.assert_called_once()


@patch("ai.pipelines.document_classifier._call_classifier_llm")
def test_classify_document_keeps_high_confidence_type(mock_llm):
    mock_llm.return_value = {"document_type": "inspection_report", "confidence": 0.82}

    result = classify_document("Inspection report for sanitary sewer #1")

    assert result.document_type == DocumentType.INSPECTION_REPORT
    assert result.confidence == 0.82
