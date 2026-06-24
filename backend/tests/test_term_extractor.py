"""Tests for controlled-vocabulary term extraction."""

from ai.pipelines.term_extractor import (
    ConfidenceLabel,
    extract_by_category,
    extract_terms,
    overall_confidence_label,
)
from services.inspection_vocabulary import VocabCategory


def test_extract_terms_empty_text() -> None:
    assert extract_terms("") == []
    assert extract_terms("   ") == []


def test_phrase_match_with_alias_and_canonical() -> None:
    text = "Rough-In inspection at Mechanical Room — Approved As Noted."
    terms = extract_terms(text)

    inspection_types = [
        t for t in terms if t.category == VocabCategory.INSPECTION_TYPE
    ]
    assert any(t.canonical == "Rough In" for t in inspection_types)

    locations = [t for t in terms if t.category == VocabCategory.LOCATION_TERM]
    assert any(t.canonical == "Mechanical Room" for t in locations)

    statuses = [t for t in terms if t.category == VocabCategory.INSPECTION_STATUS]
    assert any(t.canonical == "Approved As Noted" for t in statuses)


def test_longest_phrase_wins_over_substring() -> None:
    text = "Underground Fire Water Rough In complete."
    terms = extract_terms(
        text, categories=(VocabCategory.INSPECTION_TYPE,)
    )
    canonicals = {t.canonical for t in terms}
    assert "Underground Fire Water Rough In" in canonicals
    assert "Underground" not in canonicals


def test_sheet_identifier_with_drawing_context() -> None:
    text = "See Sheet U1.C4.31 for detail."
    terms = extract_terms(text, categories=(VocabCategory.SHEET_IDENTIFIER,))
    assert len(terms) == 1
    assert terms[0].canonical == "U1.C4.31"
    assert terms[0].confidence_score >= 0.85


def test_sheet_identifier_without_context_is_medium_confidence() -> None:
    text = "Reference U1.C4.31 in notes."
    terms = extract_terms(text, categories=(VocabCategory.SHEET_IDENTIFIER,))
    assert len(terms) == 1
    assert terms[0].confidence_label == ConfidenceLabel.MEDIUM


def test_confidence_label_terms_not_extracted() -> None:
    text = "High Confidence match on Passed status."
    terms = extract_terms(text)
    assert not any(
        t.category == VocabCategory.CONFIDENCE_LABEL for t in terms
    )


def test_extract_by_category_groups_results() -> None:
    grouped = extract_by_category("Passed hydro test in Utility MR.")
    assert "inspection_status" in grouped
    assert "inspection_type" in grouped
    assert grouped["inspection_status"][0].canonical == "Passed"


def test_overall_confidence_label_weakest_link() -> None:
    terms = extract_terms("Site inspection Passed.")
    label = overall_confidence_label(terms)
    assert label in (
        ConfidenceLabel.HIGH,
        ConfidenceLabel.MEDIUM,
        ConfidenceLabel.LOW,
    )
