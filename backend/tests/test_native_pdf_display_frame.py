"""Native PDF display-frame extraction and Document AI agreement checks."""

from __future__ import annotations

import json
from pathlib import Path

import fitz
import pytest

from ai.pipelines.document_text_extraction import extract_document
from ai.pipelines.native_pdf_display_frame import (
    DisplayWord,
    frame_agreement,
    native_words_display_fractional,
)
from ai.pipelines.pdf_display_space import pdf_rect_to_display_fractional

_MASTER_1722_PDF = (
    Path(__file__).resolve().parents[1]
    / "uploads/projects/1348/drawings/213463639cc949cda3e2356abe5c560d_Master.pdf"
)
_MASTER_1722_EXPORT = Path(__file__).resolve().parents[2] / "Notes/master-1722-text-elements.json"


def test_frame_agreement_counts_aligned_pairs() -> None:
    native = [DisplayWord("HELLO", 0.10, 0.20, 0.15, 0.22)]
    docai = [{"text": "HELLO", "bbox_json": {"x0": 0.101, "y0": 0.201, "x1": 0.14, "y1": 0.22}}]
    report = frame_agreement(native, docai, center_tol=0.02)
    assert report["compared"] == 1
    assert report["matched"] == 1
    assert report["agreement"] == 1.0


def test_native_pdf_extraction_uses_rotation_not_transformation_matrix() -> None:
    doc = fitz.open()
    page = doc.new_page(width=1000, height=500)
    page.set_rotation(270)
    page.insert_text((100, 400), "TICK", fontsize=12)
    raw = page.get_text("words")[0]
    x0, y0, x1, y1 = raw[0], raw[1], raw[2], raw[3]
    display_rect = pdf_rect_to_display_fractional(page, x0, y0, x1, y1)
    fixed = native_words_display_fractional(page)
    assert fixed
    assert fixed[0].text == "TICK"
    assert abs(fixed[0].cx - (display_rect[0] + display_rect[2]) / 2) < 0.01
    assert abs(fixed[0].cy - (display_rect[1] + display_rect[3]) / 2) < 0.01
    doc.close()


@pytest.mark.skipif(not _MASTER_1722_PDF.is_file(), reason="Master.pdf fixture not on disk")
@pytest.mark.skipif(not _MASTER_1722_EXPORT.is_file(), reason="1722 export snapshot missing")
def test_master_1722_native_display_frame_matches_document_ai() -> None:
    data = json.loads(_MASTER_1722_EXPORT.read_text())
    elements = data["drawing_text_elements"]
    persisted_native = [t for t in elements if t.get("source") == "native_pdf"]
    docai = [t for t in elements if t.get("source") == "document_ai"]

    page = fitz.open(str(_MASTER_1722_PDF))[0]
    fixed_native = native_words_display_fractional(page)
    page.close()

    before = frame_agreement(persisted_native, docai)
    after = frame_agreement(fixed_native, docai)

    assert before["agreement"] is not None and before["agreement"] < 0.1
    assert after["agreement"] is not None and after["agreement"] > 0.7

    tick = [w for w in fixed_native if w.text in ("0'", "4'", "10'", "20'", "40'")]
    assert tick
    for word in tick:
        assert 0.68 < word.cx < 0.74
        assert 0.96 < word.cy < 0.98


@pytest.mark.skipif(not _MASTER_1722_PDF.is_file(), reason="Master.pdf fixture not on disk")
def test_extract_document_native_words_on_rotated_master() -> None:
    extracted = extract_document(_MASTER_1722_PDF)
    ticks = [w for w in extracted.words if w.text in ("0'", "4'", "10'", "20'", "40'")]
    assert ticks
    for word in ticks:
        x0, y0, x1, y1 = word.bbox.to_fractional()
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        assert 0.68 < cx < 0.74
        assert 0.96 < cy < 0.98
