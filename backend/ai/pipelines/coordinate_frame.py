"""Normalized fractional coordinate rotation helpers."""

from __future__ import annotations

import math


def rotate_point(
    x: float,
    y: float,
    degrees: float,
    *,
    cx: float = 0.5,
    cy: float = 0.5,
) -> tuple[float, float]:
    """Rotate a normalized point clockwise around ``(cx, cy)``."""
    if degrees == 0.0:
        return x, y

    radians = math.radians(degrees)
    dx = x - cx
    dy = y - cy
    cos_r = math.cos(radians)
    sin_r = math.sin(radians)
    return (
        dx * cos_r + dy * sin_r + cx,
        -dx * sin_r + dy * cos_r + cy,
    )


def rotate_bbox(
    bbox: tuple[float, float, float, float],
    degrees: float,
    *,
    cx: float = 0.5,
    cy: float = 0.5,
) -> tuple[float, float, float, float]:
    """Rotate bbox corners and return the axis-aligned union bbox."""
    if degrees == 0.0:
        return bbox

    x0, y0, x1, y1 = bbox
    corners = (
        (x0, y0),
        (x1, y0),
        (x1, y1),
        (x0, y1),
    )
    rotated = [rotate_point(x, y, degrees, cx=cx, cy=cy) for x, y in corners]
    xs = [point[0] for point in rotated]
    ys = [point[1] for point in rotated]
    return min(xs), min(ys), max(xs), max(ys)


def normalize_to_true_north(
    bbox: tuple[float, float, float, float],
    true_north_rotation_deg: float,
) -> tuple[float, float, float, float]:
    """Rotate a bbox into true-north orientation using page metadata."""
    return rotate_bbox(bbox, true_north_rotation_deg)
