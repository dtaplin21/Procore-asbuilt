"""Normalized 0-1 scope geometry for inspection overlays."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

from ai.agents.evidence_dossier import EvidenceDossier
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
    type: str  # rect | polygon | polyline
    points: tuple[tuple[float, float], ...] | None = None
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
            payload.update(
                {
                    "x": self.x,
                    "y": self.y,
                    "width": self.width,
                    "height": self.height,
                }
            )
        elif self.type in {"polygon", "polyline"}:
            if not self.points:
                raise ValueError(f"{self.type} scope requires points")
            payload["points"] = [[float(x), float(y)] for x, y in self.points]
        else:
            raise ValueError("scope type must be 'rect', 'polygon', or 'polyline'")

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
    else:
        raise ValueError("geometry.type must be 'rect', 'polygon', or 'polyline'")


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
    x0, y0, x1, y1 = bbox
    return ScopeGeometry(
        page=page,
        type="rect",
        x=x0,
        y=y0,
        width=max(x1 - x0, 0.0),
        height=max(y1 - y0, 0.0),
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
