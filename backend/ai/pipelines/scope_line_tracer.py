"""Derive line-segment scope geometry on master drawing."""

from __future__ import annotations

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
from services.legend_lookup import find_codes_for_term
from services.location_match_eval import rect_iou

_ANCHOR_PADDING = 0.05
_POINT_RECT_SIZE = 0.02
_STATION_NORMALIZE_RE = re.compile(r"\s+")
_PLAN_VIEW_MAX_Y = 0.55
_PLAN_VIEW_MIN_Y = 0.10
# Prefer digitized SheetLine over vision when line confidence meets this floor.
_SHEET_LINE_HIGH_CONFIDENCE = 0.7
# Break ties vs. legacy untyped lines when a typed line already matched legend codes.
_TYPED_SHEET_LINE_MATCH_BONUS = 0.2
# Full plan band used when anchor-local SheetLine search misses.
_MASTER_PLAN_PLACEMENT_ANCHOR = (0.12, 0.22, 0.92, 0.78)


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
            expanded_anchor=expanded_anchor,
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
                expanded_anchor=expanded_anchor,
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
        expanded_anchor=expanded_anchor,
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
    """Snap inspection placement to a digitized SheetLine on the master plan only."""
    if strict is None:
        from services.inspection_placement_errors import placement_strict_enabled

        strict = placement_strict_enabled()

    legend_codes = _utility_legend_codes(dossier, session=session)
    base_meta: dict[str, Any] = {
        "source": "sheet_line",
        "legend_codes": sorted(legend_codes),
    }
    if strict:
        search_passes: list[
            tuple[tuple[float, float, float, float], float, bool, str | None]
        ] = [
            (
                _expand_bbox(anchor_bbox, _ANCHOR_PADDING),
                _SHEET_LINE_HIGH_CONFIDENCE,
                True,
                None,
            ),
        ]
    else:
        search_passes = [
            (_expand_bbox(anchor_bbox, _ANCHOR_PADDING), _SHEET_LINE_HIGH_CONFIDENCE, True, None),
            (
                _expand_bbox(anchor_bbox, _ANCHOR_PADDING * 4.0),
                _SHEET_LINE_HIGH_CONFIDENCE,
                True,
                "wide_anchor",
            ),
            (_MASTER_PLAN_PLACEMENT_ANCHOR, 0.45, True, "plan_corridor"),
            (_MASTER_PLAN_PLACEMENT_ANCHOR, 0.25, True, "plan_corridor_relaxed"),
            (_MASTER_PLAN_PLACEMENT_ANCHOR, 0.15, False, "plan_any_line"),
        ]
    for expanded, min_confidence, use_legend, search_tag in search_passes:
        candidate = _best_plan_sheet_line(
            session,
            drawing_id=int(master_drawing_id),
            page=page,
            expanded_anchor=expanded,
            legend_codes=legend_codes if use_legend else set(),
            min_confidence=min_confidence,
        )
        if candidate is None:
            continue
        points, viewport_id, confidence = candidate
        meta = {
            **base_meta,
            "viewport_id": viewport_id,
            "sheet_line_confidence": confidence,
        }
        if search_tag:
            meta["sheet_line_search"] = search_tag
        return scope_line_segments(
            page=page,
            points=points,
            scope_kind=ScopeKind.UTILITY_LINE,
            meta=meta,
        )
    from services.master_sheet_line_inventory import (
        get_master_sheet_line_inventory,
        placement_failure_from_inventory,
    )
    from services.inspection_placement_errors import INSPECTION_NO_MASTER_SHEET_LINE

    inventory = get_master_sheet_line_inventory(
        session, int(master_drawing_id), page=page
    )
    failure = placement_failure_from_inventory(inventory)
    if failure is not None:
        code, message = failure
        raise ValueError(f"[{code}] {message}")
    raise ValueError(
        f"[{INSPECTION_NO_MASTER_SHEET_LINE}] "
        f"No plan SheetLine on master drawing {master_drawing_id} page {page} for placement"
    )


def _prefer_plan_sheet_line(
    *,
    session: Session | None,
    drawing_id: int,
    page: int,
    expanded_anchor: tuple[float, float, float, float],
    base_meta: dict[str, Any],
    source_drawing_id: int | None,
    legend_codes: set[str] | None = None,
    min_confidence: float = _SHEET_LINE_HIGH_CONFIDENCE,
) -> ScopeGeometry | None:
    """Use high-confidence SheetLine polylines inside plan viewports over vision."""
    if session is None:
        return None
    candidate = _best_plan_sheet_line(
        session,
        drawing_id=drawing_id,
        page=page,
        expanded_anchor=expanded_anchor,
        legend_codes=legend_codes or set(),
        min_confidence=min_confidence,
    )
    if candidate is None:
        return None
    points, viewport_id, confidence = candidate
    meta = {
        **base_meta,
        "source": "sheet_line",
        "viewport_id": viewport_id,
        "sheet_line_confidence": confidence,
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
            if code and code in legend_codes:
                return True
    upper = str(line_type).upper()
    return any(code in upper for code in legend_codes)


def _best_plan_sheet_line(
    session: Session,
    *,
    drawing_id: int,
    page: int,
    expanded_anchor: tuple[float, float, float, float],
    legend_codes: set[str] | None = None,
    min_confidence: float = _SHEET_LINE_HIGH_CONFIDENCE,
) -> tuple[tuple[tuple[float, float], ...], str | None, float] | None:
    drawing = session.get(Drawing, int(drawing_id))
    if drawing is None:
        return None
    stats = cast(dict[str, Any] | None, drawing.index_stats_json)
    if not isinstance(stats, dict):
        return None
    graphs = stats.get("sheetEntityGraph")
    if not isinstance(graphs, dict):
        return None
    page_graph = graphs.get(str(page))
    if not isinstance(page_graph, dict):
        return None

    plan_ids = {
        str(vp.get("viewport_id"))
        for vp in (page_graph.get("viewports") or [])
        if isinstance(vp, dict) and vp.get("kind") == "plan" and vp.get("viewport_id")
    }
    plan_bbox: tuple[float, float, float, float] | None = None
    for vp in page_graph.get("viewports") or []:
        if not isinstance(vp, dict) or vp.get("kind") != "plan":
            continue
        bb = vp.get("bbox_fractional")
        if isinstance(bb, (list, tuple)) and len(bb) == 4:
            plan_bbox = tuple(float(v) for v in bb)
            break

    def _line_in_plan_area(raw_line: dict[str, Any]) -> bool:
        points_raw = raw_line.get("points")
        if not isinstance(points_raw, (list, tuple)) or len(points_raw) < 2:
            return False
        ys: list[float] = []
        for pt in points_raw:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                ys.append(float(pt[1]))
        if not ys:
            return False
        mid_y = sum(ys) / len(ys)
        if plan_bbox is not None:
            return plan_bbox[1] <= mid_y <= plan_bbox[3]
        return _PLAN_VIEW_MIN_Y <= mid_y <= _PLAN_VIEW_MAX_Y

    codes = legend_codes or set()
    ax0, ay0, ax1, ay1 = expanded_anchor
    anchor_cx = (ax0 + ax1) / 2.0
    anchor_cy = (ay0 + ay1) / 2.0

    best: tuple[tuple[tuple[float, float], ...], str | None, float, float] | None = None
    for raw in page_graph.get("lines") or []:
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
        viewport_id = raw.get("viewport_id")
        if plan_ids:
            if viewport_id is None or str(viewport_id) not in plan_ids:
                continue
        elif not _line_in_plan_area(raw):
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
        mid_x = sum(p[0] for p in points) / len(points)
        mid_y = sum(p[1] for p in points) / len(points)
        intersects = any(ax0 <= px <= ax1 and ay0 <= py <= ay1 for px, py in points)
        # Prefer lines that intersect the anchor; otherwise nearest midpoint.
        distance = 0.0 if intersects else ((mid_x - anchor_cx) ** 2 + (mid_y - anchor_cy) ** 2)
        score = distance - confidence  # lower is better
        if raw.get("line_type"):
            score -= _TYPED_SHEET_LINE_MATCH_BONUS
        if best is None or score < best[3]:
            best = (tuple(points), str(viewport_id), confidence, score)

    if best is None:
        return None
    return best[0], best[1], best[2]


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
        upper = token.text.upper()
        if not any(re.search(rf"\b{re.escape(code)}\b", upper) for code in legend_codes):
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
