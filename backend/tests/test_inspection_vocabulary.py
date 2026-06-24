"""Tests for inspection vocabulary taxonomy."""

from services.inspection_vocabulary import (
    VocabCategory,
    all_categories,
    canonical_terms,
    category_def,
    MatchStrategy,
)


def test_all_categories_covers_vocab_keys() -> None:
    assert len(all_categories()) == len(VocabCategory)


def test_sheet_identifier_uses_pattern_strategy() -> None:
    sheet = category_def(VocabCategory.SHEET_IDENTIFIER)
    assert sheet.strategy == MatchStrategy.PATTERN
    assert len(sheet.patterns) == 1
    assert sheet.terms == ()


def test_canonical_terms_for_inspection_status() -> None:
    terms = canonical_terms(VocabCategory.INSPECTION_STATUS)
    assert "Passed" in terms
    assert "Failed" in terms
