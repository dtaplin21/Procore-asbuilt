"""Structured digitization output for one drawing page (no CAD required)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ViewportKind = Literal["plan", "section", "detail", "elevation", "profile", "other"]


@dataclass(frozen=True)
class ViewportScale:
    raw_text: str
    real_feet_per_paper_inch: float
    confidence: float
    horizontal: dict[str, Any] | None = None
    vertical: dict[str, Any] | None = None


@dataclass(frozen=True)
class DrawingViewport:
    viewport_id: str
    kind: ViewportKind
    page: int
    bbox_fractional: tuple[float, float, float, float]  # x0,y0,x1,y1
    scale: ViewportScale | None
    source: str  # manual | ocr | detected
    notes: str = ""


@dataclass(frozen=True)
class SheetLabel:
    text: str
    bbox_fractional: tuple[float, float, float, float]
    viewport_id: str | None
    confidence: float


@dataclass(frozen=True)
class SheetSymbol:
    symbol_class: str
    bbox_fractional: tuple[float, float, float, float]
    viewport_id: str | None
    confidence: float
    detector: str  # yolo | manual | contour


@dataclass(frozen=True)
class SheetLine:
    points: tuple[tuple[float, float], ...]
    viewport_id: str | None
    confidence: float
    line_type: str | None = None


@dataclass(frozen=True)
class SheetEntityGraph:
    drawing_id: int
    page: int
    viewports: tuple[DrawingViewport, ...]
    labels: tuple[SheetLabel, ...] = ()
    symbols: tuple[SheetSymbol, ...] = ()
    lines: tuple[SheetLine, ...] = ()
    associations: tuple[dict[str, Any], ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)


def _geometry_center(
    point_or_bbox: tuple[float, ...],
) -> tuple[float, float] | None:
    if len(point_or_bbox) == 2:
        return float(point_or_bbox[0]), float(point_or_bbox[1])
    if len(point_or_bbox) == 4:
        x0, y0, x1, y1 = (float(v) for v in point_or_bbox)
        return (x0 + x1) / 2.0, (y0 + y1) / 2.0
    return None


def _bbox_area(bbox: tuple[float, float, float, float]) -> float:
    x0, y0, x1, y1 = bbox
    return max(x1 - x0, 0.0) * max(y1 - y0, 0.0)


def _contains_point(
    bbox: tuple[float, float, float, float],
    point: tuple[float, float],
) -> bool:
    x0, y0, x1, y1 = bbox
    x, y = point
    return x0 <= x <= x1 and y0 <= y <= y1


def assign_viewport_id(
    point_or_bbox: tuple[float, ...],
    viewports: tuple[DrawingViewport, ...],
) -> str | None:
    """Return viewport_id whose bbox contains the point/center; prefer smallest area on ties.

    NEVER fall back to a fake global viewport for scale conversion — return None if outside all.
    """
    center = _geometry_center(point_or_bbox)
    if center is None or not viewports:
        return None

    containing = [
        viewport
        for viewport in viewports
        if _contains_point(viewport.bbox_fractional, center)
    ]
    if not containing:
        return None

    best = min(containing, key=lambda viewport: _bbox_area(viewport.bbox_fractional))
    return best.viewport_id
