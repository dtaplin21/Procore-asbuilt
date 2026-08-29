"""Compute master ↔ auxiliary registration from shared survey control points."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Sequence, cast

from sqlalchemy.orm import Session

from ai.pipelines.coordinate_frame import rotate_point
from ai.pipelines.drawing_location_resolver import RegistrationTransform
from ai.pipelines.scope_geometry import clamp_point_to_page
from ai.pipelines.survey_point_extractor import (
    extract_stations_from_text,
    is_placed_survey_label_bbox,
)
from models.drawing_survey_point import DrawingSurveyPoint
from models.drawing_viewport import DrawingViewport as DrawingViewportRow
from models.models import Drawing


@dataclass(frozen=True)
class ControlPointPair:
    aux_xy: tuple[float, float]
    master_xy: tuple[float, float]
    northing: float | None = None
    easting: float | None = None
    station: str | None = None
    pairing_method: str = "ne"


_STATION_NORMALIZE_RE = re.compile(r"\s+")


def _normalize_station(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _STATION_NORMALIZE_RE.sub("", value.strip().upper())
    return normalized or None


def _load_plan_viewport_bboxes(
    session: Session,
    drawing_id: int,
    *,
    page: int = 1,
) -> list[tuple[float, float, float, float]]:
    """Return fractional bboxes for kind=plan viewports (empty if none seeded)."""
    rows = (
        session.query(DrawingViewportRow)
        .filter(
            DrawingViewportRow.drawing_id == int(drawing_id),
            DrawingViewportRow.page == int(page),
            DrawingViewportRow.kind == "plan",
        )
        .all()
    )
    bboxes: list[tuple[float, float, float, float]] = []
    for row in rows:
        bbox = cast(dict[str, Any], row.bbox_json)
        bboxes.append(
            (
                float(bbox["x0"]),
                float(bbox["y0"]),
                float(bbox["x1"]),
                float(bbox["y1"]),
            )
        )
    return bboxes


def _point_in_any_bbox(
    point: tuple[float, float],
    bboxes: Sequence[tuple[float, float, float, float]],
) -> bool:
    x, y = point
    for x0, y0, x1, y1 in bboxes:
        if x0 <= x <= x1 and y0 <= y <= y1:
            return True
    return False


def _filter_survey_rows_to_plan_viewports(
    session: Session,
    rows: Sequence[DrawingSurveyPoint],
    *,
    drawing_id: int,
) -> list[DrawingSurveyPoint]:
    """Keep survey controls inside plan viewports when viewports are seeded.

    Section/profile geometry must never silently drive plan registration.
    If no plan viewport exists for the drawing, keep all rows (legacy behavior).
    """
    plan_bboxes = _load_plan_viewport_bboxes(session, drawing_id, page=1)
    if not plan_bboxes:
        return list(rows)

    kept: list[DrawingSurveyPoint] = []
    for row in rows:
        if int(row.page) != 1:
            # Multi-page: only keep if that page has a plan viewport containing the point.
            page_bboxes = _load_plan_viewport_bboxes(
                session, drawing_id, page=int(row.page)
            )
            if not page_bboxes:
                continue
            centroid = _bbox_centroid(cast(dict[str, float], row.label_bbox_json))
            if centroid is not None and _point_in_any_bbox(centroid, page_bboxes):
                kept.append(row)
            continue
        centroid = _bbox_centroid(cast(dict[str, float], row.label_bbox_json))
        if centroid is None:
            continue
        if _point_in_any_bbox(centroid, plan_bboxes):
            kept.append(row)
    return kept


def _digitized_station_centroids(
    session: Session,
    drawing_id: int,
    *,
    page: int = 1,
) -> dict[str, tuple[float, float]]:
    """Station → centroid from persisted SheetEntityGraph labels in plan viewports."""
    drawing = session.get(Drawing, int(drawing_id))
    if drawing is None:
        return {}
    stats = cast(dict[str, Any] | None, drawing.index_stats_json)
    if not isinstance(stats, dict):
        return {}
    graphs = stats.get("sheetEntityGraph")
    if not isinstance(graphs, dict):
        return {}
    page_graph = graphs.get(str(page))
    if not isinstance(page_graph, dict):
        return {}

    plan_ids = {
        str(vp.get("viewport_id"))
        for vp in (page_graph.get("viewports") or [])
        if isinstance(vp, dict) and vp.get("kind") == "plan"
    }
    plan_bboxes = _load_plan_viewport_bboxes(session, drawing_id, page=page)
    stations: dict[str, tuple[float, float]] = {}

    for label in page_graph.get("labels") or []:
        if not isinstance(label, dict):
            continue
        text = str(label.get("text") or "")
        found = extract_stations_from_text(text)
        if not found:
            continue
        bbox = label.get("bbox_fractional")
        if not (isinstance(bbox, (list, tuple)) and len(bbox) == 4):
            continue
        x0, y0, x1, y1 = (float(v) for v in bbox)
        centroid = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        viewport_id = label.get("viewport_id")
        if plan_ids and viewport_id not in plan_ids:
            continue
        if plan_bboxes and not _point_in_any_bbox(centroid, plan_bboxes):
            continue
        for station in found:
            key = _normalize_station(station)
            if key is not None and key not in stations:
                stations[key] = centroid

    # Symbol associations may carry station text via label_text.
    for assoc in page_graph.get("associations") or []:
        if not isinstance(assoc, dict):
            continue
        if plan_ids and assoc.get("viewport_id") not in plan_ids:
            continue
        for station in extract_stations_from_text(str(assoc.get("label_text") or "")):
            key = _normalize_station(station)
            if key is None or key in stations:
                continue
            # Prefer associated symbol bbox if present in symbols list.
            si = assoc.get("symbol_index")
            symbols = page_graph.get("symbols") or []
            if isinstance(si, int) and 0 <= si < len(symbols):
                symbol = symbols[si]
                bbox = symbol.get("bbox_fractional") if isinstance(symbol, dict) else None
                if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                    x0, y0, x1, y1 = (float(v) for v in bbox)
                    stations[key] = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
    return stations


def _match_digitized_station_controls(
    session: Session,
    *,
    aux_drawing_id: int,
    master_drawing_id: int,
) -> list[ControlPointPair]:
    """Prefer SheetEntityGraph station labels inside plan viewports when available."""
    aux_stations = _digitized_station_centroids(session, aux_drawing_id)
    master_stations = _digitized_station_centroids(session, master_drawing_id)
    pairs: list[ControlPointPair] = []
    for station, aux_xy in aux_stations.items():
        master_xy = master_stations.get(station)
        if master_xy is None:
            continue
        pairs.append(
            ControlPointPair(
                aux_xy=aux_xy,
                master_xy=master_xy,
                station=station,
                pairing_method="digitized_station",
            )
        )
    return pairs


def _bbox_centroid(bbox_json: dict[str, float]) -> tuple[float, float] | None:
    if not is_placed_survey_label_bbox(bbox_json):
        return None
    x0 = float(bbox_json["x0"])
    y0 = float(bbox_json["y0"])
    x1 = float(bbox_json["x1"])
    y1 = float(bbox_json["y1"])
    return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)


def _survey_coord_key(northing: float, easting: float) -> tuple[float, float]:
    return (round(northing, 2), round(easting, 2))


def _linear_fit(
    source_values: Sequence[float],
    target_values: Sequence[float],
) -> tuple[float, float]:
    """Fit ``target = scale * source + translate`` with least squares."""
    if len(source_values) != len(target_values) or not source_values:
        return 1.0, 0.0

    n = float(len(source_values))
    sum_source = sum(source_values)
    sum_target = sum(target_values)
    sum_source_source = sum(value * value for value in source_values)
    sum_source_target = sum(
        source * target for source, target in zip(source_values, target_values, strict=True)
    )
    denom = n * sum_source_source - sum_source * sum_source
    if abs(denom) < 1e-12:
        scale = 1.0
        translate = sum(
            target - source
            for source, target in zip(source_values, target_values, strict=True)
        ) / n
        return scale, translate

    scale = (n * sum_source_target - sum_source * sum_target) / denom
    translate = (sum_target - scale * sum_source) / n
    return scale, translate


def _has_real_survey_coordinates(row: DrawingSurveyPoint) -> bool:
    """True when a row carries OCR N/E suitable for coordinate matching."""
    if float(row.northing) == 0.0 and float(row.easting) == 0.0:
        return False
    meta = row.meta_json if isinstance(row.meta_json, dict) else {}
    if meta.get("plain_text_fallback"):
        return False
    return is_placed_survey_label_bbox(
        cast(dict[str, float], row.label_bbox_json),
        source=cast(str | None, row.source),
        meta_json=meta,
    )


def _master_has_real_survey_coordinates(master_rows: Sequence[DrawingSurveyPoint]) -> bool:
    return any(_has_real_survey_coordinates(row) for row in master_rows)


def _similarity_registration(
    pairs: Sequence[tuple[tuple[float, float], tuple[float, float]]],
) -> RegistrationTransform | None:
    """Uniform scale + rotation (+ translation) from paired fractional centroids."""
    if len(pairs) < 2:
        return None

    best_transform: RegistrationTransform | None = None
    best_error = float("inf")

    for rotation_deg in [step * 0.5 for step in range(-360, 361)]:
        aux0, master0 = pairs[0]
        rotated0 = rotate_point(aux0[0], aux0[1], rotation_deg)
        scales: list[float] = []
        for aux_xy, master_xy in pairs[1:]:
            rotated = rotate_point(aux_xy[0], aux_xy[1], rotation_deg)
            delta_rot = (rotated[0] - rotated0[0], rotated[1] - rotated0[1])
            delta_master = (master_xy[0] - master0[0], master_xy[1] - master0[1])
            rot_len = math.hypot(delta_rot[0], delta_rot[1])
            master_len = math.hypot(delta_master[0], delta_master[1])
            if rot_len > 1e-9:
                scales.append(master_len / rot_len)
        if not scales:
            continue

        scale = sum(scales) / len(scales)
        translate_x = master0[0] - scale * rotated0[0]
        translate_y = master0[1] - scale * rotated0[1]
        candidate = RegistrationTransform(
            scale_x=scale,
            scale_y=scale,
            translate_x=translate_x,
            translate_y=translate_y,
            rotation_degrees=rotation_deg,
        )
        error = 0.0
        for aux_xy, master_xy in pairs:
            projected = project_point_to_master(
                aux_xy[0],
                aux_xy[1],
                candidate,
            )
            error += math.hypot(
                projected[0] - master_xy[0],
                projected[1] - master_xy[1],
            )
        if error < best_error:
            best_error = error
            best_transform = candidate

    return best_transform


def compute_registration_from_control_points(
    pairs: Sequence[ControlPointPair | tuple[tuple[float, float], tuple[float, float]]],
) -> RegistrationTransform | None:
    """Build a registration transform from paired aux/master fractional centroids."""
    normalized: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for pair in pairs:
        if isinstance(pair, ControlPointPair):
            normalized.append((pair.aux_xy, pair.master_xy))
        else:
            normalized.append(pair)

    if len(normalized) == 1:
        aux_xy, master_xy = normalized[0]
        return RegistrationTransform(
            scale_x=1.0,
            scale_y=1.0,
            translate_x=master_xy[0] - aux_xy[0],
            translate_y=master_xy[1] - aux_xy[1],
            rotation_degrees=0.0,
        )

    if len(normalized) < 2:
        return None

    similarity = _similarity_registration(normalized)
    if similarity is not None:
        return similarity

    aux_x = [aux[0] for aux, _ in normalized]
    aux_y = [aux[1] for aux, _ in normalized]
    master_x = [master[0] for _, master in normalized]
    master_y = [master[1] for _, master in normalized]

    scale_x, translate_x = _linear_fit(aux_x, master_x)
    scale_y, translate_y = _linear_fit(aux_y, master_y)

    return RegistrationTransform(
        scale_x=scale_x,
        scale_y=scale_y,
        translate_x=translate_x,
        translate_y=translate_y,
        rotation_degrees=0.0,
    )


def _match_control_points_by_ne(
    aux_rows: Sequence[DrawingSurveyPoint],
    master_rows: Sequence[DrawingSurveyPoint],
) -> tuple[list[ControlPointPair], set[int]]:
    """Pair placed survey points that share the same N/E on aux and master sheets."""
    master_by_coord: dict[tuple[float, float], DrawingSurveyPoint] = {}
    for row in master_rows:
        key = _survey_coord_key(float(row.northing), float(row.easting))
        master_by_coord.setdefault(key, row)

    pairs: list[ControlPointPair] = []
    seen_keys: set[tuple[float, float]] = set()
    matched_aux_ids: set[int] = set()
    for aux_row in aux_rows:
        key = _survey_coord_key(float(aux_row.northing), float(aux_row.easting))
        if key in seen_keys:
            continue
        master_row = master_by_coord.get(key)
        if master_row is None:
            continue

        aux_centroid = _bbox_centroid(cast(dict[str, float], aux_row.label_bbox_json))
        master_centroid = _bbox_centroid(cast(dict[str, float], master_row.label_bbox_json))
        if aux_centroid is None or master_centroid is None:
            continue

        seen_keys.add(key)
        matched_aux_ids.add(cast(int, aux_row.id))
        pairs.append(
            ControlPointPair(
                aux_xy=aux_centroid,
                master_xy=master_centroid,
                northing=float(aux_row.northing),
                easting=float(aux_row.easting),
                station=cast(str | None, aux_row.station),
                pairing_method="ne",
            )
        )

    return pairs, matched_aux_ids


def _match_control_points_by_station(
    aux_rows: Sequence[DrawingSurveyPoint],
    master_rows: Sequence[DrawingSurveyPoint],
    *,
    exclude_aux_ids: set[int],
) -> list[ControlPointPair]:
    """Pair aux/master points by station when master sheets lack OCR'd N/E labels."""
    master_by_station: dict[str, DrawingSurveyPoint] = {}
    for row in master_rows:
        station = _normalize_station(cast(str | None, row.station))
        if station is None:
            continue
        master_by_station.setdefault(station, row)

    pairs: list[ControlPointPair] = []
    seen_stations: set[str] = set()
    for aux_row in aux_rows:
        aux_id = cast(int, aux_row.id)
        if aux_id in exclude_aux_ids:
            continue
        station = _normalize_station(cast(str | None, aux_row.station))
        if station is None or station in seen_stations:
            continue
        master_row = master_by_station.get(station)
        if master_row is None:
            continue

        aux_centroid = _bbox_centroid(cast(dict[str, float], aux_row.label_bbox_json))
        master_centroid = _bbox_centroid(cast(dict[str, float], master_row.label_bbox_json))
        if aux_centroid is None or master_centroid is None:
            continue

        seen_stations.add(station)
        pairs.append(
            ControlPointPair(
                aux_xy=aux_centroid,
                master_xy=master_centroid,
                northing=float(aux_row.northing),
                easting=float(aux_row.easting),
                station=cast(str | None, aux_row.station),
                pairing_method="station",
            )
        )

    return pairs


def match_control_points(
    session: Session,
    *,
    aux_drawing_id: int,
    master_drawing_id: int,
) -> list[ControlPointPair]:
    """Pair aux/master control points by shared N/E, then by shared station labels.

    Prefers digitized SheetEntityGraph stations inside ``kind=plan`` viewports.
    Falls back to ``DrawingSurveyPoint`` rows, filtered to plan viewports when
    seeded (section/profile geometry is ignored for registration).
    """
    digitized = _match_digitized_station_controls(
        session,
        aux_drawing_id=int(aux_drawing_id),
        master_drawing_id=int(master_drawing_id),
    )
    if len(digitized) >= 2:
        return digitized

    aux_rows: list[DrawingSurveyPoint] = (
        session.query(DrawingSurveyPoint)
        .filter(DrawingSurveyPoint.drawing_id == aux_drawing_id)
        .order_by(DrawingSurveyPoint.id.asc())
        .all()
    )
    master_rows: list[DrawingSurveyPoint] = (
        session.query(DrawingSurveyPoint)
        .filter(DrawingSurveyPoint.drawing_id == master_drawing_id)
        .order_by(DrawingSurveyPoint.id.asc())
        .all()
    )
    aux_rows = _filter_survey_rows_to_plan_viewports(
        session, aux_rows, drawing_id=int(aux_drawing_id)
    )
    master_rows = _filter_survey_rows_to_plan_viewports(
        session, master_rows, drawing_id=int(master_drawing_id)
    )

    pairs_by_ne, matched_aux_ids = _match_control_points_by_ne(aux_rows, master_rows)
    if not _master_has_real_survey_coordinates(master_rows):
        pairs_by_ne = []
        matched_aux_ids = set()
    pairs_by_station = _match_control_points_by_station(
        aux_rows,
        master_rows,
        exclude_aux_ids=matched_aux_ids,
    )
    survey_pairs = [*pairs_by_ne, *pairs_by_station]
    if digitized and not survey_pairs:
        return digitized
    if digitized:
        # Merge: digitized stations first, then survey pairs for unmatched stations.
        seen = {_normalize_station(p.station) for p in digitized}
        for pair in survey_pairs:
            key = _normalize_station(pair.station)
            if key is None or key not in seen:
                digitized.append(pair)
                if key is not None:
                    seen.add(key)
        return digitized
    return survey_pairs


def compute_registration_for_linked_drawings(
    session: Session,
    *,
    linked_drawing_ids: Sequence[int],
    master_drawing_id: int,
) -> tuple[RegistrationTransform | None, int, int | None]:
    """Return the best registration transform across linked aux drawings."""
    best_pairs: list[ControlPointPair] = []
    best_aux_id: int | None = None

    for aux_drawing_id in linked_drawing_ids:
        if int(aux_drawing_id) == int(master_drawing_id):
            continue
        pairs = match_control_points(
            session,
            aux_drawing_id=int(aux_drawing_id),
            master_drawing_id=int(master_drawing_id),
        )
        if len(pairs) > len(best_pairs):
            best_pairs = pairs
            best_aux_id = int(aux_drawing_id)

    transform = compute_registration_from_control_points(best_pairs)
    return transform, len(best_pairs), best_aux_id


def registration_transform_to_meta(
    transform: RegistrationTransform,
    *,
    control_point_count: int,
    aux_drawing_id: int | None = None,
) -> dict[str, float | int]:
    meta: dict[str, float | int] = {
        "scale_x": transform.scale_x,
        "scale_y": transform.scale_y,
        "translate_x": transform.translate_x,
        "translate_y": transform.translate_y,
        "rotation_degrees": transform.rotation_degrees,
        "registration_control_point_count": control_point_count,
    }
    if aux_drawing_id is not None:
        meta["registration_aux_drawing_id"] = aux_drawing_id
    return meta


def project_point_to_master(
    x: float,
    y: float,
    registration_transform: RegistrationTransform,
) -> tuple[float, float]:
    rx, ry = rotate_point(
        x,
        y,
        registration_transform.rotation_degrees,
    )
    return clamp_point_to_page(
        (
            rx * registration_transform.scale_x + registration_transform.translate_x,
            ry * registration_transform.scale_y + registration_transform.translate_y,
        )
    )


def project_polyline_to_master(
    points: Sequence[tuple[float, float]],
    registration_transform: RegistrationTransform,
) -> tuple[tuple[float, float], ...]:
    return tuple(
        project_point_to_master(x, y, registration_transform) for x, y in points
    )


def project_bbox_to_master(
    bbox: tuple[float, float, float, float],
    registration_transform: RegistrationTransform,
) -> tuple[float, float, float, float]:
    return registration_transform.apply(*bbox)
