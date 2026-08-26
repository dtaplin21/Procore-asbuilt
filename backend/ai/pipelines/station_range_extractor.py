"""Extract plan-view station ranges from indexed auxiliary drawing OCR tokens."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from sqlalchemy.orm import Session

from ai.pipelines.survey_point_extractor import extract_stations_from_text
from models.drawing_text_element import DrawingTextElement


class _TextTokenLike(Protocol):
    text: str
    bbox_json: dict[str, float]


@dataclass(frozen=True)
class StationRangeResult:
    station_from: str | None
    station_to: str | None
    station_from_bbox_json: dict[str, float] | None = None
    station_to_bbox_json: dict[str, float] | None = None
    source_drawing_id: int | None = None


def station_chainage(value: str) -> float:
    """Convert ``10+90.95``-style labels to numeric chainage for ordering."""
    cleaned = value.strip().upper()
    major, minor = cleaned.split("+", 1)
    return int(major) * 100 + float(minor)


def _centroid_y(bbox: dict[str, float]) -> float:
    if "y" in bbox:
        return float(bbox["y"]) + float(bbox.get("height", 0.0)) / 2.0
    return (float(bbox.get("y0", 0.0)) + float(bbox.get("y1", 0.0))) / 2.0


def extract_station_range_from_tokens(
    tokens: Sequence[_TextTokenLike],
    *,
    max_profile_y: float = 0.85,
) -> StationRangeResult:
    """Return min/max plan-view stations from OCR tokens (filters profile strip)."""
    hits: list[tuple[float, str, dict[str, float]]] = []
    seen_chainages: set[float] = set()

    for token in tokens:
        bbox = token.bbox_json
        if _centroid_y(bbox) > max_profile_y:
            continue
        for station in extract_stations_from_text(token.text):
            chainage = station_chainage(station)
            if chainage in seen_chainages:
                continue
            seen_chainages.add(chainage)
            hits.append((chainage, station, bbox))

    if len(hits) < 2:
        return StationRangeResult(station_from=None, station_to=None)

    hits.sort(key=lambda item: item[0])
    _, station_from, from_bbox = hits[0]
    _, station_to, to_bbox = hits[-1]
    return StationRangeResult(
        station_from=station_from,
        station_to=station_to,
        station_from_bbox_json=from_bbox,
        station_to_bbox_json=to_bbox,
    )


def extract_station_range_for_drawings(
    session: Session,
    drawing_ids: Sequence[int],
    *,
    page: int = 1,
    max_profile_y: float = 0.85,
) -> StationRangeResult:
    """Pick the linked drawing with the richest plan-view station span."""
    best: StationRangeResult | None = None
    best_hit_count = 0

    for drawing_id in drawing_ids:
        rows: list[DrawingTextElement] = (
            session.query(DrawingTextElement)
            .filter(DrawingTextElement.master_drawing_id == int(drawing_id))
            .filter(DrawingTextElement.page == page)
            .order_by(DrawingTextElement.id.asc())
            .all()
        )
        if not rows:
            continue

        plan_station_count = sum(
            1
            for row in rows
            if _centroid_y(row.bbox_json) <= max_profile_y
            and extract_stations_from_text(row.text)
        )
        result = extract_station_range_from_tokens(rows, max_profile_y=max_profile_y)
        if result.station_from is None or result.station_to is None:
            continue
        if plan_station_count > best_hit_count:
            best_hit_count = plan_station_count
            best = StationRangeResult(
                station_from=result.station_from,
                station_to=result.station_to,
                station_from_bbox_json=result.station_from_bbox_json,
                station_to_bbox_json=result.station_to_bbox_json,
                source_drawing_id=int(drawing_id),
            )

    return best or StationRangeResult(station_from=None, station_to=None)
