"""Compute master ↔ auxiliary registration from shared survey control points."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence, cast

from sqlalchemy.orm import Session

from ai.pipelines.coordinate_frame import rotate_point
from ai.pipelines.drawing_location_resolver import RegistrationTransform
from ai.pipelines.scope_geometry import clamp_point_to_page
from ai.pipelines.survey_point_extractor import is_placed_survey_label_bbox
from models.drawing_survey_point import DrawingSurveyPoint


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
    """Pair aux/master control points by shared N/E, then by shared station labels."""
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

    pairs_by_ne, matched_aux_ids = _match_control_points_by_ne(aux_rows, master_rows)
    pairs_by_station = _match_control_points_by_station(
        aux_rows,
        master_rows,
        exclude_aux_ids=matched_aux_ids,
    )
    return [*pairs_by_ne, *pairs_by_station]


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
