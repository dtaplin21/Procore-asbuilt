"""Tests for drawing scale parser (Phase 3a)."""

from __future__ import annotations

import pytest

from ai.pipelines.document_text_extraction import BoundingBox, PositionedWord
from ai.pipelines.drawing_scale_parser import parse_scale_from_text, parse_scale_from_words


def _word(text: str, x: float, y: float, page_index: int = 0) -> PositionedWord:
    return PositionedWord(
        text=text,
        bbox=BoundingBox(
            x=x,
            y=y,
            width=40.0,
            height=12.0,
            page_width=612.0,
            page_height=792.0,
        ),
        page_index=page_index,
    )


@pytest.mark.parametrize(
    ("text", "real_feet_per_paper_inch"),
    [
        ('1" = 10\'', 10.0),
        ('1"=10\'', 10.0),
        ("1 inch = 10 feet", 10.0),
        ("SCALE 1/8\" = 1'-0\"", 8.0),
        ("HORIZ 1\"=10'  VERT 1\"=10'", 10.0),
    ],
)
def test_parse_scale_from_text_patterns(text: str, real_feet_per_paper_inch: float) -> None:
    parsed = parse_scale_from_text(text)
    assert parsed is not None
    assert parsed["real_feet_per_paper_inch"] == pytest.approx(real_feet_per_paper_inch)
    assert parsed["paper_inches_per_real_foot"] == pytest.approx(1 / real_feet_per_paper_inch)
    assert parsed["horizontal"]["units"] == "in=ft"


def test_parse_scale_1_to_100_ratio() -> None:
    parsed = parse_scale_from_text("SCALE 1:100")
    assert parsed is not None
    assert parsed["real_feet_per_paper_inch"] == pytest.approx(100 / 12)
    assert parsed["confidence"] == pytest.approx(0.72)


def test_parse_scale_attaches_page_dimensions() -> None:
    parsed = parse_scale_from_text(
        '1"=10\'',
        page_meta={"width_pt": 720.0, "height_pt": 504.0},
    )
    assert parsed is not None
    assert parsed["page_width_in"] == pytest.approx(10.0)
    assert parsed["page_height_in"] == pytest.approx(7.0)


def test_parse_scale_from_words_prefers_title_block() -> None:
    words = [
        _word('1"', 50.0, 100.0),
        _word("=", 95.0, 100.0),
        _word("20'", 120.0, 100.0),
        _word('1"', 500.0, 650.0),
        _word("=", 545.0, 650.0),
        _word("10'", 570.0, 650.0),
    ]
    parsed = parse_scale_from_words(words, page=1)
    assert parsed is not None
    assert parsed["real_feet_per_paper_inch"] == pytest.approx(10.0)
    assert parsed["source_bbox"][0] >= 0.75


def test_parse_scale_from_words_falls_back_to_full_page() -> None:
    words = [
        _word("SCALE", 100.0, 200.0),
        _word('1"', 150.0, 200.0),
        _word("=", 180.0, 200.0),
        _word("10'", 200.0, 200.0),
    ]
    parsed = parse_scale_from_words(words, page=1)
    assert parsed is not None
    assert parsed["real_feet_per_paper_inch"] == pytest.approx(10.0)
