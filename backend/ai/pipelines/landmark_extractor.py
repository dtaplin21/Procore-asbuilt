"""Extract contour landmarks from full drawing page renditions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

TITLE_BLOCK_X_MIN = 0.75
TITLE_BLOCK_Y_MIN = 0.75
LEGEND_ZONE_X_MAX = 0.35
LEGEND_ZONE_Y_MIN = 0.65

MIN_CONTOUR_AREA_NORM = 0.00005
MAX_CONTOUR_AREA_NORM = 0.05
MIN_CONTOUR_POINTS = 5
MAX_LANDMARKS_PER_PAGE = 200

LandmarkType = Literal["tank", "manhole", "building", "other"]


@dataclass(frozen=True)
class LandmarkRecord:
    page: int
    landmark_type: LandmarkType
    bbox_json: dict[str, float]
    hu_moments_json: list[float]
    ocr_confidence: float
    meta_json: dict[str, Any]


def _centroid(bbox: dict[str, float]) -> tuple[float, float]:
    return (
        (bbox["x0"] + bbox["x1"]) / 2.0,
        (bbox["y0"] + bbox["y1"]) / 2.0,
    )


def _in_exclusion_zone(bbox: dict[str, float]) -> bool:
    cx, cy = _centroid(bbox)
    if cx >= TITLE_BLOCK_X_MIN and cy >= TITLE_BLOCK_Y_MIN:
        return True
    if cx <= LEGEND_ZONE_X_MAX and cy >= LEGEND_ZONE_Y_MIN:
        return True
    return False


def _classify_landmark_type(
    *,
    width_norm: float,
    height_norm: float,
    area_norm: float,
) -> LandmarkType:
    aspect = width_norm / max(height_norm, 1e-9)
    inverse_aspect = height_norm / max(width_norm, 1e-9)
    circularity = min(aspect, inverse_aspect)

    if area_norm >= 0.01:
        return "building"
    if 0.85 <= circularity <= 1.15 and area_norm <= 0.002:
        return "manhole"
    if area_norm >= 0.001:
        return "tank"
    return "other"


def _hint_overlap_fraction(
    bbox: dict[str, float],
    hint_bbox: tuple[float, float, float, float],
) -> float:
    x0 = max(bbox["x0"], hint_bbox[0])
    y0 = max(bbox["y0"], hint_bbox[1])
    x1 = min(bbox["x1"], hint_bbox[2])
    y1 = min(bbox["y1"], hint_bbox[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    bbox_area = max((bbox["x1"] - bbox["x0"]) * (bbox["y1"] - bbox["y0"]), 1e-9)
    return inter / bbox_area


def extract_landmarks_from_page(
    rendition_png: Path | str,
    page_meta: dict[str, Any],
    *,
    page: int | None = None,
    optional_hint_bbox: tuple[float, float, float, float] | None = None,
) -> list[LandmarkRecord]:
    """Extract landmarks from a full page PNG; exclusion zones filter only."""
    try:
        import cv2  # type: ignore[import-untyped]
        import numpy as np  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("opencv/numpy unavailable; skipping landmark extraction")
        return []

    image = cv2.imread(str(rendition_png), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return []

    height, width = image.shape[:2]
    if height <= 0 or width <= 0:
        return []

    blurred = cv2.GaussianBlur(image, (5, 5), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    page_number = int(page if page is not None else page_meta.get("page", 1))
    landmarks: list[LandmarkRecord] = []

    for contour in contours:
        if len(contour) < MIN_CONTOUR_POINTS:
            continue

        x, y, w, h = cv2.boundingRect(contour)
        if w <= 0 or h <= 0:
            continue

        bbox = {
            "x0": x / width,
            "y0": y / height,
            "x1": (x + w) / width,
            "y1": (y + h) / height,
        }
        area_norm = (bbox["x1"] - bbox["x0"]) * (bbox["y1"] - bbox["y0"])
        if area_norm < MIN_CONTOUR_AREA_NORM or area_norm > MAX_CONTOUR_AREA_NORM:
            continue
        if _in_exclusion_zone(bbox):
            continue

        moments = cv2.moments(contour)
        if moments.get("m00", 0) == 0:
            continue
        hu = cv2.HuMoments(moments).flatten()
        hu_list = [float(value) for value in hu]

        landmark_type = _classify_landmark_type(
            width_norm=bbox["x1"] - bbox["x0"],
            height_norm=bbox["y1"] - bbox["y0"],
            area_norm=area_norm,
        )
        meta: dict[str, Any] = {"area_norm": area_norm, "contour_points": len(contour)}
        if optional_hint_bbox is not None:
            overlap = _hint_overlap_fraction(bbox, optional_hint_bbox)
            meta["hint_overlap"] = overlap
            if overlap > 0:
                meta["hint_boost"] = True

        landmarks.append(
            LandmarkRecord(
                page=page_number,
                landmark_type=landmark_type,
                bbox_json=bbox,
                hu_moments_json=hu_list,
                ocr_confidence=1.0,
                meta_json=meta,
            )
        )
        if len(landmarks) >= MAX_LANDMARKS_PER_PAGE:
            break

    if optional_hint_bbox is not None:
        landmarks.sort(
            key=lambda record: -float(record.meta_json.get("hint_overlap", 0.0)),
        )

    return landmarks
