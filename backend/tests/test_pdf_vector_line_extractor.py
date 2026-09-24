"""Tests for PDF vector line extraction (Step 1)."""

from __future__ import annotations

from pathlib import Path

import fitz

from ai.pipelines.landmark_extractor import TITLE_BLOCK_X_MIN, TITLE_BLOCK_Y_MIN
from ai.pipelines.pdf_vector_line_extractor import (
    extract_pdf_vector_chains,
    extract_pdf_vector_segments,
    segments_to_chains,
)
from ai.pipelines.sheet_entity_graph import DrawingViewport


def _write_solid_plan_line_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=800, height=600)
    # Plan area (avoid title block corner).
    page.draw_line((80, 200), (720, 200), width=0.72, color=(0, 0, 0))
    doc.save(str(path))
    doc.close()


def _write_dashed_shape_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=800, height=600)
    shape = page.new_shape()
    for i in range(8):
        x0 = 80 + i * 24
        shape.draw_line(fitz.Point(x0, 250), fitz.Point(x0 + 12, 250))
    shape.finish(color=(0, 0, 0), width=0.72)
    shape.commit()
    doc.save(str(path))
    doc.close()


def test_extract_segments_maps_to_fractional_display_space(tmp_path: Path) -> None:
    pdf_path = tmp_path / "solid.pdf"
    _write_solid_plan_line_pdf(pdf_path)

    segments = extract_pdf_vector_segments(pdf_path)

    assert len(segments) >= 1
    seg = segments[0]
    assert 0.0 <= seg.x0 <= 1.0 and 0.0 <= seg.y0 <= 1.0
    assert 0.0 <= seg.x1 <= 1.0 and 0.0 <= seg.y1 <= 1.0
    assert abs(seg.stroke_width - 0.72) < 0.01
    mid_x = (seg.x0 + seg.x1) / 2.0
    mid_y = (seg.y0 + seg.y1) / 2.0
    assert mid_x < TITLE_BLOCK_X_MIN or mid_y < TITLE_BLOCK_Y_MIN


def test_solid_line_chain_kind(tmp_path: Path) -> None:
    pdf_path = tmp_path / "solid.pdf"
    _write_solid_plan_line_pdf(pdf_path)

    chains = extract_pdf_vector_chains(pdf_path)

    assert chains
    assert chains[0].style.kind_guess == "solid"
    assert len(chains[0].points) >= 2


def test_dashed_shape_has_multiple_segments_and_non_solid_kind(tmp_path: Path) -> None:
    pdf_path = tmp_path / "dashed.pdf"
    _write_dashed_shape_pdf(pdf_path)

    segments = extract_pdf_vector_segments(pdf_path)
    assert len(segments) >= 8

    chains = segments_to_chains(segments)
    assert chains
    assert chains[0].style.segment_count >= 8
    assert chains[0].style.kind_guess in {"dashed", "dash_dot", "unknown"}


def test_extract_segments_on_rotated_page_stays_in_fractional_range(tmp_path: Path) -> None:
    pdf_path = tmp_path / "rotated.pdf"
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)
    page.set_rotation(270)
    page.draw_line((72, 72), (320, 72), width=0.5)
    doc.save(str(pdf_path))
    doc.close()

    segments = extract_pdf_vector_segments(pdf_path)
    assert segments
    for seg in segments:
        for coord in (seg.x0, seg.y0, seg.x1, seg.y1):
            assert -0.1 <= coord <= 1.1


def test_chains_to_sheet_lines_assigns_viewport(tmp_path: Path) -> None:
    from ai.pipelines.pdf_vector_line_extractor import chains_to_sheet_lines

    pdf_path = tmp_path / "solid.pdf"
    _write_solid_plan_line_pdf(pdf_path)
    chains = extract_pdf_vector_chains(pdf_path)
    viewports = (
        DrawingViewport(
            viewport_id="plan",
            kind="plan",
            page=1,
            bbox_fractional=(0.0, 0.0, 1.0, 0.85),
            scale=None,
            source="manual",
        ),
    )

    lines = chains_to_sheet_lines(chains, viewports)

    assert lines
    assert lines[0].viewport_id == "plan"
    assert lines[0].line_type == "solid"
    assert lines[0].source == "pdf_vector"
    assert lines[0].style_signature is not None
    assert lines[0].style_signature.get("kind_guess") == "solid"
