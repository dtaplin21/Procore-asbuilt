"""Dash-pattern typing for raster-extracted polylines (Step 4 fallback)."""

from __future__ import annotations

import math
import numpy as np

from ai.pipelines.legend_line_swatch import LegendLineTemplate
from ai.pipelines.line_style_match import signature_distance
from ai.pipelines.pdf_vector_line_extractor import (
    LineStyleKind,
    LineStyleSignature,
    style_signature_as_dict,
)
from ai.pipelines.sheet_entity_graph import SheetLine

_RASTER_CONFIDENCE_FACTOR = 0.85


def _bresenham(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        points.append((x, y))
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy
    return points


def profile_along_polyline(
    binary_ink: np.ndarray,
    points_frac: tuple[tuple[float, float], ...],
    page_w: int,
    page_h: int,
) -> tuple[list[float], list[float]]:
    """Return ink run lengths and gap lengths in pixels along the polyline."""
    if len(points_frac) < 2 or page_w <= 0 or page_h <= 0:
        return [], []

    ink_flags: list[bool] = []
    height, width = binary_ink.shape[:2]
    for (x0f, y0f), (x1f, y1f) in zip(points_frac, points_frac[1:]):
        x0 = int(round(x0f * page_w))
        y0 = int(round(y0f * page_h))
        x1 = int(round(x1f * page_w))
        y1 = int(round(y1f * page_h))
        for x, y in _bresenham(x0, y0, x1, y1):
            if 0 <= x < width and 0 <= y < height:
                ink_flags.append(bool(binary_ink[y, x] > 127))

    if not ink_flags:
        return [], []

    runs: list[float] = []
    gaps: list[float] = []
    current = ink_flags[0]
    length = 1
    for flag in ink_flags[1:]:
        if flag == current:
            length += 1
        else:
            (runs if current else gaps).append(float(length))
            current = flag
            length = 1
    (runs if current else gaps).append(float(length))

    if ink_flags[0] is False and gaps:
        gaps.pop(0)

    return runs, gaps


def signature_from_run_gap_profile(
    runs: list[float],
    gaps: list[float],
    *,
    page_w: int,
    page_h: int,
) -> LineStyleSignature:
    diagonal = math.hypot(float(page_w), float(page_h)) or 1.0
    mean_run = (sum(runs) / len(runs) if runs else 0.0) / diagonal
    mean_gap = (sum(gaps) / len(gaps) if gaps else 0.0) / diagonal

    kind: LineStyleKind = "unknown"
    if not gaps or mean_gap < mean_run * 0.05:
        kind = "solid"
    elif mean_gap > mean_run * 0.3:
        kind = "dashed"
    elif mean_gap > mean_run * 0.1:
        kind = "dash_dot"

    return LineStyleSignature(
        stroke_width_bucket=0.0,
        mean_segment_len_frac=mean_run,
        mean_gap_len_frac=mean_gap,
        segment_count=max(len(runs), 1),
        kind_guess=kind,
    )


def classify_raster_line(
    line: SheetLine,
    binary_ink: np.ndarray,
    page_w: int,
    page_h: int,
    templates: list[LegendLineTemplate] | None = None,
) -> SheetLine:
    runs, gaps = profile_along_polyline(binary_ink, line.points, page_w, page_h)
    style = signature_from_run_gap_profile(runs, gaps, page_w=page_w, page_h=page_h)

    line_type: str | None = None
    legend_line_type_id: int | None = None
    if templates:
        best = min(templates, key=lambda t: signature_distance(style, t.style))
        line_type = best.line_type_name
        legend_line_type_id = best.legend_line_type_id
    elif style.kind_guess != "unknown":
        line_type = style.kind_guess

    style_sig: dict[str, float | str] = dict(style_signature_as_dict(style))
    style_sig["source"] = "raster_profile"

    return SheetLine(
        points=line.points,
        viewport_id=line.viewport_id,
        confidence=float(line.confidence) * _RASTER_CONFIDENCE_FACTOR,
        line_type=line_type,
        source="raster",
        style_signature=style_sig,
        legend_line_type_id=legend_line_type_id,
    )


def classify_raster_lines(
    lines: list[SheetLine],
    binary_ink: np.ndarray,
    page_w: int,
    page_h: int,
    templates: list[LegendLineTemplate] | None = None,
) -> list[SheetLine]:
    return [
        classify_raster_line(line, binary_ink, page_w, page_h, templates=templates)
        for line in lines
    ]
