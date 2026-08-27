"""Extract plan-view station ranges from indexed auxiliary drawing OCR tokens."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, cast

from sqlalchemy.orm import Session

from ai.pipelines.survey_point_extractor import extract_stations_from_text
from models.drawing_text_element import DrawingTextElement


class _TextTokenLike(Protocol):
    @property
    def text(self) -> str: ...

    @property
    def bbox_json(self) -> dict[str, float]: ...


@dataclass(frozen=True)
class _DrawingTextToken:
    text: str
    bbox_json: dict[str, float]

    @classmethod
    def from_row(cls, row: DrawingTextElement) -> _DrawingTextToken:
        return cls(
            text=str(row.text),
            bbox_json=cast(dict[str, float], row.bbox_json),
        )


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


def _station_major(station: str) -> int:
    return int(station.strip().upper().split("+", 1)[0])


def extract_station_range_from_tokens(
    tokens: Sequence[_TextTokenLike],
    *,
    max_profile_y: float = 0.85,
) -> StationRangeResult:
    """Return min/max station span from OCR tokens (plan view preferred).

    When only one plan-view station exists (common on C4.20), pair it with the
    minimum matching profile-grid station (e.g. ``10+00`` at y>0.85 + ``10+90.95``
    on plan) so trench runs span the full plan chainage.
    """
    plan_hits: list[tuple[float, str, dict[str, float]]] = []
    profile_hits: list[tuple[float, str, dict[str, float]]] = []
    seen_plan: set[float] = set()
    seen_profile: set[float] = set()

    for token in tokens:
        bbox = token.bbox_json
        centroid_y = _centroid_y(bbox)
        bucket = plan_hits if centroid_y <= max_profile_y else profile_hits
        seen = seen_plan if centroid_y <= max_profile_y else seen_profile
        for station in extract_stations_from_text(token.text):
            chainage = station_chainage(station)
            if chainage in seen:
                continue
            seen.add(chainage)
            bucket.append((chainage, station, bbox))

    if not plan_hits:
        return StationRangeResult(station_from=None, station_to=None)

    majors = {_station_major(station) for _, station, _ in plan_hits}
    best: StationRangeResult | None = None
    best_span = -1.0

    for major in majors:
        major_plan = sorted(
            (hit for hit in plan_hits if _station_major(hit[1]) == major),
            key=lambda item: item[0],
        )
        major_profile = sorted(
            (hit for hit in profile_hits if _station_major(hit[1]) == major),
            key=lambda item: item[0],
        )
        if not major_plan:
            continue

        _, station_to, to_bbox = major_plan[-1]
        to_chainage = station_chainage(station_to)

        station_from: str | None = None
        from_bbox: dict[str, float] | None = None
        if major_profile:
            profile_candidates = [
                hit for hit in major_profile if hit[0] <= to_chainage
            ]
            if profile_candidates:
                _, station_from, from_bbox = profile_candidates[0]
        if station_from is None and len(major_plan) >= 2:
            _, station_from, from_bbox = major_plan[0]
        if station_from is None:
            continue

        span = station_chainage(station_to) - station_chainage(station_from)
        if span <= 0 or span <= best_span:
            continue
        best_span = span
        best = StationRangeResult(
            station_from=station_from,
            station_to=station_to,
            station_from_bbox_json=from_bbox,
            station_to_bbox_json=to_bbox,
        )

    return best or StationRangeResult(station_from=None, station_to=None)


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

        tokens = [_DrawingTextToken.from_row(row) for row in rows]
        plan_station_count = sum(
            1
            for token in tokens
            if _centroid_y(token.bbox_json) <= max_profile_y
            and extract_stations_from_text(token.text)
        )
        result = extract_station_range_from_tokens(tokens, max_profile_y=max_profile_y)
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
