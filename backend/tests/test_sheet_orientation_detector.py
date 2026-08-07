"""Tests for sheet orientation detection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]
import pytest

from ai.pipelines.sheet_orientation_detector import (
    DEFAULT_KEYPLAN_TEMPLATE_PATH,
    detect_orientation_from_keyplan_cv,
    detect_orientation_from_text,
    detect_sheet_orientation,
)


@dataclass
class _FakeTextElement:
    page: int
    text: str


def test_orientation_text_north_pointing_down() -> None:
    result = detect_orientation_from_text(["NORTH POINTING DOWN"])
    assert result is not None
    degrees, snippet = result
    assert degrees == pytest.approx(180.0)
    assert "NORTH" in snippet.upper()


def test_detect_sheet_orientation_prefers_text_over_pdf_rotation() -> None:
    result = detect_sheet_orientation(
        page=1,
        page_meta={"rotation": 90},
        text_elements=[_FakeTextElement(page=1, text="NORTH POINTING DOWN")],
    )
    assert result.true_north_source == "orientation_text"
    assert result.true_north_rotation_deg == pytest.approx(180.0)


def test_keyplan_cv_detects_rotated_template_in_title_block(tmp_path: Path) -> None:
    assert DEFAULT_KEYPLAN_TEMPLATE_PATH.exists()

    template = cv2.imread(str(DEFAULT_KEYPLAN_TEMPLATE_PATH), cv2.IMREAD_GRAYSCALE)
    assert template is not None

    width, height = 800, 600
    canvas = np.full((height, width), 255, dtype=np.uint8)
    x0 = int(width * 0.70)
    y0 = int(height * 0.70)
    rotated = cv2.rotate(template, cv2.ROTATE_180)
    th, tw = rotated.shape[:2]
    canvas[y0 : y0 + th, x0 : x0 + tw] = rotated

    png_path = tmp_path / "sheet.png"
    cv2.imwrite(str(png_path), canvas)

    match = detect_orientation_from_keyplan_cv(
        png_path,
        template_path=DEFAULT_KEYPLAN_TEMPLATE_PATH,
    )
    assert match is not None
    rotation_deg, score, bbox = match
    assert score >= 0.70
    assert rotation_deg == pytest.approx(180.0)
    assert bbox[0] >= 0.65
    assert bbox[1] >= 0.65
