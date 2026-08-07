"""Tests for landmark extraction and contour matching."""

from __future__ import annotations

from pathlib import Path

import cv2  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]
import pytest

from ai.pipelines.landmark_extractor import LandmarkRecord, extract_landmarks_from_page
from ai.pipelines.landmark_matcher import (
    CONFIDENCE_THREE_OR_MORE_PAIRS,
    CONFIDENCE_TWO_PAIRS,
    hu_distance,
    run_landmark_matcher,
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
        assert not (cx >= 0.75 and cy >= 0.75)


def test_hu_distance_identical_shapes_is_zero() -> None:
    hu = [1.0, 0.2, 0.05, 0.01, 1e-6, 1e-7, 1e-8]
    assert hu_distance(hu, hu) == pytest.approx(0.0)


def test_landmark_matcher_output_from_master_bboxes(tmp_path: Path) -> None:
    png = tmp_path / "page.png"
    _synthetic_page_with_rectangles(png)
    evidence_landmarks = extract_landmarks_from_page(png, {"page": 1})
    master_landmarks = [
        LandmarkRecord(
            page=1,
            landmark_type=record.landmark_type,
            bbox_json={
                "x0": record.bbox_json["x0"] + 0.05,
                "y0": record.bbox_json["y0"] + 0.05,
                "x1": record.bbox_json["x1"] + 0.05,
                "y1": record.bbox_json["y1"] + 0.05,
            },
            hu_moments_json=record.hu_moments_json,
            ocr_confidence=1.0,
            meta_json={},
        )
        for record in evidence_landmarks[:2]
    ]

    result = run_landmark_matcher(
        master_landmarks=master_landmarks,
        evidence_rendition_png=str(png),
        evidence_page_meta={"page": 1},
    )
    assert result is not None
    assert result.pair_count >= 2
    assert result.confidence in (CONFIDENCE_TWO_PAIRS, CONFIDENCE_THREE_OR_MORE_PAIRS)
    x0, y0, x1, y1 = result.bbox_fractional
    assert x1 > x0
    assert y1 > y0
