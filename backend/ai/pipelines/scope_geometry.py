"""Normalized 0-1 scope geometry for inspection overlays."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence, cast

LineSegment = tuple[tuple[float, float], tuple[float, float]]

from ai.agents.evidence_dossier import EvidenceDossier
from ai.pipelines.fractional_coords import (
    bbox_intersects_page,
    clamp_fractional,
    clamp_fractional_bbox,
    clamp_point_to_page,
)
from services.region_storage import _check_normalized

_LINEAR_UTILITY_RE = re.compile(
    r"\b(?:lateral|main(?:line)?|run|pipe|piping|duct|sewer|sanitary|water|conduit|"
    r"force\s+main|drain(?:age)?|utility\s+line|trunk)\b",
    re.IGNORECASE,
)
_CORRIDOR_RE = re.compile(
    r"\b(?:corridor|hallway|passage|parking\s+lot|parking)\b",
    re.IGNORECASE,
)
_AREA_RE = re.compile(
    r"\b(?:room|area|zone|wing|space|lot)\b",
    re.IGNORECASE,
)


class ScopeKind(str, Enum):
    UTILITY_LINE = "utility_line"
    STATION_RANGE = "station_range"
    POINT = "point"
    AREA = "area"
    CORRIDOR = "corridor"


@dataclass(frozen=True)
class ScopeGeometry:
    page: int
    type: str  # rect | polygon | polyline | line_segments
    points: tuple[tuple[float, float], ...] | None = None
    segments: tuple[LineSegment, ...] | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    scope_kind: ScopeKind = ScopeKind.AREA
    meta: dict[str, Any] | None = None

    def to_geometry_json(self) -> dict[str, Any]:
        """Serialize for DrawingOverlay.geometry column."""
        payload: dict[str, Any] = {
            "page": self.page,
            "type": self.type,
        }

        if self.type == "rect":
            if self.x is None or self.y is None or self.width is None or self.height is None:
                raise ValueError("rect scope requires x, y, width, and height")
            x = clamp_fractional(float(self.x))
            y = clamp_fractional(float(self.y))
            width = max(float(self.width), 0.0)
            height = max(float(self.height), 0.0)
            if x + width > 1.0:
                width = max(1.0 - x, 0.001)
            if y + height > 1.0:
                height = max(1.0 - y, 0.001)
            payload.update(
                {
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                }
            )
        elif self.type in {"polygon", "polyline"}:
            if not self.points:
                raise ValueError(f"{self.type} scope requires points")
            payload["points"] = [
                list(clamp_point_to_page((float(x), float(y))))
                for x, y in self.points
            ]
        elif self.type == "line_segments":
            if not self.segments:
                raise ValueError("line_segments scope requires segments")
            payload["segments"] = [
                [
                    list(clamp_point_to_page((float(a[0]), float(a[1])))),
                    list(clamp_point_to_page((float(b[0]), float(b[1])))),
                ]
                for a, b in self.segments
            ]
        else:
            raise ValueError(
                "scope type must be 'rect', 'polygon', 'polyline', or 'line_segments'"
            )

        if self.scope_kind != ScopeKind.AREA:
            payload["scope_kind"] = self.scope_kind.value
        if self.meta:
            payload["meta"] = dict(self.meta)

        validate_scope_geometry(payload)
        return payload


def validate_scope_geometry(geometry: dict[str, Any]) -> None:
    """Validate normalized scope geometry. Raises ValueError on invalid input."""
    if not isinstance(geometry, dict):
        raise ValueError("geometry must be an object")

    gtype = geometry.get("type")
    if gtype == "rect":
        for key in ("x", "y", "width", "height"):
            if key not in geometry:
                raise ValueError(f"rect geometry requires {key}")
            val = geometry[key]
            if not isinstance(val, (int, float)):
                raise ValueError(f"{key} must be a number")
            _check_normalized(float(val), key)
        width = float(geometry["width"])
        height = float(geometry["height"])
        if width <= 0 or height <= 0:
            raise ValueError("Scope bounding box must have positive width and height.")
    elif gtype == "polygon":
        _validate_point_list(geometry.get("points"), min_points=3, label="polygon")
    elif gtype == "polyline":
        _validate_point_list(geometry.get("points"), min_points=2, label="polyline")
    elif gtype == "line_segments":
        _validate_segment_list(geometry.get("segments"))
    else:
        raise ValueError(
            "geometry.type must be 'rect', 'polygon', 'polyline', or 'line_segments'"
        )


def line_segments_from_points(
    points: Sequence[tuple[float, float]],
) -> tuple[LineSegment, ...]:
    """Turn consecutive vertices into independent segment pairs (not a connected polyline stroke)."""
    if len(points) < 2:
        return ()
    return tuple((points[index], points[index + 1]) for index in range(len(points) - 1))


def scope_line_segments(
    *,
    page: int,
    points: Sequence[tuple[float, float]],
    scope_kind: ScopeKind,
    meta: dict[str, Any] | None = None,
) -> ScopeGeometry:
    segments = line_segments_from_points(points)
    if not segments:
        raise ValueError("line segment scope requires at least two points")
    return ScopeGeometry(
        page=page,
        type="line_segments",
        segments=segments,
        scope_kind=scope_kind,
        meta=meta,
    )


def scope_path_points(scope: ScopeGeometry) -> tuple[tuple[float, float], ...] | None:
    """Flatten scope geometry into a vertex path for bbox envelopes and eval metrics."""
    if scope.type == "polyline" and scope.points:
        return scope.points
    if scope.type == "line_segments" and scope.segments:
        path: list[tuple[float, float]] = []
        for index, (start, end) in enumerate(scope.segments):
            if index == 0:
                path.append(start)
            path.append(end)
        return tuple(path)
    return None


def _validate_segment_list(segments: Any) -> None:
    if not isinstance(segments, list):
        raise ValueError("line_segments must have segments array")
    if len(segments) < 1:
        raise ValueError("line_segments needs at least 1 segment.")
    for index, segment in enumerate(segments):
        if not isinstance(segment, (list, tuple)) or len(segment) != 2:
            raise ValueError(f"segment {index} must be [[x0, y0], [x1, y1]]")
        for point_index, point in enumerate(segment):
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                raise ValueError(f"segment {index} point {point_index} must be [x, y]")
            _check_normalized(float(point[0]), f"segments[{index}][{point_index}][0]")
            _check_normalized(float(point[1]), f"segments[{index}][{point_index}][1]")


def _validate_point_list(
    points: Any,
    *,
    min_points: int,
    label: str,
) -> None:
    if not isinstance(points, list):
        raise ValueError(f"{label} must have points array")
    if len(points) < min_points:
        raise ValueError(f"A {label} needs at least {min_points} points.")
    for index, point in enumerate(points):
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            raise ValueError(f"point {index} must be [x, y]")
        _check_normalized(float(point[0]), f"points[{index}][0]")
        _check_normalized(float(point[1]), f"points[{index}][1]")


def bbox_to_scope_rect(
    bbox: tuple[float, float, float, float],
    *,
    page: int,
    scope_kind: ScopeKind,
) -> ScopeGeometry:
    x0, y0, x1, y1 = clamp_fractional_bbox(bbox)
    return ScopeGeometry(
        page=page,
        type="rect",
        x=x0,
        y=y0,
        width=max(x1 - x0, 0.001),
        height=max(y1 - y0, 0.001),
        scope_kind=scope_kind,
    )


def infer_scope_kind(dossier: EvidenceDossier) -> ScopeKind:
    """Infer overlay scope type from dossier clues and survey context."""
    text = _dossier_text_blob(dossier)
    station_from, station_to = _station_range(dossier)
    survey_points = _evidence_survey_points(dossier)

    if station_from and station_to:
        if _has_linear_utility_language(text):
            return ScopeKind.UTILITY_LINE
        return ScopeKind.STATION_RANGE

    if len(survey_points) >= 2:
        return ScopeKind.UTILITY_LINE

    if _has_linear_utility_language(text):
        return ScopeKind.UTILITY_LINE

    if not _has_linear_utility_language(text):
        if _CORRIDOR_RE.search(text):
            return ScopeKind.CORRIDOR
        if _AREA_RE.search(text):
            return ScopeKind.AREA

    if len(survey_points) == 1:
        return ScopeKind.POINT

    return ScopeKind.AREA


def _dossier_text_blob(dossier: EvidenceDossier) -> str:
    parts = [dossier.evidence_text, dossier.base_text]
    for clue in dossier.expanded_clues:
        parts.extend(clue.expanded_values)
    for attachment in dossier.linked_attachments:
        parts.append(attachment.text_preview)
    return " ".join(part.strip() for part in parts if part and part.strip())


def _has_linear_utility_language(text: str) -> bool:
    return bool(_LINEAR_UTILITY_RE.search(text))


def _station_range(dossier: EvidenceDossier) -> tuple[str | None, str | None]:
    station_from: str | None = None
    station_to: str | None = None

    meta = cast(dict[str, Any] | None, getattr(dossier.evidence, "meta", None))
    if isinstance(meta, dict):
        station_from = _clean_station(meta.get("station_from"))
        station_to = _clean_station(meta.get("station_to"))

    for clue in dossier.clues:
        clue_type = str(getattr(clue, "clue_type", "") or "")
        value = _clean_station(getattr(clue, "clue_value", None))
        if not value:
            continue
        if clue_type == "station_from":
            station_from = station_from or value
        elif clue_type == "station_to":
            station_to = station_to or value

    for clue in dossier.expanded_clues:
        value = _clean_station(clue.original_value)
        if not value:
            continue
        if clue.clue_type == "station_from":
            station_from = station_from or value
        elif clue.clue_type == "station_to":
            station_to = station_to or value

    return station_from, station_to


def _clean_station(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _evidence_survey_points(dossier: EvidenceDossier) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for item in dossier.survey_points_meta:
        if not isinstance(item, dict):
            continue
        try:
            float(item["northing"])
            float(item["easting"])
        except (KeyError, TypeError, ValueError):
            continue
        points.append(item)
    return points
