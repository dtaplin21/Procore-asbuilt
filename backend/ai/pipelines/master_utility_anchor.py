"""Fallback search windows on master drawings when coordinate pins are aux-only."""

from __future__ import annotations

from typing import Any, Sequence

from ai.pipelines.scope_geometry import clamp_fractional_bbox

# Plan-view band (exclude title block / profile strip).
_PLAN_Y_MIN = 0.18
_PLAN_Y_MAX = 0.88
_CORRIDOR_PAD_X = 0.22
_CORRIDOR_PAD_Y = 0.18

_UTILITY_ANCHOR_TERMS = (
    "HIGHWAY",
    "SANITARY",
    "SEWER",
    "SSMH",
    "STORM",
    "WATER",
    "UTIL",
)


def _centroid_y(bbox: dict[str, float]) -> float:
    return (float(bbox["y0"]) + float(bbox["y1"])) / 2.0


def _valid_bbox(raw: Any) -> dict[str, float] | None:
    if not isinstance(raw, dict):
        return None
    try:
        return {
            "x0": float(raw["x0"]),
            "y0": float(raw["y0"]),
            "x1": float(raw["x1"]),
            "y1": float(raw["y1"]),
        }
    except (KeyError, TypeError, ValueError):
        return None


def _bbox_from_element(element: Any) -> dict[str, float] | None:
    return _valid_bbox(getattr(element, "bbox_json", None))


def _matches_utility_anchor(text: str) -> bool:
    upper = text.strip().upper()
    if not upper:
        return False
    if upper in {"SS", "SD", "WTR"}:
        return True
    return any(term in upper for term in _UTILITY_ANCHOR_TERMS)


def utility_corridor_anchor_from_text_elements(
    elements: Sequence[Any],
    *,
    page: int = 1,
) -> tuple[float, float, float, float] | None:
    """Build a master-space search bbox around utility / corridor OCR on the plan."""
    hits: list[dict[str, float]] = []
    for element in elements:
        if int(getattr(element, "page", 1)) != page:
            continue
        bbox = _bbox_from_element(element)
        if bbox is None:
            continue
        cy = _centroid_y(bbox)
        if cy < _PLAN_Y_MIN or cy > _PLAN_Y_MAX:
            continue
        text = str(getattr(element, "text", "") or "")
        if not _matches_utility_anchor(text):
            continue
        hits.append(bbox)

    if not hits:
        return None

    x0 = min(b["x0"] for b in hits)
    y0 = min(b["y0"] for b in hits)
    x1 = max(b["x1"] for b in hits)
    y1 = max(b["y1"] for b in hits)
    return clamp_fractional_bbox(
        (
            max(0.0, x0 - _CORRIDOR_PAD_X),
            max(0.0, y0 - _CORRIDOR_PAD_Y),
            min(1.0, x1 + _CORRIDOR_PAD_X),
            min(1.0, y1 + _CORRIDOR_PAD_Y),
        )
    )


def utility_corridor_anchor_for_drawing(
    session: Any,
    master_drawing_id: int,
    *,
    page: int = 1,
) -> tuple[float, float, float, float] | None:
    """Load indexed tokens for a drawing and derive a utility trace anchor."""
    from models.drawing_text_element import DrawingTextElement

    rows = (
        session.query(DrawingTextElement)
        .filter(DrawingTextElement.master_drawing_id == int(master_drawing_id))
        .filter(DrawingTextElement.page == int(page))
        .order_by(DrawingTextElement.id.asc())
        .all()
    )
    if not rows:
        return None
    return utility_corridor_anchor_from_text_elements(rows, page=page)
