"""Tests for legend icon PNG extraction."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from ai.pipelines.legend_icon_extraction import (
    legend_icon_entries_from_rows,
    parse_legend_bbox_arg,
    write_legend_icon_manifest,
)
from ai.pipelines.legend_line_row_builder import LegendLineRow, cluster_legend_line_rows
from models.drawing_text_element import DrawingTextElement


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
        text_normalized=text.upper(),
        bbox_json={"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        ocr_confidence=0.9,
        source="document_ai",
    )


def test_parse_legend_bbox_arg() -> None:
    bbox = parse_legend_bbox_arg("0.7,0.02,0.98,0.135")
    assert bbox == (0.7, 0.02, 0.98, 0.135)


def test_cluster_legend_line_rows_in_rect() -> None:
    """Right-side legend rect excludes left-band tokens."""
    elements = [
        _element(text="LEFT", x0=0.05, y0=0.30, x1=0.10, y1=0.32),
        _element(text="PROPERTY", x0=0.72, y0=0.05, x1=0.79, y1=0.07),
        _element(text="LINE", x0=0.80, y0=0.051, x1=0.84, y1=0.071),
    ]
    rect = (0.70, 0.02, 0.98, 0.14)
    rows = cluster_legend_line_rows(elements, legend_rect=rect)
    assert len(rows) == 1
    assert rows[0].text == "PROPERTY LINE"


def test_legend_icon_entries_from_rows_writes_pngs(tmp_path: Path) -> None:
    page = Image.new("RGB", (1000, 800), color=(255, 255, 255))
    rows = [
        LegendLineRow(
            text="WATER LINE",
            label_bbox=(0.72, 0.05, 0.90, 0.07),
            swatch_bbox=(0.66, 0.05, 0.72, 0.07),
        ),
    ]
    entries = legend_icon_entries_from_rows(page, rows, tmp_path)
    assert len(entries) == 1
    icon_path = Path(entries[0].icon_crop_path)
    assert icon_path.is_file()
    assert entries[0].label_text == "WATER LINE"
    assert entries[0].source == "indexed_tokens"

    manifest = write_legend_icon_manifest(entries, tmp_path)
    assert manifest.is_file()
    assert "WATER LINE" in manifest.read_text(encoding="utf-8")
