"""Derive polyline scope geometry on master drawing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from sqlalchemy.orm import Session

from ai.agents.evidence_dossier import EvidenceDossier
from ai.pipelines.scope_geometry import (
    ScopeGeometry,
    ScopeKind,
    _evidence_survey_points,
    _station_range,
    bbox_to_scope_rect,
)
from ai.pipelines.survey_point_extractor import extract_stations_from_text
from models.drawing_text_element import DrawingTextElement
from services.legend_lookup import find_codes_for_term
from services.location_match_eval import rect_iou

_ANCHOR_PADDING = 0.05
_POINT_RECT_SIZE = 0.02
_STATION_NORMALIZE_RE = re.compile(r"\s+")


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
) -> ScopeGeometry:
    """Build normalized scope geometry for the matched work area."""
    expanded_anchor = _expand_bbox(anchor_bbox, _ANCHOR_PADDING)
    tokens = _load_master_text_tokens(dossier, page=page, session=session)

    if scope_kind == ScopeKind.STATION_RANGE:
        return _trace_station_range(
            dossier,
            anchor_bbox=anchor_bbox,
            expanded_anchor=expanded_anchor,
            tokens=tokens,
            page=page,
        )

    if scope_kind == ScopeKind.UTILITY_LINE:
        endpoint_positions = _survey_endpoint_positions(
            dossier,
            expanded_anchor=expanded_anchor,
        )
        if endpoint_positions is not None:
            return ScopeGeometry(
                page=page,
                type="polyline",
                points=endpoint_positions,
                scope_kind=ScopeKind.UTILITY_LINE,
                meta={"source": "survey_endpoints"},
            )
        return _trace_utility_line(
            dossier,
            anchor_bbox=anchor_bbox,
            expanded_anchor=expanded_anchor,
            tokens=tokens,
            page=page,
            session=session,
            master_png_path=master_png_path,
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
) -> ScopeGeometry:
    station_from, station_to = _station_range(dossier)
    target_stations = [
        station
        for station in (_normalize_station(station_from), _normalize_station(station_to))
        if station
    ]

    matched_points: list[tuple[float, float]] = []
    for station in target_stations:
        centroid = _find_station_centroid(tokens, station, expanded_anchor)
        if centroid is not None:
            matched_points.append(centroid)

    if len(matched_points) >= 2:
        return ScopeGeometry(
            page=page,
            type="polyline",
            points=tuple(matched_points),
            scope_kind=ScopeKind.STATION_RANGE,
            meta={"source": "station_labels", "stations": target_stations},
        )

    fallback = _centerline_through_anchor(anchor_bbox, expanded_anchor)
    return ScopeGeometry(
        page=page,
        type="polyline",
        points=fallback,
        scope_kind=ScopeKind.STATION_RANGE,
        meta={"source": "anchor_centerline_fallback", "stations": target_stations},
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
) -> ScopeGeometry:
    legend_codes = _utility_legend_codes(dossier, session=session)
    label_points = _legend_label_points(tokens, legend_codes, expanded_anchor)

    meta: dict[str, Any] = {"source": "utility_line_trace"}
    ambiguous = len(label_points) >= 3
    if ambiguous:
        meta["ambiguous"] = True

    if len(label_points) >= 2:
        ordered = _order_points_along_dominant_axis(label_points, anchor_bbox)
        return ScopeGeometry(
            page=page,
            type="polyline",
            points=tuple(ordered),
            scope_kind=ScopeKind.UTILITY_LINE,
            meta={**meta, "legend_codes": sorted(legend_codes)},
        )

    centerline = _centerline_through_anchor(anchor_bbox, expanded_anchor)
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

    return ScopeGeometry(
        page=page,
        type="polyline",
        points=centerline,
        scope_kind=ScopeKind.UTILITY_LINE,
        meta={**meta, "legend_codes": sorted(legend_codes), "vision_deferred": True},
    )


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

    return ScopeGeometry(
        page=page,
        type="polyline",
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


def _find_station_centroid(
    tokens: list[_MasterTextToken],
    station: str,
    expanded_anchor: tuple[float, float, float, float],
) -> tuple[float, float] | None:
    for token in tokens:
        if not _bbox_intersects(token.bbox, expanded_anchor):
            continue
        for extracted in extract_stations_from_text(token.text):
            if _normalize_station(extracted) == station:
                return _clamp_point(_centroid(token.bbox), expanded_anchor)
    return None


def _survey_endpoint_positions(
    dossier: EvidenceDossier,
    *,
    expanded_anchor: tuple[float, float, float, float],
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    points = _evidence_survey_points(dossier)
    if len(points) < 2:
        return None

    positions: list[tuple[float, float]] = []
    for item in points[:2]:
        label_bbox = item.get("label_bbox_json")
        if isinstance(label_bbox, dict):
            centroid = _centroid(_bbox_from_json(cast(dict[str, float], label_bbox)))
        else:
            return None
        positions.append(_clamp_point(centroid, expanded_anchor))

    return (positions[0], positions[1])


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
) -> list[tuple[float, float]]:
    if not legend_codes:
        return []

    points: list[tuple[float, float]] = []
    for token in tokens:
        if not _bbox_intersects(token.bbox, expanded_anchor):
            continue
        upper = token.text.upper()
        if not any(re.search(rf"\b{re.escape(code)}\b", upper) for code in legend_codes):
            continue
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
    x0, y0, x1, y1 = bbox
    return (
        max(0.0, x0 - padding),
        max(0.0, y0 - padding),
        min(1.0, x1 + padding),
        min(1.0, y1 + padding),
    )


def _clamp_point(
    point: tuple[float, float],
    bbox: tuple[float, float, float, float],
) -> tuple[float, float]:
    x0, y0, x1, y1 = bbox
    x, y = point
    return (max(x0, min(x1, x)), max(y0, min(y1, y)))


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
