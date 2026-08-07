"""Tests for evidence kind classification."""

from __future__ import annotations

import pytest

from ai.pipelines.document_text_extraction import (
    BoundingBox,
    ExtractedDocument,
    PositionedWord,
    SourceFormat,
)
from ai.pipelines.evidence_kind_classifier import (
    EvidenceKind,
    classify_evidence_kind,
    contour_matching_enabled,
    native_page1_word_count,
)
from ai.schemas.document_extraction_schemas import DocumentType


def _word(text: str, page_index: int = 0) -> PositionedWord:
    return PositionedWord(
        text=text,
        bbox=BoundingBox(
            x=0.0,
            y=0.0,
            width=10.0,
            height=10.0,
            page_width=100.0,
            page_height=100.0,
        ),
        page_index=page_index,
    )


@pytest.mark.parametrize(
    ("document_type", "expected"),
    [
        (DocumentType.FIELD_PHOTO.value, EvidenceKind.PHOTO),
        (DocumentType.MASTER_DRAWING.value, EvidenceKind.DRAWING_SCAN),
        (DocumentType.INSPECTION_REPORT.value, EvidenceKind.FORM),
        (DocumentType.UNKNOWN.value, EvidenceKind.FORM),
    ],
)
def test_document_type_base_mapping(document_type: str, expected: EvidenceKind) -> None:
    assert classify_evidence_kind(document_type) == expected


def test_linked_install_sheet_overrides_form_to_drawing_scan() -> None:
    assert (
        classify_evidence_kind(
            DocumentType.INSPECTION_REPORT.value,
            has_linked_sheet=True,
        )
        == EvidenceKind.DRAWING_SCAN
    )


def test_native_text_density_overrides_form_to_drawing_scan() -> None:
    assert (
        classify_evidence_kind(
            DocumentType.INSPECTION_REPORT.value,
            native_page1_words=50,
        )
        == EvidenceKind.DRAWING_SCAN
    )


def test_field_photo_stays_photo_without_overrides() -> None:
    assert classify_evidence_kind(DocumentType.FIELD_PHOTO.value) == EvidenceKind.PHOTO


def test_native_page1_word_count_ignores_non_native_pdf() -> None:
    document = ExtractedDocument(
        source_format=SourceFormat.SCANNED_PDF,
        page_count=1,
        words=[_word(f"w{i}") for i in range(60)],
    )
    assert native_page1_word_count(document) == 0


def test_native_page1_word_count_only_page_one() -> None:
    words = [_word(f"w{i}") for i in range(50)]
    words.extend(_word(f"p2-{i}", page_index=1) for i in range(10))
    document = ExtractedDocument(
        source_format=SourceFormat.NATIVE_PDF,
        page_count=2,
        words=words,
    )
    assert native_page1_word_count(document) == 50


def test_contour_matching_enabled_only_for_drawing_scan() -> None:
    assert contour_matching_enabled(EvidenceKind.DRAWING_SCAN) is True
    assert contour_matching_enabled(EvidenceKind.PHOTO) is False
    assert contour_matching_enabled(EvidenceKind.FORM) is False
