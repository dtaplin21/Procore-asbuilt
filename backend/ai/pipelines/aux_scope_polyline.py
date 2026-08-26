"""Build ordered polylines from auxiliary drawing scoped survey points."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ai.pipelines.station_range_extractor import station_chainage
from ai.pipelines.survey_point_extractor import SurveyPointRecord, is_placed_survey_label_bbox


@dataclass(frozen=True)
class AuxSurveyPolylineResult:
    points: tuple[tuple[float, float], ...]
    source_drawing_id: int
    stations: tuple[str, ...]


def _drawing_id(point: SurveyPointRecord) -> int | None:
    meta = point.meta_json or {}
    raw = meta.get("drawing_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _bbox_centroid(label_bbox: dict[str, float]) -> tuple[float, float] | None:
    if is_placed_survey_label_bbox(label_bbox):
        x0 = float(label_bbox["x0"])
        y0 = float(label_bbox["y0"])
        x1 = float(label_bbox["x1"])
        y1 = float(label_bbox["y1"])
        return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)

    if "x" in label_bbox and "y" in label_bbox:
        try:
            x = float(label_bbox["x"])
            y = float(label_bbox["y"])
            width = float(label_bbox.get("width", 0.0))
            height = float(label_bbox.get("height", 0.0))
        except (KeyError, TypeError, ValueError):
            return None
        if width <= 0 or height <= 0 or width * height < 0.00005:
            return None
        return (x + width / 2.0, y + height / 2.0)

    return None


def _normalize_station(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().upper()
    return cleaned or None


def _station_in_range(
    station: str,
    *,
    station_from: str | None,
    station_to: str | None,
) -> bool:
    if station_from is None or station_to is None:
        return True
    chainage = station_chainage(station)
    return station_chainage(station_from) <= chainage <= station_chainage(station_to)


def build_aux_survey_polyline(
    scoped_points: Sequence[SurveyPointRecord],
    *,
    station_from: str | None = None,
    station_to: str | None = None,
    min_points: int = 3,
) -> AuxSurveyPolylineResult | None:
    """Chain scoped aux survey points into an ordered polyline by station chainage."""
    if not scoped_points:
        return None

    grouped: dict[int, list[tuple[float, str, tuple[float, float]]]] = {}
    for point in scoped_points:
        drawing_id = _drawing_id(point)
        station = _normalize_station(point.station)
        if drawing_id is None or station is None:
            continue
        if not _station_in_range(
            station,
            station_from=station_from,
            station_to=station_to,
        ):
            continue
        centroid = _bbox_centroid(point.label_bbox_json)
        if centroid is None:
            continue
        grouped.setdefault(drawing_id, []).append(
            (station_chainage(station), station, centroid)
        )

    best_drawing_id: int | None = None
    best_hits: list[tuple[float, str, tuple[float, float]]] = []
    for drawing_id, hits in grouped.items():
        if len(hits) > len(best_hits):
            best_drawing_id = drawing_id
            best_hits = hits

    if best_drawing_id is None or len(best_hits) < min_points:
        return None

    best_hits.sort(key=lambda item: item[0])
    deduped: list[tuple[float, str, tuple[float, float]]] = []
    seen_chainages: set[float] = set()
    for chainage, station, centroid in best_hits:
        if chainage in seen_chainages:
            continue
        seen_chainages.add(chainage)
        deduped.append((chainage, station, centroid))

    if len(deduped) < min_points:
        return None

    return AuxSurveyPolylineResult(
        points=tuple(centroid for _, _, centroid in deduped),
        source_drawing_id=best_drawing_id,
        stations=tuple(station for _, station, _ in deduped),
    )
