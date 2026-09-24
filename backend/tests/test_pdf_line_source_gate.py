"""Tests for PDF vector vs raster line-source gate (Step 0)."""

from __future__ import annotations

from pathlib import Path

import fitz

from ai.pipelines.pdf_line_source_gate import (
    PdfLineSource,
    classify_pdf_line_source,
)


def _write_blank_pdf(path: Path) -> None:
    doc = fitz.open()
    doc.new_page()
    doc.save(str(path))
    doc.close()


def _write_vector_rich_pdf(path: Path, *, line_count: int = 550) -> None:
    doc = fitz.open()
    page = doc.new_page(width=800, height=600)
    for i in range(line_count):
        y = 20 + (i % 500)
        page.draw_line((10, y), (400, y), width=0.5)
    doc.save(str(path))
    doc.close()


def test_classify_blank_pdf_as_raster(tmp_path: Path) -> None:
    pdf_path = tmp_path / "blank.pdf"
    _write_blank_pdf(pdf_path)

    source, stats = classify_pdf_line_source(pdf_path)

    assert source is PdfLineSource.RASTER
    assert stats.line_op_count < 500
    assert stats.stroked_path_count < 100


def test_classify_vector_rich_pdf_as_vector(tmp_path: Path) -> None:
    pdf_path = tmp_path / "vector.pdf"
    _write_vector_rich_pdf(pdf_path, line_count=550)

    source, stats = classify_pdf_line_source(pdf_path)

    assert source is PdfLineSource.VECTOR
    assert stats.line_op_count >= 500
    assert stats.stroked_path_count >= 100
    assert stats.path_count >= stats.stroked_path_count


def test_classify_invalid_page_raises(tmp_path: Path) -> None:
    pdf_path = tmp_path / "one_page.pdf"
    _write_blank_pdf(pdf_path)

    try:
        classify_pdf_line_source(pdf_path, page=99)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "out of range" in str(exc)
