"""Derive line-segment scope geometry on master drawing."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from sqlalchemy.orm import Session

from ai.agents.evidence_dossier import EvidenceDossier
from ai.pipelines.station_range_extractor import station_chainage
from ai.pipelines.scope_geometry import (
    ScopeGeometry,
    ScopeKind,
    _station_range,
    bbox_to_scope_rect,
    clamp_fractional_bbox,
    clamp_point_to_page,
    scope_line_segments,
)
from ai.pipelines.survey_point_extractor import extract_stations_from_text
from models.drawing_text_element import DrawingTextElement
from models.models import Drawing
from services.legend_lookup import find_codes_for_term, legend_code_matches_text
from services.location_match_eval import rect_iou
from services.sheet_digitization import load_page_lines

_ANCHOR_PADDING = 0.05
# Distance from the anchor point to a segment, in page fractions.
# A vertex inside the padded search box is not close enough on its own.
_ANCHOR_TOUCH_TOLERANCE = 0.02
_POINT_RECT_SIZE = 0.02
_STATION_NORMALIZE_RE = re.compile(r"\s+")
_PLAN_VIEW_MAX_Y = 0.55
_PLAN_VIEW_MIN_Y = 0.10
# Prefer digitized SheetLine over vision when line confidence meets this floor.
_SHEET_LINE_HIGH_CONFIDENCE = 0.7
# Break ties vs. legacy untyped lines when a typed line already matched legend codes.
_TYPED_SHEET_LINE_MATCH_BONUS = 0.2
# A line this long, in page fractions, is sheet furniture unless the tracer
# was asked for that line type.
LONG_LINE_FRAC = 0.25
_BORDER_SPAN_FRAC = 0.5
_PAGE_EDGE_MARGIN = 0.06
_RECT_CLOSE_EPS = 0.02
_AXIS_EDGE_SLOP = 0.01


@dataclass(frozen=True)
class _MasterTextToken:
    text: str
    bbox: tuple[float, float, float, float]
    page: int


def trace_scope_geometry(
    dossier: EvidenceDossier,
    *,
    anchor_bbox: tuple[float, float, float, float],
    scope_kind: ScopeKind,
    page: int = 1,
    session: Session | None = None,
    master_png_path: Path | None = None,
    source_drawing_id: int | None = None,
) -> ScopeGeometry:
    """Build normalized scope geometry for the matched work area."""
    expanded_anchor = _expand_bbox(anchor_bbox, _ANCHOR_PADDING)
    tokens, trace_on_aux = _resolve_trace_tokens(
        dossier,
        page=page,
        session=session,
        source_drawing_id=source_drawing_id,
    )

    if scope_kind == ScopeKind.STATION_RANGE:
        return _trace_station_range(
            dossier,
            anchor_bbox=anchor_bbox,
            expanded_anchor=expanded_anchor,
            tokens=tokens,
            page=page,
            global_station_search=trace_on_aux,
            source_drawing_id=source_drawing_id if trace_on_aux else None,
        )

    if scope_kind == ScopeKind.UTILITY_LINE:
        station_from, station_to = _station_range(dossier)
        legend_codes = _utility_legend_codes(dossier, session=session)
        trace_meta: dict[str, Any] = {"source": "utility_line_trace"}
        if source_drawing_id is not None:
            trace_meta["source_drawing_id"] = source_drawing_id

        sheet_on_master = _prefer_plan_sheet_line(
            session=session,
            drawing_id=int(dossier.master_drawing_id),
            page=page,
            anchor_bbox=anchor_bbox,
            base_meta=trace_meta,
            source_drawing_id=None,
            legend_codes=legend_codes,
        )
        if sheet_on_master is not None:
            return sheet_on_master

        if trace_on_aux and source_drawing_id is not None:
            sheet_on_aux = _prefer_plan_sheet_line(
                session=session,
                drawing_id=int(source_drawing_id),
                page=page,
                anchor_bbox=anchor_bbox,
                base_meta=trace_meta,
                source_drawing_id=source_drawing_id,
                legend_codes=legend_codes,
            )
            if sheet_on_aux is not None:
                return sheet_on_aux

        if station_from and station_to:
            station_scope = _trace_station_range(
                dossier,
                anchor_bbox=anchor_bbox,
                expanded_anchor=expanded_anchor,
                tokens=tokens,
                page=page,
                global_station_search=trace_on_aux,
                source_drawing_id=source_drawing_id if trace_on_aux else None,
            )
            if (
                station_scope.segments
                and station_scope.meta is not None
                and station_scope.meta.get("source")
                in {"station_labels", "aux_plan_station_labels"}
            ):
                meta = {
                    "source": "aux_plan_station_labels"
                    if trace_on_aux
                    else "station_labels",
                    "stations": station_scope.meta.get("stations", []),
                }
                if trace_on_aux and source_drawing_id is not None:
                    meta["source_drawing_id"] = source_drawing_id
                return ScopeGeometry(
                    page=page,
                    type="line_segments",
                    segments=station_scope.segments,
                    scope_kind=ScopeKind.UTILITY_LINE,
                    meta=meta,
                )

        return _trace_utility_line(
            dossier,
            anchor_bbox=anchor_bbox,
            expanded_anchor=expanded_anchor,
            tokens=tokens,
            page=page,
            session=session,
            master_png_path=master_png_path,
            source_drawing_id=source_drawing_id if trace_on_aux else None,
        )

    if scope_kind in {ScopeKind.AREA, ScopeKind.CORRIDOR}:
        return _trace_region_scope(
            dossier,
            anchor_bbox=anchor_bbox,
            page=page,
            scope_kind=scope_kind,
        )

    if scope_kind == ScopeKind.POINT:
        return _trace_point_scope(
            anchor_bbox=anchor_bbox,
            expanded_anchor=expanded_anchor,
            page=page,
        )

    return bbox_to_scope_rect(anchor_bbox, page=page, scope_kind=scope_kind)


def _trace_station_range(
    dossier: EvidenceDossier,
    *,
    anchor_bbox: tuple[float, float, float, float],
    expanded_anchor: tuple[float, float, float, float],
    tokens: list[_MasterTextToken],
    page: int,
    global_station_search: bool = False,
    source_drawing_id: int | None = None,
) -> ScopeGeometry:
    station_from, station_to = _station_range(dossier)
    target_stations = [
        station
        for station in (_normalize_station(station_from), _normalize_station(station_to))
        if station
    ]

    if global_station_search and len(target_stations) >= 2:
        plan_points = _collect_aux_plan_station_polyline_points(
            tokens,
            station_from=target_stations[0],
            station_to=target_stations[1],
        )
        if len(plan_points) >= 2:
            meta: dict[str, Any] = {
                "source": "aux_plan_station_labels",
                "stations": target_stations,
            }
            if source_drawing_id is not None:
                meta["source_drawing_id"] = source_drawing_id
            return scope_line_segments(
                page=page,
                points=tuple(plan_points),
                scope_kind=ScopeKind.STATION_RANGE,
                meta=meta,
            )

    matched_points: list[tuple[float, float]] = []
    for station in target_stations:
        centroid = _find_station_centroid(
            tokens,
            station,
            expanded_anchor,
            global_search=global_station_search,
        )
        if centroid is not None:
            matched_points.append(centroid)

    if len(matched_points) >= 2:
        meta = {"source": "station_labels", "stations": target_stations}
        if source_drawing_id is not None:
            meta["source_drawing_id"] = source_drawing_id
        return scope_line_segments(
            page=page,
            points=tuple(matched_points),
            scope_kind=ScopeKind.STATION_RANGE,
            meta=meta,
        )

    fallback = _centerline_through_anchor(anchor_bbox, expanded_anchor)
    fallback_meta: dict[str, Any] = {
        "source": "anchor_centerline_fallback",
        "stations": target_stations,
    }
    if source_drawing_id is not None:
        fallback_meta["source_drawing_id"] = source_drawing_id
    return scope_line_segments(
        page=page,
        points=fallback,
        scope_kind=ScopeKind.STATION_RANGE,
        meta=fallback_meta,
    )


def _trace_utility_line(
    dossier: EvidenceDossier,
    *,
    anchor_bbox: tuple[float, float, float, float],
    expanded_anchor: tuple[float, float, float, float],
    tokens: list[_MasterTextToken],
    page: int,
    session: Session | None,
    master_png_path: Path | None = None,
    source_drawing_id: int | None = None,
) -> ScopeGeometry:
    legend_codes = _utility_legend_codes(dossier, session=session)
    label_points = _legend_label_points(
        tokens,
        legend_codes,
        expanded_anchor,
        global_search=source_drawing_id is not None,
    )

    meta: dict[str, Any] = {"source": "utility_line_trace"}
    if source_drawing_id is not None:
        meta["source_drawing_id"] = source_drawing_id
    ambiguous = len(label_points) >= 3
    if ambiguous:
        meta["ambiguous"] = True

    if len(label_points) >= 2:
        ordered = _order_points_along_dominant_axis(label_points, anchor_bbox)
        return scope_line_segments(
            page=page,
            points=tuple(ordered),
            scope_kind=ScopeKind.UTILITY_LINE,
            meta={**meta, "legend_codes": sorted(legend_codes)},
        )

    sheet_line_geometry = _prefer_plan_sheet_line(
        session=session,
        drawing_id=(
            int(source_drawing_id)
            if source_drawing_id is not None
            else int(dossier.master_drawing_id)
        ),
        page=page,
        anchor_bbox=anchor_bbox,
        base_meta={**meta, "legend_codes": sorted(legend_codes)},
        source_drawing_id=source_drawing_id,
        legend_codes=legend_codes,
    )
    if sheet_line_geometry is not None:
        return sheet_line_geometry

    vision_geometry = _vision_trace_fallback(
        dossier,
        anchor_bbox=anchor_bbox,
        expanded_anchor=expanded_anchor,
        page=page,
        master_png_path=master_png_path,
        base_meta={**meta, "legend_codes": sorted(legend_codes)},
    )
    if vision_geometry is not None:
        return vision_geometry

    centerline = _centerline_through_anchor(anchor_bbox, expanded_anchor)
    return scope_line_segments(
        page=page,
        points=centerline,
        scope_kind=ScopeKind.UTILITY_LINE,
        meta={**meta, "legend_codes": sorted(legend_codes), "vision_trace_empty": True},
    )


def resolve_master_sheet_line_scope(
    session: Session,
    *,
    dossier: EvidenceDossier,
    master_drawing_id: int,
    page: int,
    anchor_bbox: tuple[float, float, float, float],
    strict: bool | None = None,
) -> ScopeGeometry:
    """Snap placement to a SheetLine in the viewport that contains the anchor."""
    if strict is None:
        from services.inspection_placement_errors import placement_strict_enabled

        strict = placement_strict_enabled()
    # A segment must reach the anchor point whether or not strict placement is on.
    _ = strict

    legend_codes = _utility_legend_codes(dossier, session=session)
    base_meta: dict[str, Any] = {
        "source": "sheet_line",
        "legend_codes": sorted(legend_codes),
    }
    from services.inspection_placement_errors import (
        INSPECTION_NO_ANCHOR_INTERSECTING_LINE,
        INSPECTION_NO_MASTER_SHEET_LINE,
    )

    candidate, region = _best_plan_sheet_line(
        session,
        drawing_id=int(master_drawing_id),
        page=page,
        anchor_bbox=anchor_bbox,
        legend_codes=legend_codes,
        min_confidence=_SHEET_LINE_HIGH_CONFIDENCE,
        require_anchor_intersection=True,
    )
    if candidate is None:
        near_miss, _near_region = _best_plan_sheet_line(
            session,
            drawing_id=int(master_drawing_id),
            page=page,
            anchor_bbox=anchor_bbox,
            legend_codes=legend_codes,
            min_confidence=_SHEET_LINE_HIGH_CONFIDENCE,
            require_anchor_intersection=False,
        )
        region_note = str(region.get("search_region_note") or "")
        if near_miss is not None:
            raise ValueError(
                f"[{INSPECTION_NO_ANCHOR_INTERSECTING_LINE}] "
                f"No digitized SheetLine passes within {_ANCHOR_TOUCH_TOLERANCE:.2f} "
                f"of the anchor point on master drawing {master_drawing_id} page {page}. "
                f"{region_note}".strip()
            )
        from services.master_sheet_line_inventory import (
            get_master_sheet_line_inventory,
            placement_failure_from_inventory,
        )

        inventory = get_master_sheet_line_inventory(
            session, int(master_drawing_id), page=page
        )
        failure = placement_failure_from_inventory(inventory)
        if failure is not None:
            code, message = failure
            raise ValueError(f"[{code}] {message} {region_note}".strip())
        raise ValueError(
            f"[{INSPECTION_NO_MASTER_SHEET_LINE}] "
            f"No SheetLine in the anchor search region on master drawing "
            f"{master_drawing_id} page {page}. {region_note}".strip()
        )
    points, viewport_id, confidence, anchor_intersects = candidate
    meta = {
        **base_meta,
        **region,
        "viewport_id": viewport_id,
        "sheet_line_confidence": confidence,
        "anchor_intersects_line": anchor_intersects,
    }
    return scope_line_segments(
        page=page,
        points=points,
        scope_kind=ScopeKind.UTILITY_LINE,
        meta=meta,
    )


def _prefer_plan_sheet_line(
    *,
    session: Session | None,
    drawing_id: int,
    page: int,
    anchor_bbox: tuple[float, float, float, float],
    base_meta: dict[str, Any],
    source_drawing_id: int | None,
    legend_codes: set[str] | None = None,
    min_confidence: float = _SHEET_LINE_HIGH_CONFIDENCE,
) -> ScopeGeometry | None:
    """Use a high-confidence SheetLine in the anchor's viewport over vision."""
    if session is None:
        return None
    candidate, region = _best_plan_sheet_line(
        session,
        drawing_id=drawing_id,
        page=page,
        anchor_bbox=anchor_bbox,
        legend_codes=legend_codes or set(),
        min_confidence=min_confidence,
        require_anchor_intersection=True,
    )
    if candidate is None:
        return None
    points, viewport_id, confidence, anchor_intersects = candidate
    meta = {
        **base_meta,
        **region,
        "source": "sheet_line",
        "viewport_id": viewport_id,
        "sheet_line_confidence": confidence,
        "anchor_intersects_line": anchor_intersects,
    }
    if source_drawing_id is not None:
        meta["source_drawing_id"] = source_drawing_id
    return scope_line_segments(
        page=page,
        points=points,
        scope_kind=ScopeKind.UTILITY_LINE,
        meta=meta,
    )


def _line_matches_utility_legend(
    raw: dict[str, Any],
    *,
    legend_codes: set[str],
    session: Session | None,
) -> bool:
    line_type = raw.get("line_type")
    if not line_type:
        return True
    type_id = raw.get("legend_line_type_id")
    if type_id is not None and session is not None:
        from models.legend_reference import DrawingLegendLineType

        row = session.get(DrawingLegendLineType, int(type_id))
        if row is not None:
            code = cast(str | None, row.abbreviation_code)
            if code and code.strip().upper() in {item.strip().upper() for item in legend_codes}:
                return True
    return any(legend_code_matches_text(code, str(line_type)) for code in legend_codes)


def _point_in_bbox(
    point: tuple[float, float],
    bbox: tuple[float, float, float, float],
) -> bool:
    x, y = point
    x0, y0, x1, y1 = bbox
    return x0 <= x <= x1 and y0 <= y <= y1


def _points_inside_bbox(
    points: list[tuple[float, float]],
    bbox: tuple[float, float, float, float],
) -> bool:
    return all(_point_in_bbox(point, bbox) for point in points)


def _bbox_area(bbox: tuple[float, float, float, float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _page_viewports(
    page_graph: dict[str, Any],
) -> list[dict[str, Any]]:
    viewports: list[dict[str, Any]] = []
    for raw in page_graph.get("viewports") or []:
        if not isinstance(raw, dict):
            continue
        viewport_id = raw.get("viewport_id")
        kind = raw.get("kind")
        bb = raw.get("bbox_fractional")
        if not viewport_id or not kind or not isinstance(bb, (list, tuple)) or len(bb) != 4:
            continue
        x0, y0, x1, y1 = (float(v) for v in bb)
        viewports.append(
            {
                "id": str(viewport_id),
                "kind": str(kind),
                "bbox": (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)),
            }
        )
    return viewports


def _anchor_search_region(
    page_graph: dict[str, Any] | None,
    anchor_point: tuple[float, float],
) -> dict[str, Any]:
    """Viewport of the anchor's kind, or the fixed y band when the page has none."""
    viewports = _page_viewports(page_graph or {})
    if not viewports:
        note = (
            "No viewport on this page; searched the fixed y band "
            f"{_PLAN_VIEW_MIN_Y:.2f}–{_PLAN_VIEW_MAX_Y:.2f}."
        )
        return {
            "search_region": "fixed_y_band",
            "search_region_note": note,
            "viewport_ids": set(),
            "bboxes": [],
            "kind": None,
        }
    containing = [
        viewport
        for viewport in viewports
        if _point_in_bbox(anchor_point, viewport["bbox"])
    ]
    if not containing:
        return {
            "search_region": "outside_viewports",
            "search_region_note": (
                "Anchor is outside every viewport; fixed y bands are not used."
            ),
            "viewport_ids": set(),
            "bboxes": [],
            "kind": None,
        }
    chosen = min(containing, key=lambda viewport: _bbox_area(viewport["bbox"]))
    kind = str(chosen["kind"])
    same_kind = [viewport for viewport in viewports if viewport["kind"] == kind]
    return {
        "search_region": "viewport",
        "search_viewport_kind": kind,
        "search_viewport_id": chosen["id"],
        "search_region_note": f"Searched the {kind} viewport.",
        "viewport_ids": {viewport["id"] for viewport in same_kind},
        "bboxes": [viewport["bbox"] for viewport in same_kind],
        "kind": kind,
    }


def _line_in_search_region(
    points: list[tuple[float, float]],
    viewport_id: Any,
    region: dict[str, Any],
) -> bool:
    mode = region.get("search_region")
    if mode == "fixed_y_band":
        mid_y = sum(point[1] for point in points) / len(points)
        return _PLAN_VIEW_MIN_Y <= mid_y <= _PLAN_VIEW_MAX_Y
    if mode != "viewport":
        return False
    viewport_ids = region.get("viewport_ids") or set()
    if viewport_id is not None and str(viewport_id) in viewport_ids:
        return True
    if viewport_id not in (None, ""):
        return False
    return any(_points_inside_bbox(points, bbox) for bbox in region.get("bboxes") or [])


def _point_segment_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    """Distance from a point to a segment, including the endpoints."""
    px, py = point
    ax, ay = start
    bx, by = end
    dx = bx - ax
    dy = by - ay
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _polyline_length(points: list[tuple[float, float]]) -> float:
    return sum(
        math.hypot(x1 - x0, y1 - y0)
        for (x0, y0), (x1, y1) in zip(points, points[1:])
    )


def _closed_rectangle(points: list[tuple[float, float]]) -> list[tuple[float, float]] | None:
    """Four axis-aligned corners, including a repeated closing vertex."""
    if len(points) < 4:
        return None
    ring = list(points)
    x0, y0 = ring[0]
    x1, y1 = ring[-1]
    if math.hypot(x1 - x0, y1 - y0) <= _RECT_CLOSE_EPS:
        ring = ring[:-1]
    if len(ring) != 4:
        return None
    corners = ring + ring[:1]
    for (ax, ay), (bx, by) in zip(corners, corners[1:]):
        if min(abs(bx - ax), abs(by - ay)) > _AXIS_EDGE_SLOP:
            return None
    return ring


def _line_bbox(
    points: list[tuple[float, float]],
) -> tuple[float, float, float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _is_sheet_border(points: list[tuple[float, float]]) -> bool:
    """Closed rectangle covering most of the page, or lying on the page edges."""
    ring = _closed_rectangle(points)
    if ring is None:
        return False
    x0, y0, x1, y1 = _line_bbox(ring)
    width = x1 - x0
    height = y1 - y0
    if width >= _BORDER_SPAN_FRAC and height >= _BORDER_SPAN_FRAC:
        return True
    edges = 0
    if x0 <= _PAGE_EDGE_MARGIN:
        edges += 1
    if y0 <= _PAGE_EDGE_MARGIN:
        edges += 1
    if x1 >= 1.0 - _PAGE_EDGE_MARGIN:
        edges += 1
    if y1 >= 1.0 - _PAGE_EDGE_MARGIN:
        edges += 1
    return edges >= 2


def suspect_line_reason(
    points: list[tuple[float, float]],
    *,
    explicitly_requested: bool,
) -> str | None:
    """Why a digitized line must not be traced, or None when it may be used.

    The sheet border on the audited page is a closed rectangle on the page
    edges. A line at least ``LONG_LINE_FRAC`` long is the same kind of
    furniture unless the tracer was asked for that line's type.
    """
    if _is_sheet_border(points):
        return "sheet_border"
    if _polyline_length(points) >= LONG_LINE_FRAC and not explicitly_requested:
        return "long_line"
    return None


def _line_explicitly_requested(
    raw: dict[str, Any],
    *,
    legend_codes: set[str],
    session: Session | None,
) -> bool:
    """True when this line's type is one the tracer was asked to find."""
    has_type = bool(raw.get("line_type")) or raw.get("legend_line_type_id") is not None
    if not has_type:
        return False
    return _line_matches_utility_legend(raw, legend_codes=legend_codes, session=session)


def _line_anchor_distance(
    points: list[tuple[float, float]],
    anchor_point: tuple[float, float],
) -> float:
    return min(
        _point_segment_distance(anchor_point, points[index], points[index + 1])
        for index in range(len(points) - 1)
    )


def _best_plan_sheet_line(
    session: Session,
    *,
    drawing_id: int,
    page: int,
    anchor_bbox: tuple[float, float, float, float],
    legend_codes: set[str] | None = None,
    min_confidence: float = _SHEET_LINE_HIGH_CONFIDENCE,
    require_anchor_intersection: bool = True,
) -> tuple[
    tuple[tuple[tuple[float, float], ...], str | None, float, bool] | None,
    dict[str, Any],
]:
    empty_region = {
        "search_region": "fixed_y_band",
        "search_region_note": (
            "No viewport on this page; searched the fixed y band "
            f"{_PLAN_VIEW_MIN_Y:.2f}–{_PLAN_VIEW_MAX_Y:.2f}."
        ),
    }
    drawing = session.get(Drawing, int(drawing_id))
    if drawing is None:
        return None, empty_region
    stats = cast(dict[str, Any] | None, drawing.index_stats_json)
    if not isinstance(stats, dict):
        return None, empty_region
    graphs = stats.get("sheetEntityGraph")
    if not isinstance(graphs, dict):
        return None, empty_region
    page_graph = graphs.get(str(page))
    if not isinstance(page_graph, dict):
        return None, empty_region

    ax0, ay0, ax1, ay1 = anchor_bbox
    anchor_point = ((ax0 + ax1) / 2.0, (ay0 + ay1) / 2.0)
    region = _anchor_search_region(page_graph, anchor_point)
    public_region = {
        key: value
        for key, value in region.items()
        if key not in {"viewport_ids", "bboxes", "kind"}
    }

    codes = legend_codes or set()
    best: tuple[tuple[tuple[float, float], ...], str | None, float, float, bool] | None = None
    for raw in load_page_lines(page_graph):
        if not isinstance(raw, dict):
            continue
        try:
            confidence = float(raw.get("confidence") or 0.0)
        except (TypeError, ValueError):
            continue
        if confidence < min_confidence:
            continue
        if not _line_matches_utility_legend(raw, legend_codes=codes, session=session):
            continue
        points_raw = raw.get("points")
        if not isinstance(points_raw, (list, tuple)) or len(points_raw) < 2:
            continue
        points: list[tuple[float, float]] = []
        for pt in points_raw:
            if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                continue
            points.append((float(pt[0]), float(pt[1])))
        if len(points) < 2:
            continue
        if suspect_line_reason(
            points,
            explicitly_requested=_line_explicitly_requested(
                raw, legend_codes=codes, session=session
            ),
        ):
            continue
        viewport_id = raw.get("viewport_id")
        if not _line_in_search_region(points, viewport_id, region):
            continue
        distance = _line_anchor_distance(points, anchor_point)
        touches = distance <= _ANCHOR_TOUCH_TOLERANCE
        if require_anchor_intersection and not touches:
            continue
        score = distance - confidence
        if raw.get("line_type"):
            score -= _TYPED_SHEET_LINE_MATCH_BONUS
        if best is None or score < best[3]:
            best = (tuple(points), str(viewport_id) if viewport_id else None, confidence, score, touches)

    if best is None:
        return None, public_region
    return (best[0], best[1], best[2], best[4]), public_region


def _vision_trace_fallback(
    dossier: EvidenceDossier,
    *,
    anchor_bbox: tuple[float, float, float, float],
    expanded_anchor: tuple[float, float, float, float],
    page: int,
    master_png_path: Path | None,
    base_meta: dict[str, Any],
) -> ScopeGeometry | None:
    if master_png_path is None or not master_png_path.is_file():
        return None

    from ai.pipelines.vision_location_reasoner import (
        build_dossier_summary,
        reason_over_master_crop,
    )

    vision = reason_over_master_crop(
        master_png_path=master_png_path,
        dossier_summary=build_dossier_summary(dossier),
        candidate_bboxes=[anchor_bbox],
        task="trace_line",
    )
    if not vision.polyline_points or len(vision.polyline_points) < 2:
        return None

    clamped = tuple(
        _clamp_point(point, expanded_anchor) for point in vision.polyline_points
    )
    meta = {
        **base_meta,
        "source": "vision_trace",
        "vision_confidence": vision.confidence,
    }
    if vision.rationale:
        meta["vision_rationale"] = vision.rationale
    if vision.highlight_detected:
        meta["highlight_detected"] = True

    return scope_line_segments(
        page=page,
        points=clamped,
        scope_kind=ScopeKind.UTILITY_LINE,
        meta=meta,
    )


def _trace_region_scope(
    dossier: EvidenceDossier,
    *,
    anchor_bbox: tuple[float, float, float, float],
    page: int,
    scope_kind: ScopeKind,
) -> ScopeGeometry:
    best_region = _best_region_for_anchor(dossier, anchor_bbox)
    if best_region is not None:
        region_bbox = best_region.bbox_on_master.to_fractional()
        return bbox_to_scope_rect(region_bbox, page=page, scope_kind=scope_kind)

    return bbox_to_scope_rect(anchor_bbox, page=page, scope_kind=scope_kind)


def _trace_point_scope(
    *,
    anchor_bbox: tuple[float, float, float, float],
    expanded_anchor: tuple[float, float, float, float],
    page: int,
) -> ScopeGeometry:
    center = _centroid(anchor_bbox)
    clamped = _clamp_point(center, expanded_anchor)
    half = _POINT_RECT_SIZE / 2
    return ScopeGeometry(
        page=page,
        type="rect",
        x=max(0.0, clamped[0] - half),
        y=max(0.0, clamped[1] - half),
        width=_POINT_RECT_SIZE,
        height=_POINT_RECT_SIZE,
        scope_kind=ScopeKind.POINT,
        meta={"source": "point_anchor"},
    )


def _load_drawing_text_tokens(
    session: Session,
    drawing_id: int,
    *,
    page: int,
) -> list[_MasterTextToken]:
    tokens: list[_MasterTextToken] = []
    seen: set[tuple[str, tuple[float, float, float, float]]] = set()
    rows: list[DrawingTextElement] = (
        session.query(DrawingTextElement)
        .filter(DrawingTextElement.master_drawing_id == drawing_id)
        .filter(DrawingTextElement.page == page)
        .order_by(DrawingTextElement.id.asc())
        .all()
    )
    for row in rows:
        bbox_json = cast(dict[str, float], row.bbox_json)
        token = _MasterTextToken(
            text=str(row.text),
            bbox=_bbox_from_json(bbox_json),
            page=page,
        )
        key = (token.text, token.bbox)
        if key not in seen:
            seen.add(key)
            tokens.append(token)
    return tokens


def _resolve_trace_tokens(
    dossier: EvidenceDossier,
    *,
    page: int,
    session: Session | None,
    source_drawing_id: int | None,
) -> tuple[list[_MasterTextToken], bool]:
    master_drawing_id = dossier.master_drawing_id
    if (
        source_drawing_id is not None
        and source_drawing_id != master_drawing_id
        and session is not None
    ):
        return (
            _load_drawing_text_tokens(session, source_drawing_id, page=page),
            True,
        )
    return _load_master_text_tokens(dossier, page=page, session=session), False


def _load_master_text_tokens(
    dossier: EvidenceDossier,
    *,
    page: int,
    session: Session | None,
) -> list[_MasterTextToken]:
    tokens: list[_MasterTextToken] = []
    seen: set[tuple[str, tuple[float, float, float, float]]] = set()

    if session is not None:
        rows: list[DrawingTextElement] = (
            session.query(DrawingTextElement)
            .filter(DrawingTextElement.master_drawing_id == dossier.master_drawing_id)
            .filter(DrawingTextElement.page == page)
            .order_by(DrawingTextElement.id.asc())
            .all()
        )
        for row in rows:
            bbox_json = cast(dict[str, float], row.bbox_json)
            token = _MasterTextToken(
                text=str(row.text),
                bbox=_bbox_from_json(bbox_json),
                page=page,
            )
            key = (token.text, token.bbox)
            if key not in seen:
                seen.add(key)
                tokens.append(token)

    for tile in dossier.master_context.candidate_tiles:
        if tile.page != page or tile.bbox_normalized is None:
            continue
        token = _MasterTextToken(
            text=tile.text,
            bbox=tile.bbox_normalized,
            page=page,
        )
        key = (token.text, token.bbox)
        if key not in seen:
            seen.add(key)
            tokens.append(token)

    return tokens


def _collect_aux_plan_station_polyline_points(
    tokens: list[_MasterTextToken],
    *,
    station_from: str,
    station_to: str,
    max_plan_y: float = _PLAN_VIEW_MAX_Y,
    min_plan_y: float = _PLAN_VIEW_MIN_Y,
) -> list[tuple[float, float]]:
    """Chain plan-view station/structure OCR into a left-to-right utility polyline."""
    lo = station_chainage(station_from)
    hi = station_chainage(station_to)
    chainage_hits: dict[float, tuple[float, float]] = {}
    structure_points: list[tuple[float, tuple[float, float]]] = []

    for token in tokens:
        centroid = clamp_point_to_page(_centroid(token.bbox))
        if centroid[1] > max_plan_y or centroid[1] < min_plan_y:
            continue

        token_stations = extract_stations_from_text(token.text)
        for extracted in token_stations:
            chainage = station_chainage(_normalize_station(extracted) or extracted)
            if lo <= chainage <= hi:
                chainage_hits[chainage] = centroid

        upper = token.text.upper()
        if token_stations:
            continue
        if any(marker in upper for marker in ("SSMH", "STA.", "STA ", "SAN. MH", "SAN MH")):
            structure_points.append((centroid[0], centroid))

    if len(chainage_hits) < 2 and structure_points:
        structure_points.sort(key=lambda item: item[0])
        if chainage_hits:
            end_point = chainage_hits[max(chainage_hits.keys())]
            end_x = end_point[0]
            start_candidates = [pt for x, pt in structure_points if x <= end_x]
            if start_candidates:
                chainage_hits.setdefault(lo, start_candidates[0])
        elif len(structure_points) >= 2:
            chainage_hits[lo] = structure_points[0][1]
            chainage_hits[hi] = structure_points[-1][1]

    if len(chainage_hits) < 2:
        return []

    start_point = chainage_hits[min(chainage_hits.keys())]
    end_point = chainage_hits[max(chainage_hits.keys())]
    min_x = min(start_point[0], end_point[0])
    max_x = max(start_point[0], end_point[0])

    ordered: list[tuple[float, float]] = [start_point]
    for x, point in sorted(structure_points, key=lambda item: item[0]):
        if min_x < x < max_x and point not in ordered:
            ordered.append(point)
    if end_point not in ordered:
        ordered.append(end_point)

    if len(ordered) < 2:
        ordered = [start_point, end_point]

    return ordered


def _find_station_centroid(
    tokens: list[_MasterTextToken],
    station: str,
    expanded_anchor: tuple[float, float, float, float],
    *,
    global_search: bool = False,
) -> tuple[float, float] | None:
    for token in tokens:
        if not global_search and not _bbox_intersects(token.bbox, expanded_anchor):
            continue
        for extracted in extract_stations_from_text(token.text):
            if _normalize_station(extracted) == station:
                centroid = _centroid(token.bbox)
                if global_search:
                    return clamp_point_to_page(centroid)
                return _clamp_point(centroid, expanded_anchor)
    return None


def _utility_legend_codes(
    dossier: EvidenceDossier,
    *,
    session: Session | None,
) -> set[str]:
    codes: set[str] = {
        str(code).strip().upper()
        for code in dossier.master_context.legend_codes_near_candidates
        if str(code).strip()
    }
    if session is None:
        return codes

    for clue in dossier.expanded_clues:
        for value in clue.expanded_values:
            for code in find_codes_for_term(session, value, dossier.project_id):
                if code.strip():
                    codes.add(code.strip().upper())
    return codes


def _legend_label_points(
    tokens: list[_MasterTextToken],
    legend_codes: set[str],
    expanded_anchor: tuple[float, float, float, float],
    *,
    global_search: bool = False,
) -> list[tuple[float, float]]:
    if not legend_codes:
        return []

    points: list[tuple[float, float]] = []
    for token in tokens:
        if not global_search and not _bbox_intersects(token.bbox, expanded_anchor):
            continue
        if not any(legend_code_matches_text(code, token.text) for code in legend_codes):
            continue
        if global_search:
            points.append(clamp_point_to_page(_centroid(token.bbox)))
        else:
            points.append(_clamp_point(_centroid(token.bbox), expanded_anchor))
    return points


def _best_region_for_anchor(
    dossier: EvidenceDossier,
    anchor_bbox: tuple[float, float, float, float],
):
    anchor_rect = _xyxy_to_xywh(anchor_bbox)
    best_region = None
    best_iou = 0.0
    for region in dossier.master_context.regions:
        region_rect = _xyxy_to_xywh(region.bbox_on_master.to_fractional())
        overlap = rect_iou(anchor_rect, region_rect)
        if overlap > best_iou:
            best_iou = overlap
            best_region = region
    if best_iou >= 0.05:
        return best_region
    return None


def _centerline_through_anchor(
    anchor_bbox: tuple[float, float, float, float],
    expanded_anchor: tuple[float, float, float, float],
) -> tuple[tuple[float, float], tuple[float, float]]:
    x0, y0, x1, y1 = anchor_bbox
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    if (x1 - x0) >= (y1 - y0):
        return (
            _clamp_point((x0, cy), expanded_anchor),
            _clamp_point((x1, cy), expanded_anchor),
        )
    return (
        _clamp_point((cx, y0), expanded_anchor),
        _clamp_point((cx, y1), expanded_anchor),
    )


def _order_points_along_dominant_axis(
    points: list[tuple[float, float]],
    anchor_bbox: tuple[float, float, float, float],
) -> list[tuple[float, float]]:
    x0, y0, x1, y1 = anchor_bbox
    if (x1 - x0) >= (y1 - y0):
        return sorted(points, key=lambda point: point[0])
    return sorted(points, key=lambda point: point[1])


def _expand_bbox(
    bbox: tuple[float, float, float, float],
    padding: float,
) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = clamp_fractional_bbox(bbox)
    return clamp_fractional_bbox(
        (
            x0 - padding,
            y0 - padding,
            x1 + padding,
            y1 + padding,
        )
    )


def _clamp_point(
    point: tuple[float, float],
    bbox: tuple[float, float, float, float],
) -> tuple[float, float]:
    x0, y0, x1, y1 = clamp_fractional_bbox(bbox)
    x, y = point
    return clamp_point_to_page((max(x0, min(x1, x)), max(y0, min(y1, y))))


def _centroid(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    x0, y0, x1, y1 = bbox
    return ((x0 + x1) / 2, (y0 + y1) / 2)


def _bbox_intersects(
    inner: tuple[float, float, float, float],
    outer: tuple[float, float, float, float],
) -> bool:
    ix0 = max(inner[0], outer[0])
    iy0 = max(inner[1], outer[1])
    ix1 = min(inner[2], outer[2])
    iy1 = min(inner[3], outer[3])
    return ix1 > ix0 and iy1 > iy0


def _bbox_from_json(bbox_json: dict[str, float]) -> tuple[float, float, float, float]:
    return (
        float(bbox_json["x0"]),
        float(bbox_json["y0"]),
        float(bbox_json["x1"]),
        float(bbox_json["y1"]),
    )


def _normalize_station(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _STATION_NORMALIZE_RE.sub("", value.strip().upper())
    return normalized or None


def _xyxy_to_xywh(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = bbox
    return (x0, y0, max(x1 - x0, 0.0), max(y1 - y0, 0.0))
