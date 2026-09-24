"""Extract stroked line geometry from PDF vector paths (display / fractional space)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import fitz

from ai.pipelines.landmark_extractor import TITLE_BLOCK_X_MIN, TITLE_BLOCK_Y_MIN
from ai.pipelines.pdf_display_space import pdf_point_to_display_fractional
from ai.pipelines.line_extractor import (
    MERGE_ANGLE_DEG,
    _merge_colinear_segments,
    _polyline_length_frac,
)
from ai.pipelines.sheet_entity_graph import DrawingViewport, SheetLine, assign_viewport_id

LineStyleKind = Literal["solid", "dashed", "dash_dot", "unknown"]

MIN_POLYLINE_LENGTH_FRAC = 0.002
DEFAULT_MAX_CHAINS = 2000


@dataclass(frozen=True)
class PdfVectorSegment:
    x0: float
    y0: float
    x1: float
    y1: float
    stroke_width: float
    color: tuple[int, int, int] | None
    path_index: int
    segment_index: int


@dataclass(frozen=True)
class LineStyleSignature:
    """Comparable fingerprint for legend swatch matching."""

    stroke_width_bucket: float
    mean_segment_len_frac: float
    mean_gap_len_frac: float
    segment_count: int
    kind_guess: LineStyleKind


@dataclass(frozen=True)
class PdfVectorChain:
    points: tuple[tuple[float, float], ...]
    stroke_width: float
    color: tuple[int, int, int] | None
    style: LineStyleSignature
    source_path_indices: tuple[int, ...]


def _in_titleblock_frac(x: float, y: float) -> bool:
    return x >= TITLE_BLOCK_X_MIN and y >= TITLE_BLOCK_Y_MIN


def _parse_stroke_color(color: object) -> tuple[int, int, int] | None:
    if not isinstance(color, (list, tuple)) or len(color) < 3:
        return None
    try:
        components = [float(c) for c in color[:3]]
    except (TypeError, ValueError):
        return None
    def _byte(v: float) -> int:
        return int(min(255, max(0, round(v))))

    r, g, b = components[0], components[1], components[2]
    if max(components) <= 1.0:
        return (_byte(r * 255), _byte(g * 255), _byte(b * 255))
    return (_byte(r), _byte(g), _byte(b))


def extract_pdf_vector_segments(
    pdf_path: str | Path,
    *,
    page: int = 1,
    min_segment_len_frac: float = 0.0005,
) -> list[PdfVectorSegment]:
    doc = fitz.open(str(pdf_path))
    segments: list[PdfVectorSegment] = []
    try:
        if page < 1 or page > doc.page_count:
            raise ValueError(f"page {page} out of range (1..{doc.page_count})")
        page_obj = doc.load_page(page - 1)
        min_len_sq = min_segment_len_frac**2
        for path_index, path in enumerate(page_obj.get_drawings()):
            if path.get("type") != "s":
                continue
            width = float(path.get("width") or 0.0)
            rgb = _parse_stroke_color(path.get("color"))
            seg_i = 0
            for item in path.get("items") or []:
                if not item or item[0] != "l":
                    continue
                _, p0, p1 = item
                x0, y0 = pdf_point_to_display_fractional(page_obj, float(p0.x), float(p0.y))
                x1, y1 = pdf_point_to_display_fractional(page_obj, float(p1.x), float(p1.y))
                if (x0 - x1) ** 2 + (y0 - y1) ** 2 < min_len_sq:
                    continue
                mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
                if _in_titleblock_frac(mx, my):
                    continue
                segments.append(
                    PdfVectorSegment(x0, y0, x1, y1, width, rgb, path_index, seg_i)
                )
                seg_i += 1
    finally:
        doc.close()
    return segments


def _chain_points_from_segments(segments: list[PdfVectorSegment]) -> tuple[tuple[float, float], ...]:
    ordered = sorted(segments, key=lambda s: s.segment_index)
    points: list[tuple[float, float]] = []
    for seg in ordered:
        a = (seg.x0, seg.y0)
        b = (seg.x1, seg.y1)
        if not points:
            points.extend([a, b])
            continue
        last = points[-1]
        da = math.hypot(a[0] - last[0], a[1] - last[1])
        db = math.hypot(b[0] - last[0], b[1] - last[1])
        if da <= db:
            if da > 1e-9:
                points.append(a)
            if math.hypot(b[0] - points[-1][0], b[1] - points[-1][1]) > 1e-9:
                points.append(b)
        else:
            if db > 1e-9:
                points.append(b)
            if math.hypot(a[0] - points[-1][0], a[1] - points[-1][1]) > 1e-9:
                points.append(a)
    # Drop duplicate consecutive vertices.
    deduped: list[tuple[float, float]] = []
    for pt in points:
        if deduped and math.hypot(pt[0] - deduped[-1][0], pt[1] - deduped[-1][1]) < 1e-9:
            continue
        deduped.append(pt)
    return tuple(deduped)


def _style_from_chain(
    points: tuple[tuple[float, float], ...],
    *,
    stroke_width: float,
    micro_segment_count: int,
) -> LineStyleSignature:
    runs: list[float] = []
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        runs.append(math.hypot(x1 - x0, y1 - y0))

    gaps: list[float] = []
    for i in range(len(points) - 2):
        ax, ay = points[i + 1]
        bx, by = points[i + 2]
        gaps.append(math.hypot(bx - ax, by - ay))

    mean_run = sum(runs) / len(runs) if runs else 0.0
    mean_gap = sum(gaps) / len(gaps) if gaps else 0.0
    width_bucket = round(stroke_width, 2)

    kind: LineStyleKind = "unknown"
    if micro_segment_count <= 1 and (not gaps or mean_gap < mean_run * 0.05):
        kind = "solid"
    elif mean_gap > mean_run * 0.3:
        kind = "dashed"
    elif mean_gap > mean_run * 0.1:
        kind = "dash_dot"

    return LineStyleSignature(
        stroke_width_bucket=width_bucket,
        mean_segment_len_frac=mean_run,
        mean_gap_len_frac=mean_gap,
        segment_count=micro_segment_count,
        kind_guess=kind,
    )


def _chain_length(points: tuple[tuple[float, float], ...]) -> float:
    return _polyline_length_frac(points)


def segments_to_chains(
    segments: list[PdfVectorSegment],
    *,
    angle_tol_deg: float = MERGE_ANGLE_DEG,
    dist_tol_frac: float = 0.002,
    min_polyline_length_frac: float = MIN_POLYLINE_LENGTH_FRAC,
) -> list[PdfVectorChain]:
    """Build chains per PDF path, then merge colinear solid two-point chains."""
    by_path: dict[int, list[PdfVectorSegment]] = {}
    for seg in segments:
        by_path.setdefault(seg.path_index, []).append(seg)

    chains: list[PdfVectorChain] = []
    for path_index, path_segments in by_path.items():
        points = _chain_points_from_segments(path_segments)
        if len(points) < 2:
            continue
        if _chain_length(points) < min_polyline_length_frac:
            continue
        width = path_segments[0].stroke_width
        color = path_segments[0].color
        style = _style_from_chain(
            points,
            stroke_width=width,
            micro_segment_count=len(path_segments),
        )
        chains.append(
            PdfVectorChain(
                points=points,
                stroke_width=width,
                color=color,
                style=style,
                source_path_indices=(path_index,),
            )
        )

    merged = _merge_solid_colinear_chains(
        chains,
        angle_tol_deg=angle_tol_deg,
        dist_tol_frac=dist_tol_frac,
        min_polyline_length_frac=min_polyline_length_frac,
    )
    return merged


def _merge_solid_colinear_chains(
    chains: list[PdfVectorChain],
    *,
    angle_tol_deg: float,
    dist_tol_frac: float,
    min_polyline_length_frac: float,
) -> list[PdfVectorChain]:
    """Merge only short solid chains (two vertices) that share stroke width."""
    solids = [c for c in chains if c.style.kind_guess == "solid" and len(c.points) == 2]
    others = [c for c in chains if c not in solids]
    if not solids:
        return chains

    by_key: dict[tuple[float, tuple[int, int, int] | None], list[PdfVectorChain]] = {}
    for chain in solids:
        key = (round(chain.stroke_width, 3), chain.color)
        by_key.setdefault(key, []).append(chain)

    merged_solids: list[PdfVectorChain] = []
    for group in by_key.values():
        segment_tuples = [
            (c.points[0][0], c.points[0][1], c.points[1][0], c.points[1][1]) for c in group
        ]
        polylines = _merge_colinear_segments(
            segment_tuples,
            angle_tol_deg=angle_tol_deg,
            dist_tol_px=dist_tol_frac,
        )
        sample = group[0]
        path_ids = tuple(sorted({pid for c in group for pid in c.source_path_indices}))
        for start, end in polylines:
            points = (start, end)
            if _chain_length(points) < min_polyline_length_frac:
                continue
            style = _style_from_chain(points, stroke_width=sample.stroke_width, micro_segment_count=1)
            merged_solids.append(
                PdfVectorChain(
                    points=points,
                    stroke_width=sample.stroke_width,
                    color=sample.color,
                    style=style,
                    source_path_indices=path_ids,
                )
            )

    return others + merged_solids


def style_signature_as_dict(style: LineStyleSignature) -> dict[str, float | str]:
    return {
        "stroke_width_bucket": style.stroke_width_bucket,
        "mean_segment_len_frac": style.mean_segment_len_frac,
        "mean_gap_len_frac": style.mean_gap_len_frac,
        "segment_count": float(style.segment_count),
        "kind_guess": style.kind_guess,
    }


def extract_pdf_vector_chains(
    pdf_path: str | Path,
    *,
    page: int = 1,
    max_chains: int = DEFAULT_MAX_CHAINS,
) -> list[PdfVectorChain]:
    segments = extract_pdf_vector_segments(pdf_path, page=page)
    chains = segments_to_chains(segments)
    chains.sort(key=lambda c: -_chain_length(c.points))
    return chains[:max_chains]


def chains_to_sheet_lines(
    chains: list[PdfVectorChain],
    viewports: tuple[DrawingViewport, ...],
    *,
    line_type: str | None = None,
    legend_line_type_id: int | None = None,
) -> list[SheetLine]:
    lines: list[SheetLine] = []
    for chain in chains:
        viewport_id = assign_viewport_id(chain.points[0], viewports)
        if line_type is not None:
            resolved_type = line_type
        else:
            resolved_type = chain.style.kind_guess
        lines.append(
            SheetLine(
                points=chain.points,
                viewport_id=viewport_id,
                confidence=0.9,
                line_type=resolved_type if resolved_type != "unknown" else None,
                source="pdf_vector",
                style_signature=style_signature_as_dict(chain.style),
                legend_line_type_id=legend_line_type_id,
            )
        )
    return lines
