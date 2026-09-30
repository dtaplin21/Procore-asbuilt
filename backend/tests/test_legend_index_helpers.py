"""Legend row clustering helpers (Document AI tokens + title-block ROI)."""

from __future__ import annotations

from ai.pipelines.legend_line_row_builder import LegendLineRow
from services.legend_index_helpers import (
    legend_rows_to_audit_meta,
    parse_fractional_rect,
)


def test_parse_fractional_rect() -> None:
    assert parse_fractional_rect("0.7,0.02,0.98,0.135") == (0.7, 0.02, 0.98, 0.135)
    assert parse_fractional_rect(None) is None


def test_legend_rows_to_audit_meta_shape() -> None:
    row = LegendLineRow(
        text="Property line",
        label_bbox=(0.71, 0.03, 0.95, 0.04),
        swatch_bbox=(0.70, 0.03, 0.71, 0.04),
    )
    meta = legend_rows_to_audit_meta([row])
    assert meta[0]["text"] == "Property line"
    assert "label_bbox" in meta[0]
