"""Tests for adjacent OCR token phrase merge."""

from __future__ import annotations

from ai.pipelines.document_text_extraction import BoundingBox, PositionedWord
from ai.pipelines.proximity_phrase_merge import merge_proximate_phrases


def _word(
    text: str,
    *,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    source: str = "document_ai",
) -> PositionedWord:
    pw, ph = 1000.0, 1000.0
    return PositionedWord(
        text=text,
        bbox=BoundingBox(
            x=x0 * pw,
            y=y0 * ph,
            width=(x1 - x0) * pw,
            height=(y1 - y0) * ph,
            page_width=pw,
            page_height=ph,
        ),
        page_index=0,
        token_source=source,
    )


def test_merges_vertical_gutter_stack() -> None:
    words = [
        _word("HIGHWAY", x0=0.68, y0=0.68, x1=0.70, y1=0.71),
        _word("24", x0=0.685, y0=0.715, x1=0.695, y1=0.735),
    ]
    merged = merge_proximate_phrases(words)
    assert len(merged) == 1
    assert merged[0].text == "HIGHWAY 24"


def test_merges_horizontal_gap_on_same_row() -> None:
    words = [
        _word("HIGHWAY", x0=0.68, y0=0.70, x1=0.695, y1=0.72),
        _word("24", x0=0.697, y0=0.701, x1=0.705, y1=0.721),
    ]
    merged = merge_proximate_phrases(words)
    assert len(merged) == 1
    assert merged[0].text == "HIGHWAY 24"


def test_does_not_merge_different_sources() -> None:
    words = [
        _word("HIGHWAY", x0=0.68, y0=0.68, x1=0.70, y1=0.71, source="document_ai"),
        _word("24", x0=0.685, y0=0.715, x1=0.695, y1=0.735, source="gutter_rotated_ocr"),
    ]
    merged = merge_proximate_phrases(words)
    assert len(merged) == 2
