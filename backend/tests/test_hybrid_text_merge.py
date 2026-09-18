"""Tests for native + OCR word merge."""

from __future__ import annotations

from ai.pipelines.document_text_extraction import BoundingBox, PositionedWord
from ai.pipelines.hybrid_text_merge import (
    merge_native_and_ocr_words,
    words_are_duplicates,
)


def _word(
    text: str,
    *,
    x: float = 100.0,
    y: float = 200.0,
    page_index: int = 0,
    page_width: float = 1000.0,
    page_height: float = 800.0,
) -> PositionedWord:
    return PositionedWord(
        text=text,
        bbox=BoundingBox(
            x=x,
            y=y,
            width=40.0,
            height=12.0,
            page_width=page_width,
            page_height=page_height,
        ),
        page_index=page_index,
    )


def test_words_are_duplicates_requires_same_page() -> None:
    left = _word("SSMH", page_index=0)
    right = _word("SSMH", page_index=1)
    assert words_are_duplicates(left, right) is False


def test_merge_prefers_native_on_duplicate() -> None:
    native = [_word("SSMH", x=100.0, page_width=3024.0)]
    ocr = [_word("SSMH", x=278.0, page_width=8400.0)]  # ~same fractional center
    merged = merge_native_and_ocr_words(native, ocr)
    assert len(merged) == 1
    assert merged[0].text == "SSMH"
    assert merged[0].token_source == "native_pdf"


def test_merge_unions_unique_ocr_tokens() -> None:
    native = [_word("UCSF")]
    ocr = [_word("MLK"), _word("SDMH")]
    merged = merge_native_and_ocr_words(native, ocr)
    texts = {word.text for word in merged}
    assert texts == {"UCSF", "MLK", "SDMH"}
    sources = {word.text: word.token_source for word in merged}
    assert sources["UCSF"] == "native_pdf"
    assert sources["MLK"] == "tesseract"
    assert sources["SDMH"] == "tesseract"
