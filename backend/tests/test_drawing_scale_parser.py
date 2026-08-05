"""Tests for drawing scale parser (Phase 3a)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ai.pipelines.document_text_extraction import BoundingBox, PositionedWord
from ai.pipelines.drawing_scale_parser import (
    SCALE_LLM_CONFIDENCE_THRESHOLD,
    page_size_inches_from_points,
    parse_scale_from_text,
    parse_scale_from_text_llm,
    parse_scale_from_words,
    real_extent_feet,
    real_size_from_normalized_bbox,
    _parse_scale_llm_payload,
)


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


def test_parse_scale_llm_payload_from_json_block() -> None:
    payload = _parse_scale_llm_payload(
        '```json\n{"found": true, "raw_text": "1\\" = 10\'", '
        '"paper_inches": 1, "real_feet": 10, "confidence": 0.84}\n```'
    )
    assert payload["found"] is True
    assert payload["paper_inches"] == pytest.approx(1.0)
    assert payload["real_feet"] == pytest.approx(10.0)
    assert payload["confidence"] == pytest.approx(0.84)


@patch("ai.pipelines.drawing_scale_parser._call_scale_llm")
def test_parse_scale_from_text_llm_builds_scale_json(mock_llm) -> None:
    mock_llm.return_value = {
        "found": True,
        "raw_text": '1" = 10\'',
        "paper_inches": 1.0,
        "real_feet": 10.0,
        "confidence": 0.84,
    }

    parsed = parse_scale_from_text_llm("Drawing scale one inch equals ten feet")
    assert parsed is not None
    assert parsed["real_feet_per_paper_inch"] == pytest.approx(10.0)
    assert parsed["confidence"] == pytest.approx(0.84)
    mock_llm.assert_called_once()


@patch("ai.pipelines.drawing_scale_parser._call_scale_llm")
def test_parse_scale_from_text_llm_rejects_low_confidence(mock_llm) -> None:
    mock_llm.return_value = {
        "found": True,
        "raw_text": '1" = 10\'',
        "paper_inches": 1.0,
        "real_feet": 10.0,
        "confidence": SCALE_LLM_CONFIDENCE_THRESHOLD - 0.01,
    }

    assert parse_scale_from_text_llm("scale maybe ten feet") is None


@patch("ai.pipelines.drawing_scale_parser._call_scale_llm")
def test_parse_scale_from_words_uses_llm_when_regex_misses(mock_llm) -> None:
    mock_llm.return_value = {
        "found": True,
        "raw_text": '1" = 10\'',
        "paper_inches": 1.0,
        "real_feet": 10.0,
        "confidence": 0.80,
    }
    words = [
        _word("Drawing", 500.0, 650.0),
        _word("scale", 545.0, 650.0),
        _word("one", 590.0, 650.0),
        _word("inch", 630.0, 650.0),
        _word("ten", 670.0, 650.0),
        _word("feet", 710.0, 650.0),
    ]

    parsed = parse_scale_from_words(words, page=1)
    assert parsed is not None
    assert parsed["real_feet_per_paper_inch"] == pytest.approx(10.0)
    assert parsed["confidence"] == pytest.approx(0.80)
    mock_llm.assert_called_once()


@patch("ai.pipelines.drawing_scale_parser._call_scale_llm")
def test_parse_scale_from_words_prefers_regex_over_llm(mock_llm) -> None:
    words = [
        _word('1"', 500.0, 650.0),
        _word("=", 545.0, 650.0),
        _word("10'", 570.0, 650.0),
    ]

    parsed = parse_scale_from_words(words, page=1)
    assert parsed is not None
    assert parsed["real_feet_per_paper_inch"] == pytest.approx(10.0)
    assert parsed["confidence"] == pytest.approx(0.90)
    mock_llm.assert_not_called()


def test_page_size_inches_from_points() -> None:
    width_in, height_in = page_size_inches_from_points(720.0, 504.0)
    assert width_in == pytest.approx(10.0)
    assert height_in == pytest.approx(7.0)


def test_real_extent_feet_matches_plan_formula() -> None:
    # real_width_ft = normalized_width * page_width_in * real_feet_per_paper_inch
    assert real_extent_feet(0.05, 42.0, 10.0) == pytest.approx(21.0)


def test_real_size_from_normalized_bbox() -> None:
    scale_json = parse_scale_from_text('1"=10\'')
    assert scale_json is not None

    size = real_size_from_normalized_bbox(
        {"x0": 0.0, "y0": 0.0, "x1": 0.05, "y1": 0.10},
        scale_json,
        page_meta={"width_pt": 720.0, "height_pt": 504.0},
    )
    assert size is not None
    assert size["width_ft"] == pytest.approx(0.05 * 10.0 * 10.0)
    assert size["height_ft"] == pytest.approx(0.10 * 7.0 * 10.0)
