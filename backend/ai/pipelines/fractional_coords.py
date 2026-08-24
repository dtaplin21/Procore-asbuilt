"""Normalized 0-1 coordinate helpers without pipeline dependencies."""

from __future__ import annotations


def clamp_fractional(value: float) -> float:
    """Clamp one normalized coordinate to the drawable page range."""
    return max(0.0, min(1.0, float(value)))


def clamp_point_to_page(point: tuple[float, float]) -> tuple[float, float]:
    return (clamp_fractional(point[0]), clamp_fractional(point[1]))


def clamp_fractional_bbox(
    bbox: tuple[float, float, float, float],
    *,
    min_span: float = 0.001,
) -> tuple[float, float, float, float]:
    """Clamp an xyxy bbox to the page; preserve a minimal span when degenerate."""
    x0, y0, x1, y1 = (float(v) for v in bbox)
    x0, x1 = sorted((clamp_fractional(x0), clamp_fractional(x1)))
    y0, y1 = sorted((clamp_fractional(y0), clamp_fractional(y1)))
    if x1 <= x0:
        x1 = min(1.0, x0 + min_span)
    if y1 <= y0:
        y1 = min(1.0, y0 + min_span)
    return (x0, y0, x1, y1)


def bbox_intersects_page(bbox: tuple[float, float, float, float]) -> bool:
    """True when the bbox overlaps any portion of the normalized page."""
    x0, y0, x1, y1 = bbox
    return x1 > 0.0 and y1 > 0.0 and x0 < 1.0 and y0 < 1.0
