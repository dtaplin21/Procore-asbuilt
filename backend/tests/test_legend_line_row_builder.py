"""Tests for legend line row clustering (Step 2a)."""

from __future__ import annotations

from models.drawing_text_element import DrawingTextElement
from ai.pipelines.legend_line_row_builder import cluster_legend_line_rows


def _element(
    *,
    text: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> DrawingTextElement:
    return DrawingTextElement(
        master_drawing_id=1,
        page=1,
        text=text,
        text_normalized=text.lower(),
        bbox_json={"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        ocr_confidence=0.9,
        source="tesseract",
    )


def test_cluster_merges_property_and_line_on_one_row() -> None:
    elements = [
        _element(text="PROPERTY", x0=0.10, y0=0.25, x1=0.17, y1=0.27),
        _element(text="LINE", x0=0.18, y0=0.251, x1=0.22, y1=0.271),
    ]

    rows = cluster_legend_line_rows(elements)

    assert len(rows) == 1
    assert rows[0].text == "PROPERTY LINE"
    assert rows[0].swatch_bbox[2] == rows[0].label_bbox[0]
    assert rows[0].swatch_bbox[0] < rows[0].label_bbox[0]


def test_cluster_excludes_plan_body_tokens() -> None:
    elements = [
        _element(text="PROPERTY", x0=0.10, y0=0.25, x1=0.17, y1=0.27),
        _element(text="MLK", x0=0.55, y0=0.40, x1=0.58, y1=0.42),
    ]

    rows = cluster_legend_line_rows(elements)

    assert len(rows) == 1
    assert rows[0].text == "PROPERTY"


def test_cluster_skips_legend_header_token() -> None:
    elements = [
        _element(text="LEGEND", x0=0.05, y0=0.25, x1=0.10, y1=0.27),
        _element(text="WATER", x0=0.12, y0=0.25, x1=0.16, y1=0.27),
        _element(text="LINE", x0=0.17, y0=0.251, x1=0.20, y1=0.271),
    ]

    rows = cluster_legend_line_rows(elements)

    assert len(rows) == 1
    assert rows[0].text == "WATER LINE"


def test_cluster_ignores_title_block_column_on_same_row() -> None:
    """Dominant x-column filter drops far-right tokens at the same row height."""
    elements = [
        _element(text="PROPERTY", x0=0.10, y0=0.25, x1=0.17, y1=0.27),
        _element(text="LINE", x0=0.18, y0=0.251, x1=0.22, y1=0.271),
        _element(text="UCSF", x0=0.32, y0=0.25, x1=0.36, y1=0.27),
        _element(text="APPROVAL", x0=0.37, y0=0.251, x1=0.42, y1=0.271),
    ]

    rows = cluster_legend_line_rows(elements)

    assert len(rows) == 1
    assert rows[0].text == "PROPERTY LINE"


def test_cluster_respects_legend_rect_over_default_band() -> None:
    elements = [
        _element(text="IN_BAND", x0=0.10, y0=0.30, x1=0.16, y1=0.32),
        _element(text="IN_RECT", x0=0.75, y0=0.05, x1=0.82, y1=0.07),
    ]
    rows = cluster_legend_line_rows(elements, legend_rect=(0.70, 0.02, 0.98, 0.14))
    assert len(rows) == 1
    assert rows[0].text == "IN_RECT"


def test_dominant_column_disabled_merges_same_row_across_columns() -> None:
    elements = [
        _element(text="PROPERTY", x0=0.10, y0=0.25, x1=0.17, y1=0.27),
        _element(text="UCSF", x0=0.32, y0=0.25, x1=0.36, y1=0.27),
    ]

    rows = cluster_legend_line_rows(elements, use_dominant_text_column=False)

    assert len(rows) == 1
    assert "UCSF" in rows[0].text
