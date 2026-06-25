"""Tests for ai.pipelines.date_extractor."""

from __future__ import annotations

from datetime import date

import pytest

from ai.pipelines.date_extractor import extract_inspection_date, extract_primary_date
from ai.pipelines.document_text_extraction import (
    BoundingBox,
    ExtractedDocument,
    PositionedWord,
    SourceFormat,
)


def _doc(*words: str) -> ExtractedDocument:
    positioned = [
        PositionedWord(
            text=w,
            bbox=BoundingBox(
                x=i * 80,
                y=100,
                width=10 * len(w),
                height=14,
                page_width=1000,
                page_height=1000,
            ),
            page_index=0,
        )
        for i, w in enumerate(words)
    ]
    return ExtractedDocument(
        source_format=SourceFormat.NATIVE_PDF,
        page_count=1,
        words=positioned,
    )


class TestExtractInspectionDateSlashFormat:
    def test_inspection_date_label_with_slash_date(self) -> None:
        result = extract_inspection_date("Inspection date: 06/24/2026 Final Roof")
        assert result == date(2026, 6, 24)

    def test_inspection_date_label_without_colon(self) -> None:
        result = extract_inspection_date("Inspection date 03/15/2025 approved")
        assert result == date(2025, 3, 15)

    def test_date_label_with_slash_date(self) -> None:
        result = extract_inspection_date("Some header. Date: 12/01/2024 status")
        assert result == date(2024, 12, 1)

    def test_single_digit_month_and_day(self) -> None:
        result = extract_inspection_date("Inspection date: 6/4/2026")
        assert result == date(2026, 6, 4)


class TestExtractInspectionDateIsoFormat:
    def test_inspection_date_label_with_iso_date(self) -> None:
        result = extract_inspection_date("Inspection date: 2020-01-15 Final Roof")
        assert result == date(2020, 1, 15)

    def test_date_of_inspection_anchor(self) -> None:
        result = extract_inspection_date("Date of inspection 2024-11-30")
        assert result == date(2024, 11, 30)

    def test_inspected_on_anchor(self) -> None:
        result = extract_inspection_date("Inspected on: 2023-07-04")
        assert result == date(2023, 7, 4)


class TestExtractInspectionDateFromDocument:
    def test_reads_from_extracted_document_words(self) -> None:
        doc = _doc("Inspection", "date:", "06/24/2026", "Final", "Roof")
        assert extract_inspection_date(doc) == date(2026, 6, 24)

    def test_multipage_uses_full_text(self) -> None:
        doc = ExtractedDocument(
            source_format=SourceFormat.NATIVE_PDF,
            page_count=2,
            words=[
                PositionedWord(
                    text="Inspection",
                    bbox=BoundingBox(0, 0, 10, 10, 100, 100),
                    page_index=1,
                ),
                PositionedWord(
                    text="date:",
                    bbox=BoundingBox(20, 0, 10, 10, 100, 100),
                    page_index=1,
                ),
                PositionedWord(
                    text="2021-05-20",
                    bbox=BoundingBox(40, 0, 10, 10, 100, 100),
                    page_index=1,
                ),
            ],
        )
        assert extract_inspection_date(doc) == date(2021, 5, 20)


class TestExtractInspectionDateNone:
    def test_empty_string(self) -> None:
        assert extract_inspection_date("") is None

    def test_whitespace_only(self) -> None:
        assert extract_inspection_date("   \n  ") is None

    def test_no_date_in_text(self) -> None:
        assert extract_inspection_date("Final inspection Roof Approved") is None

    def test_unanchored_bare_date_falls_back_to_first_date(self) -> None:
        assert extract_inspection_date("Report generated 06/24/2026") == date(2026, 6, 24)


class TestExtractInspectionDateValidation:
    def test_invalid_slash_date_returns_none(self) -> None:
        assert extract_inspection_date("Inspection date: 02/30/2026") is None

    def test_invalid_iso_date_returns_none(self) -> None:
        assert extract_inspection_date("Inspection date: 2026-13-01") is None

    def test_prefers_first_anchored_date(self) -> None:
        text = "Inspection date: 01/02/2023 and Date: 03/04/2024"
        assert extract_inspection_date(text) == date(2023, 1, 2)

    def test_iso_preferred_over_slash_when_both_follow_anchor(self) -> None:
        text = "Inspection date: 2022-06-01 / 06/02/2022"
        assert extract_inspection_date(text) == date(2022, 6, 1)


class TestExtractInspectionDateAnchors:
    def test_inspection_on_anchor(self) -> None:
        assert extract_inspection_date("Inspection on 09/09/2025") == date(2025, 9, 9)

    def test_case_insensitive_anchor(self) -> None:
        assert extract_inspection_date("INSPECTION DATE: 04/05/2024") == date(2024, 4, 5)

    def test_hyphen_after_anchor(self) -> None:
        assert extract_inspection_date("Inspection date - 2025-02-28") == date(2025, 2, 28)

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Inspection date: 11/30/2026", date(2026, 11, 30)),
            ("Date: 2026-06-24", date(2026, 6, 24)),
        ],
    )
    def test_parametrized_examples(self, text: str, expected: date) -> None:
        assert extract_inspection_date(text) == expected


class TestExtractInspectionDateFallbackFormats:
    def test_dash_numeric_date(self) -> None:
        assert extract_primary_date("Inspection date: 06-24-2026") == date(2026, 6, 24)

    def test_two_digit_slash_year(self) -> None:
        assert extract_primary_date("Inspection date: 6/24/26") == date(2026, 6, 24)

    def test_month_day_year_written(self) -> None:
        assert extract_primary_date("Inspection date: June 24, 2026") == date(2026, 6, 24)

    def test_day_month_year_with_ordinal(self) -> None:
        assert extract_primary_date("Inspection date: 24th June 2026") == date(2026, 6, 24)

    def test_fallback_finds_top_of_form_date_without_label(self) -> None:
        assert extract_primary_date("06/24/2026 Final inspection Roof") == date(2026, 6, 24)
