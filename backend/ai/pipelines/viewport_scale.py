"""Per-viewport scale resolution and fractional→feet conversion.

Feet conversion MUST use the containing viewport's scale only.
Never fall back to sheet-global ``drawings.scale_json``.
"""

from __future__ import annotations

from typing import Any, Literal, Sequence, cast

from sqlalchemy.orm import Session

from ai.pipelines.drawing_scale_parser import (
    real_extent_feet,
    real_feet_per_paper_inch_from_scale,
)
from ai.pipelines.sheet_entity_graph import (
    DrawingViewport,
    ViewportKind,
    ViewportScale,
    assign_viewport_id,
)
from models.drawing_viewport import DrawingViewport as DrawingViewportRow


def viewport_scale_from_json(scale_json: dict[str, Any] | None) -> ViewportScale | None:
    """Build a ViewportScale from DB / parser ``scale_json`` shape."""
    if not scale_json:
        return None
    try:
        rfppi = float(scale_json.get("real_feet_per_paper_inch", 0.0))
    except (TypeError, ValueError):
        return None
    if rfppi <= 0:
        return None
    raw = scale_json.get("raw_text")
    try:
        confidence = float(scale_json.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    horizontal = scale_json.get("horizontal")
    vertical = scale_json.get("vertical")
    return ViewportScale(
        raw_text=str(raw) if raw is not None else "",
        real_feet_per_paper_inch=rfppi,
        confidence=confidence,
        horizontal=cast(dict[str, Any] | None, horizontal if isinstance(horizontal, dict) else None),
        vertical=cast(dict[str, Any] | None, vertical if isinstance(vertical, dict) else None),
    )


def _bbox_fractional_from_json(bbox_json: dict[str, Any]) -> tuple[float, float, float, float]:
    return (
        float(bbox_json["x0"]),
        float(bbox_json["y0"]),
        float(bbox_json["x1"]),
        float(bbox_json["y1"]),
    )


def drawing_viewport_from_row(row: DrawingViewportRow) -> DrawingViewport:
    """Map an ORM DrawingViewport row to the sheet-entity dataclass."""
    return DrawingViewport(
        viewport_id=cast(str, row.viewport_id),
        kind=cast(ViewportKind, row.kind),
        page=cast(int, row.page),
        bbox_fractional=_bbox_fractional_from_json(cast(dict[str, Any], row.bbox_json)),
        scale=viewport_scale_from_json(cast(dict[str, Any] | None, row.scale_json)),
        source=cast(str, row.source),
        notes=cast(str, row.notes or ""),
    )


def load_viewports(
    session: Session,
    drawing_id: int,
    page: int = 1,
) -> list[DrawingViewport]:
    """Load calibrated viewports for one drawing page (dataclass form)."""
    rows = (
        session.query(DrawingViewportRow)
        .filter_by(drawing_id=drawing_id, page=page)
        .order_by(DrawingViewportRow.viewport_id.asc())
        .all()
    )
    return [drawing_viewport_from_row(row) for row in rows]


def _scale_json_from_viewport_scale(scale: ViewportScale) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "raw_text": scale.raw_text,
        "real_feet_per_paper_inch": scale.real_feet_per_paper_inch,
        "confidence": scale.confidence,
    }
    if scale.horizontal is not None:
        payload["horizontal"] = scale.horizontal
    if scale.vertical is not None:
        payload["vertical"] = scale.vertical
    return payload


def scale_for_geometry(
    viewports: Sequence[DrawingViewport],
    *,
    point: tuple[float, float] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> ViewportScale | None:
    """Pick viewport containing geometry; return its scale. None if unresolved.

    MUST NOT return sheet-global drawings.scale_json as a silent fallback.
    """
    if point is None and bbox is None:
        return None
    if point is not None and bbox is not None:
        raise ValueError("Pass only one of point or bbox")

    geometry: tuple[float, ...] = point if point is not None else cast(
        tuple[float, float, float, float],
        bbox,
    )
    viewport_id = assign_viewport_id(geometry, tuple(viewports))
    if viewport_id is None:
        return None

    for viewport in viewports:
        if viewport.viewport_id == viewport_id:
            return viewport.scale
    return None


def fractional_delta_to_feet(
    delta_frac: float,
    *,
    axis: Literal["x", "y"],
    scale: ViewportScale,
    page_width_in: float,
    page_height_in: float,
) -> float:
    """Convert a fractional page delta to feet using THAT viewport's scale only."""
    scale_axis = "horizontal" if axis == "x" else "vertical"
    page_axis_in = page_width_in if axis == "x" else page_height_in
    rfppi = real_feet_per_paper_inch_from_scale(
        _scale_json_from_viewport_scale(scale),
        axis=scale_axis,
    )
    if rfppi is None:
        raise ValueError(f"Viewport scale missing usable {scale_axis} feet/inch")
    return real_extent_feet(float(delta_frac), float(page_axis_in), float(rfppi))
