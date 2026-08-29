"""Baseline tests for OpenCV contour landmark extraction (PRE-1 digitization).

Current behavior (sheet digitization plan):
- Contours + Hu moments only — no trained symbol classes (YOLO/DINO).
- Heuristic landmark_type labels (building/manhole/tank/other) from shape ratios.
- Title-block / legend exclusion zones filter candidates.
"""

from __future__ import annotations

from pathlib import Path

import cv2  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]

from ai.pipelines.landmark_extractor import (
    TITLE_BLOCK_X_MIN,
    TITLE_BLOCK_Y_MIN,
    extract_landmarks_from_page,
)


def _synthetic_page_with_rectangles(path: Path) -> None:
    image = np.full((600, 800), 255, dtype=np.uint8)
    cv2.rectangle(image, (120, 140), (180, 200), 0, 2)
    cv2.rectangle(image, (320, 240), (390, 310), 0, 2)
    cv2.rectangle(image, (650, 520), (780, 580), 0, 2)  # title block — excluded
    cv2.imwrite(str(path), image)


def test_extract_landmarks_from_full_page_excludes_title_block(tmp_path: Path) -> None:
    png = tmp_path / "page.png"
    _synthetic_page_with_rectangles(png)
    landmarks = extract_landmarks_from_page(png, {"page": 1})
    assert len(landmarks) >= 2
    for landmark in landmarks:
        cx = (landmark.bbox_json["x0"] + landmark.bbox_json["x1"]) / 2.0
        cy = (landmark.bbox_json["y0"] + landmark.bbox_json["y1"]) / 2.0
        assert not (cx >= TITLE_BLOCK_X_MIN and cy >= TITLE_BLOCK_Y_MIN)


def test_landmarks_are_contour_heuristics_not_trained_symbols(tmp_path: Path) -> None:
    """Baseline: types come from aspect/area heuristics, not a symbol detector."""
    png = tmp_path / "page.png"
    _synthetic_page_with_rectangles(png)
    landmarks = extract_landmarks_from_page(png, {"page": 1})
    assert landmarks
    allowed = {"building", "manhole", "tank", "other"}
    for landmark in landmarks:
        assert landmark.landmark_type in allowed
        assert len(landmark.hu_moments_json) == 7
        assert "area_norm" in landmark.meta_json
        assert "detector" not in landmark.meta_json
        assert "symbol_class" not in landmark.meta_json
