"""Tests for gutter-scoped adjacent OCR token phrase merge."""

from __future__ import annotations

from ai.pipelines.document_text_extraction import BoundingBox, PositionedWord
from ai.pipelines.proximity_phrase_merge import (
    MAX_MERGE_CHAIN_LEN,
    MAX_MERGED_STRING_LEN,
    boxes_are_vertically_stacked,
    merge_proximate_phrases,
    should_merge_token,
)
from tests.fixtures.drawing_index_regression import (
    generate_dense_page_fixture,
    make_token,
)


def _word(
    text: str,
    *,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    source: str = "gutter_rotated_ocr",
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


def test_gutter_tokens_in_band_are_eligible() -> None:
    w = _word("HIGHWAY", x0=0.05, y0=0.50, x1=0.08, y1=0.53)
    assert should_merge_token(w) is True


def test_document_ai_never_eligible_even_in_gutter_x() -> None:
    w = _word("HIGHWAY", x0=0.05, y0=0.50, x1=0.08, y1=0.53, source="document_ai")
    assert should_merge_token(w) is False


def test_merges_vertical_gutter_stack_in_left_band() -> None:
    # Match plan-edge geometry: "24" above "HIGHWAY" (smaller y), read as HIGHWAY 24.
    words = [
        _word("24", x0=0.055, y0=0.50, x1=0.07, y1=0.515),
        _word("HIGHWAY", x0=0.05, y0=0.518, x1=0.08, y1=0.55),
    ]
    merged = merge_proximate_phrases(words)
    assert len(merged) == 1
    assert merged[0].text == "HIGHWAY 24"


def test_document_ai_dense_page_passes_through_unchanged() -> None:
    words = [
        _word("A", x0=0.70, y0=0.05, x1=0.72, y1=0.06, source="document_ai"),
        _word("B", x0=0.721, y0=0.051, x1=0.74, y1=0.061, source="document_ai"),
        _word("C", x0=0.75, y0=0.05, x1=0.77, y1=0.06, source="document_ai"),
    ]
    merged = merge_proximate_phrases(words)
    assert len(merged) == 3
    assert [w.text for w in merged] == ["A", "B", "C"]


def test_mixed_gutter_and_document_ai_preserves_doc_ai_count() -> None:
    words = [
        _word("LINE", x0=0.72, y0=0.05, x1=0.75, y1=0.06, source="document_ai"),
        _word("24", x0=0.055, y0=0.50, x1=0.07, y1=0.515),
        _word("HIGHWAY", x0=0.05, y0=0.518, x1=0.08, y1=0.55),
        _word("WATER", x0=0.76, y0=0.05, x1=0.79, y1=0.06, source="document_ai"),
    ]
    merged = merge_proximate_phrases(words)
    assert len(merged) == 3
    assert merged[0].text == "LINE"
    assert merged[1].text == "HIGHWAY 24"
    assert merged[2].text == "WATER"


def test_max_merged_string_len_blocks_runaway_chain() -> None:
    long_a = "X" * (MAX_MERGED_STRING_LEN // 2)
    long_b = "Y" * (MAX_MERGED_STRING_LEN // 2 + 5)
    words = [
        _word(long_a, x0=0.05, y0=0.50, x1=0.08, y1=0.53),
        _word(long_b, x0=0.081, y0=0.501, x1=0.10, y1=0.531),
    ]
    merged = merge_proximate_phrases(words)
    assert len(merged) == 2


def test_boxes_are_vertically_stacked_highway_24_bboxes() -> None:
    """Document AI HIGHWAY + 24 on master 1722 (overlapping y, close x0)."""
    highway = (0.68089604, 0.67869824, 0.69991547, 0.73609465)
    two_four = (0.69273037, 0.66213018, 0.70329672, 0.68047339)
    assert boxes_are_vertically_stacked(highway, two_four) is True


def test_merges_document_ai_vertical_stack_in_phrase_rect() -> None:
    words = [
        _word("HIGHWAY", x0=0.68089604, y0=0.67869824, x1=0.69991547, y1=0.73609465, source="document_ai"),
        _word("24", x0=0.69273037, y0=0.66213018, x1=0.70329672, y1=0.68047339, source="document_ai"),
    ]
    merged = merge_proximate_phrases(words)
    assert len(merged) == 1
    assert merged[0].text == "HIGHWAY 24"


def test_phrase_merge_has_a_floor() -> None:
    """A dense synthetic Doc AI page must not collapse below a token floor."""
    synthetic_tokens = generate_dense_page_fixture(n_tokens=1000)
    merged = merge_proximate_phrases(synthetic_tokens)
    assert len(merged) >= 900


def test_no_merge_outside_gutter_band() -> None:
    tokens = [
        make_token(text="A", x0=0.5, source="document_ai"),
        make_token(text="B", x0=0.52, source="document_ai"),
    ]
    merged = merge_proximate_phrases(tokens)
    assert len(merged) == 2
    assert [word.text for word in merged] == ["A", "B"]


def test_highway_24_merges_as_vertical_stack() -> None:
    tokens = [
        make_token(
            text="HIGHWAY",
            x0=0.68089604,
            y0=0.67869824,
            x1=0.69991547,
            y1=0.73609465,
            source="document_ai",
        ),
        make_token(
            text="24",
            x0=0.69273037,
            y0=0.66213018,
            x1=0.70329672,
            y1=0.68047339,
            source="document_ai",
        ),
    ]
    merged = merge_proximate_phrases(tokens)
    assert len(merged) == 1
    assert merged[0].text == "HIGHWAY 24"


def test_max_chain_len_blocks_fourth_merge() -> None:
    words = [
        _word("A", x0=0.05, y0=0.50, x1=0.06, y1=0.52),
        _word("B", x0=0.061, y0=0.501, x1=0.07, y1=0.521),
        _word("C", x0=0.071, y0=0.502, x1=0.08, y1=0.522),
        _word("D", x0=0.081, y0=0.503, x1=0.09, y1=0.523),
        _word("E", x0=0.091, y0=0.504, x1=0.10, y1=0.524),
    ]
    merged = merge_proximate_phrases(words)
    assert len(merged) >= 2
    max_parts = max(len(w.text.split()) for w in merged)
    assert max_parts <= MAX_MERGE_CHAIN_LEN
