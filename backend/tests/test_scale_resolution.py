"""Line-local scale parsing and scale-bar corroboration."""

from __future__ import annotations

import json
from pathlib import Path

import fitz
import pytest

from ai.pipelines.native_pdf_display_frame import DisplayWord, native_words_display_fractional
from ai.pipelines.scale_resolution import (
    DisplayScaleWord,
    attach_scales_to_viewports,
    resolve_scale,
    resolve_scale_from_sources,
)

_MASTER_PDF = (
    Path(__file__).resolve().parents[1]
    / "uploads/projects/1348/drawings/213463639cc949cda3e2356abe5c560d_Master.pdf"
)


def _w(text: str, x0: float, y0: float, x1: float | None = None, y1: float | None = None) -> DisplayScaleWord:
    return DisplayScaleWord(
        text=text,
        x0=x0,
        y0=y0,
        x1=x1 if x1 is not None else x0 + 0.01,
        y1=y1 if y1 is not None else y0 + 0.004,
    )


def test_text_only_single_line() -> None:
    words = [_w("1", 0.5, 0.9), _w("INCH", 0.51, 0.9), _w("=", 0.52, 0.9), _w("10", 0.53, 0.9), _w("FT", 0.54, 0.9)]
    result = resolve_scale(words, page_width_in=36.0)
    assert result["status"] == "text_only"
    assert result["scale_json"] is not None
    assert result["scale_json"]["real_feet_per_paper_inch"] == pytest.approx(10.0)


def test_attach_scales_to_viewports() -> None:
    candidates = [
        {"real_feet_per_paper_inch": 5.0, "bbox": [0.1, 0.05, 0.2, 0.08], "raw_text": '1" = 5 FT'},
        {"real_feet_per_paper_inch": 20.0, "bbox": [0.2, 0.5, 0.3, 0.52], "raw_text": "1 INCH = 20 FT"},
    ]
    viewports = [
        {"viewport_id": "section", "bbox_fractional": [0.04, 0.03, 0.55, 0.30]},
        {"viewport_id": "plan", "bbox_fractional": [0.03, 0.30, 0.88, 0.99]},
    ]
    attached = attach_scales_to_viewports(candidates, viewports)
    assert round(attached["section"]["real_feet_per_paper_inch"]) == 5
    assert round(attached["plan"]["real_feet_per_paper_inch"]) == 20


@pytest.mark.skipif(not _MASTER_PDF.is_file(), reason="Master.pdf not on disk")
def test_master_1722_native_corroborates_20_ft_per_inch() -> None:
    doc = fitz.open(str(_MASTER_PDF))
    page = doc[0]
    page_w_in = page.rect.width / 72.0
    native = native_words_display_fractional(page)
    doc.close()

    result = resolve_scale(native, page_w_in)
    assert result["status"] == "corroborated", result
    assert result["scale_json"] is not None
    assert result["scale_json"]["real_feet_per_paper_inch"] == pytest.approx(20.0, rel=1e-4)
    assert "INCH" in result["scale_json"]["raw_text"].upper()


@pytest.mark.skipif(not _MASTER_PDF.is_file(), reason="Master.pdf not on disk")
def test_master_1722_fake_40_ft_inch_conflicts_with_bar() -> None:
    doc = fitz.open(str(_MASTER_PDF))
    page = doc[0]
    page_w_in = page.rect.width / 72.0
    native = list(native_words_display_fractional(page))
    doc.close()

    fake = [w for w in native if w.text not in ("20", "FT", "=", "INCH", "1")]
    y = 0.9767
    for t, x in [("1", 0.6869), ("INCH", 0.6887), ("=", 0.695), ("40", 0.6973), ("FT", 0.701)]:
        fake.append(DisplayWord(t, x, y, x + 0.003, y + 0.004))

    result = resolve_scale(fake, page_w_in)
    assert result["status"] == "conflict"
    assert result["scale_json"] is None
