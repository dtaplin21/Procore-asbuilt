"""Deterministic OpenCV line / centerline extraction for sheet digitization."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

from ai.pipelines.landmark_extractor import TITLE_BLOCK_X_MIN, TITLE_BLOCK_Y_MIN
from ai.pipelines.sheet_entity_graph import DrawingViewport, SheetLine

logger = logging.getLogger(__name__)

MIN_SEGMENT_LENGTH_PX = 40.0
MIN_POLYLINE_LENGTH_FRAC = 0.02
HOUGH_THRESHOLD = 40
HOUGH_MIN_LINE_LENGTH = 60
HOUGH_MAX_LINE_GAP = 25
MERGE_ANGLE_DEG = 8.0
MERGE_DIST_PX = 14.0


def _in_titleblock_frac(x: float, y: float) -> bool:
    return x >= TITLE_BLOCK_X_MIN and y >= TITLE_BLOCK_Y_MIN


def _polyline_midpoint(
    points: tuple[tuple[float, float], ...],
) -> tuple[float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _polyline_length_frac(points: tuple[tuple[float, float], ...]) -> float:
    total = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        total += math.hypot(x1 - x0, y1 - y0)
    return total


def _segment_angle_deg(x0: float, y0: float, x1: float, y1: float) -> float:
    return math.degrees(math.atan2(y1 - y0, x1 - x0)) % 180.0


def _angle_delta_deg(a: float, b: float) -> float:
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def _point_line_distance(
    px: float,
    py: float,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> float:
    dx, dy = x1 - x0, y1 - y0
    denom = math.hypot(dx, dy)
    if denom < 1e-9:
        return math.hypot(px - x0, py - y0)
    return abs(dy * px - dx * py + x1 * y0 - y1 * x0) / denom


def _normalize_segment(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> tuple[float, float, float, float]:
    """Order endpoints left-to-right (top-to-bottom on ties)."""
    if (x0, y0) <= (x1, y1):
        return x0, y0, x1, y1
    return x1, y1, x0, y0


def _merge_colinear_segments(
    segments: list[tuple[float, float, float, float]],
    *,
    angle_tol_deg: float = MERGE_ANGLE_DEG,
    dist_tol_px: float = MERGE_DIST_PX,
) -> list[tuple[tuple[float, float], ...]]:
    """Merge near-colinear overlapping/adjacent segments into 2-point polylines."""
    if not segments:
        return []

    remaining = [
        _normalize_segment(x0, y0, x1, y1) for x0, y0, x1, y1 in segments
    ]
    remaining.sort(key=lambda s: (-math.hypot(s[2] - s[0], s[3] - s[1]), s[0], s[1]))

    polylines: list[tuple[tuple[float, float], ...]] = []
    used = [False] * len(remaining)

    for i, base in enumerate(remaining):
        if used[i]:
            continue
        used[i] = True
        bx0, by0, bx1, by1 = base
        angle = _segment_angle_deg(bx0, by0, bx1, by1)
        pts_x = [bx0, bx1]
        pts_y = [by0, by1]

        changed = True
        while changed:
            changed = False
            for j, seg in enumerate(remaining):
                if used[j]:
                    continue
                x0, y0, x1, y1 = seg
                if _angle_delta_deg(angle, _segment_angle_deg(x0, y0, x1, y1)) > angle_tol_deg:
                    continue
                d0 = _point_line_distance(x0, y0, bx0, by0, bx1, by1)
                d1 = _point_line_distance(x1, y1, bx0, by0, bx1, by1)
                if d0 > dist_tol_px or d1 > dist_tol_px:
                    continue
                # Require proximity along the chain (endpoint near current extent).
                extent = list(zip(pts_x, pts_y))
                near = False
                for px, py in extent:
                    if math.hypot(px - x0, py - y0) <= dist_tol_px * 3:
                        near = True
                    if math.hypot(px - x1, py - y1) <= dist_tol_px * 3:
                        near = True
                if not near:
                    # Still allow if segment overlaps projection of base strongly.
                    proj_ok = d0 <= dist_tol_px and d1 <= dist_tol_px
                    if not proj_ok:
                        continue
                used[j] = True
                pts_x.extend([x0, x1])
                pts_y.extend([y0, y1])
                changed = True

        # Fit endpoints as min/max projection onto the dominant axis.
        dx, dy = bx1 - bx0, by1 - by0
        if abs(dx) >= abs(dy):
            order = sorted(zip(pts_x, pts_y), key=lambda p: p[0])
        else:
            order = sorted(zip(pts_x, pts_y), key=lambda p: p[1])
        start, end = order[0], order[-1]
        if start == end:
            continue
        polylines.append((start, end))

    return polylines


def _detect_segments(binary: Any) -> list[tuple[float, float, float, float]]:
    import cv2  # type: ignore[import-untyped]
    import numpy as np  # type: ignore[import-untyped]

    work = binary

    segments: list[tuple[float, float, float, float]] = []

    try:
        lsd = cv2.createLineSegmentDetector()
        detected = lsd.detect(work)[0]
    except Exception:  # noqa: BLE001
        detected = None

    if detected is not None:
        for line in detected:
            x0, y0, x1, y1 = (float(v) for v in line.reshape(4))
            if math.hypot(x1 - x0, y1 - y0) >= MIN_SEGMENT_LENGTH_PX:
                segments.append((x0, y0, x1, y1))

    if segments:
        return segments

    hough = cv2.HoughLinesP(
        work,
        rho=1,
        theta=np.pi / 180.0,
        threshold=HOUGH_THRESHOLD,
        minLineLength=HOUGH_MIN_LINE_LENGTH,
        maxLineGap=HOUGH_MAX_LINE_GAP,
    )
    if hough is None:
        return []
    for line in hough:
        x0, y0, x1, y1 = (float(v) for v in line.reshape(4))
        if math.hypot(x1 - x0, y1 - y0) >= MIN_SEGMENT_LENGTH_PX:
            segments.append((x0, y0, x1, y1))
    return segments


def extract_line_polylines(
    rendition_png: Path | str,
    *,
    viewport: DrawingViewport | None = None,
    max_lines: int = 200,
) -> list[SheetLine]:
    """Extract page-fractional polylines from a drawing PNG.

    Pixel detections are always mapped back to the full page. When ``viewport``
    is set, processing is cropped to that bbox first and ``viewport_id`` is
    attached to each returned ``SheetLine``.
    """
    try:
        import cv2  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("opencv unavailable; skipping line extraction")
        return []

    image = cv2.imread(str(rendition_png), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return []

    page_h, page_w = image.shape[:2]
    if page_h <= 0 or page_w <= 0:
        return []

    offset_x = 0
    offset_y = 0
    work = image
    if viewport is not None:
        x0, y0, x1, y1 = viewport.bbox_fractional
        px0 = max(0, min(page_w - 1, int(x0 * page_w)))
        py0 = max(0, min(page_h - 1, int(y0 * page_h)))
        px1 = max(px0 + 1, min(page_w, int(math.ceil(x1 * page_w))))
        py1 = max(py0 + 1, min(page_h, int(math.ceil(y1 * page_h))))
        work = image[py0:py1, px0:px1]
        offset_x, offset_y = px0, py0
        if work.size == 0:
            return []

    blurred = cv2.GaussianBlur(work, (5, 5), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    segments = _detect_segments(closed)
    # Shift crop-local pixels into full-page pixel space before merge.
    page_segments = [
        (x0 + offset_x, y0 + offset_y, x1 + offset_x, y1 + offset_y)
        for x0, y0, x1, y1 in segments
    ]
    polylines_px = _merge_colinear_segments(page_segments)

    viewport_id = viewport.viewport_id if viewport is not None else None
    results: list[SheetLine] = []
    for points_px in polylines_px:
        points_frac = tuple(
            (float(x) / float(page_w), float(y) / float(page_h)) for x, y in points_px
        )
        if len(points_frac) < 2:
            continue
        if _polyline_length_frac(points_frac) < MIN_POLYLINE_LENGTH_FRAC:
            continue
        mx, my = _polyline_midpoint(points_frac)
        if _in_titleblock_frac(mx, my):
            continue
        # If both endpoints sit in the titleblock, skip.
        if all(_in_titleblock_frac(x, y) for x, y in points_frac):
            continue

        results.append(
            SheetLine(
                points=points_frac,
                viewport_id=viewport_id,
                confidence=0.75,
                line_type=None,
            )
        )
        if len(results) >= max_lines:
            break

    # Prefer longer polylines first.
    results.sort(key=lambda line: -_polyline_length_frac(line.points))
    return results[:max_lines]
