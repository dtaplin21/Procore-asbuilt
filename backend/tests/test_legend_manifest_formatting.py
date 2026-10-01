"""Production legend manifest formatting for AI-readable labels."""

from __future__ import annotations

from ai.pipelines.legend_line_row_builder import (
    format_legend_row_manifest_text,
    legend_context_block,
    LegendLineRow,
)


def test_format_hcai_permit_rows() -> None:
    raw = "SEWER LINE HCAI PERMIT SHOWN FOR REFERENCE ONLY"
    assert format_legend_row_manifest_text(raw) == (
        "SEWER LINE — HCAI PERMIT (SHOWN FOR REFERENCE ONLY)"
    )


def test_format_sheet_and_detail_commas() -> None:
    raw = "SSMH OR SDMH SEE DETAIL 3. SHEET U2.06.00"
    assert format_legend_row_manifest_text(raw) == (
        "SSMH OR SDMH, SEE DETAIL 3, SHEET U2.C6.00"
    )


def test_legend_context_block_numbered() -> None:
    rows = [
        LegendLineRow(
            text="PROPERTY LINE",
            label_bbox=(0.1, 0.1, 0.2, 0.12),
            swatch_bbox=(0.04, 0.1, 0.1, 0.12),
        ),
        LegendLineRow(
            text="WATER LINE",
            label_bbox=(0.1, 0.13, 0.2, 0.15),
            swatch_bbox=(0.04, 0.13, 0.1, 0.15),
        ),
    ]
    block = legend_context_block(rows)
    assert block.splitlines() == ["1. PROPERTY LINE", "2. WATER LINE"]
