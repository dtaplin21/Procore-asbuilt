"""Tests for raster dash-pattern classification (Step 4)."""

from __future__ import annotations

from pathlib import Path

import cv2  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]

from ai.pipelines.line_dash_classifier import (
    classify_raster_line,
    profile_along_polyline,
    signature_from_run_gap_profile,
)
from ai.pipelines.sheet_entity_graph import SheetLine


def test_profile_detects_dashed_pattern() -> None:
    binary = np.zeros((100, 400), dtype=np.uint8)
    for x in range(0, 360, 24):
        binary[50, x : x + 12] = 255

    runs, gaps = profile_along_polyline(
        binary,
        ((0.05, 0.5), (0.95, 0.5)),
        page_w=400,
        page_h=100,
    )

    assert runs
    assert gaps
    style = signature_from_run_gap_profile(runs, gaps, page_w=400, page_h=100)
    assert style.kind_guess in {"dashed", "dash_dot"}


def test_classify_raster_line_sets_source_and_style(tmp_path: Path) -> None:
    png_path = tmp_path / "dashed.png"
    image = np.full((200, 400), 255, dtype=np.uint8)
    for x in range(20, 360, 30):
        cv2.line(image, (x, 100), (x + 15, 100), 0, 2)
    cv2.imwrite(str(png_path), image)

    gray = cv2.imread(str(png_path), cv2.IMREAD_GRAYSCALE)
    assert gray is not None
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    base = SheetLine(
        points=((0.05, 0.5), (0.9, 0.5)),
        viewport_id="plan",
        confidence=0.75,
    )
    typed = classify_raster_line(base, binary, 400, 200)

    assert typed.source == "raster"
    assert typed.style_signature is not None
    assert typed.confidence < base.confidence
