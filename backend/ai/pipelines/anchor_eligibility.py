"""Drop placement anchors that cannot be a plan location, before ranking.

A legend or title-block box is not a utility location. A coordinate pin is not
a location when this sheet has no registered northing/easting. Those anchors
are removed first. Ranking only sees what remains, so a higher score on a
rejected anchor cannot beat a lower score on a valid one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from sqlalchemy.orm import Session

from ai.pipelines.drawing_location_resolver import ResolutionMethod
from ai.pipelines.drawing_scale_parser import TITLE_BLOCK_X_MIN, TITLE_BLOCK_Y_MIN
from ai.pipelines.location_match_orchestrator import LocationMatchCandidate
from ai.pipelines.registration_from_survey import _master_has_real_survey_coordinates
from models.drawing_region import DrawingRegion
from models.drawing_survey_point import DrawingSurveyPoint
from models.models import Drawing
from services.legend_index_helpers import resolved_legend_rect

# Far-right title-block column. Legend labels on these sheets stop near x=0.88.
TITLE_BLOCK_COLUMN_X_MIN = 0.88

REASON_LEGEND = "Anchor box is in the legend area."
REASON_TITLE_BLOCK = "Anchor box is in the title-block area."
REASON_COORDINATE_WITHOUT_NE = (
    "Coordinate anchor rejected because the sheet has no registered N/E."
)

BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class AnchorRejection:
    candidate: LocationMatchCandidate
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class AnchorContext:
    legend_areas: tuple[BBox, ...]
    title_block_areas: tuple[BBox, ...]
    sheet_has_registered_ne: bool


def _center(bbox: BBox) -> tuple[float, float]:
    x0, y0, x1, y1 = bbox
    return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)


def _contains(area: BBox, x: float, y: float) -> bool:
    x0, y0, x1, y1 = area
    return x0 <= x <= x1 and y0 <= y <= y1


def _as_bbox(raw: Any) -> BBox | None:
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        try:
            x0, y0, x1, y1 = (float(v) for v in raw)
        except (TypeError, ValueError):
            return None
        return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    if not isinstance(raw, dict):
        return None
    if all(key in raw for key in ("x0", "y0", "x1", "y1")):
        try:
            x0, y0, x1, y1 = (
                float(raw["x0"]),
                float(raw["y0"]),
                float(raw["x1"]),
                float(raw["y1"]),
            )
        except (TypeError, ValueError):
            return None
        return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    if raw.get("type") == "rect" and all(key in raw for key in ("x", "y", "width", "height")):
        try:
            x = float(raw["x"])
            y = float(raw["y"])
            width = float(raw["width"])
            height = float(raw["height"])
        except (TypeError, ValueError):
            return None
        return (x, y, x + width, y + height)
    return None


def _legend_areas_from_stats(stats: Any) -> list[BBox]:
    if not isinstance(stats, dict):
        return []
    legend = stats.get("legend_index")
    if not isinstance(legend, dict):
        return []
    areas: list[BBox] = []
    rect = _as_bbox(legend.get("legend_rect"))
    if rect is not None:
        areas.append(rect)
    rows = legend.get("legend_line_rows")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key in ("label_bbox", "swatch_bbox"):
                parsed = _as_bbox(row.get(key))
                if parsed is not None:
                    areas.append(parsed)
    return areas


def _region_areas(session: Session, drawing_id: int, page: int) -> tuple[list[BBox], list[BBox]]:
    rows = (
        session.query(DrawingRegion)
        .filter(
            DrawingRegion.master_drawing_id == int(drawing_id),
            DrawingRegion.page == int(page),
        )
        .all()
    )
    legend: list[BBox] = []
    title: list[BBox] = []
    for row in rows:
        geometry = row.geometry if isinstance(row.geometry, dict) else None
        bbox = _as_bbox(geometry)
        if bbox is None:
            continue
        meta = geometry.get("meta") if isinstance(geometry, dict) else None
        zone = meta.get("zone") if isinstance(meta, dict) else None
        label = str(row.label or "").strip().lower()
        if zone == "legend_block" or label == "legend":
            legend.append(bbox)
        elif zone == "title_block" or label == "title block":
            title.append(bbox)
    return legend, title


def _default_title_block_areas() -> tuple[BBox, ...]:
    return (
        (TITLE_BLOCK_X_MIN, TITLE_BLOCK_Y_MIN, 1.0, 1.0),
        (TITLE_BLOCK_COLUMN_X_MIN, 0.0, 1.0, 1.0),
    )


def load_anchor_context(
    session: Session,
    drawing_id: int,
    *,
    page: int = 1,
) -> AnchorContext:
    drawing = session.get(Drawing, int(drawing_id))
    stats = getattr(drawing, "index_stats_json", None) if drawing is not None else None
    legend = _legend_areas_from_stats(stats)
    region_legend, region_title = _region_areas(session, drawing_id, page)
    legend.extend(region_legend)
    if not legend:
        fallback = resolved_legend_rect()
        if fallback is not None:
            legend.append(fallback)

    survey_rows = (
        session.query(DrawingSurveyPoint)
        .filter(DrawingSurveyPoint.drawing_id == int(drawing_id))
        .all()
    )
    return AnchorContext(
        legend_areas=tuple(legend),
        title_block_areas=(*_default_title_block_areas(), *region_title),
        sheet_has_registered_ne=_master_has_real_survey_coordinates(survey_rows),
    )


def anchor_rejection_reasons(
    candidate: LocationMatchCandidate,
    context: AnchorContext,
) -> tuple[str, ...]:
    """Reasons this anchor cannot be ranked. Empty when it is eligible."""
    reasons: list[str] = []
    bbox = candidate.bbox_fractional
    if bbox is not None:
        cx, cy = _center(bbox)
        if any(_contains(area, cx, cy) for area in context.legend_areas):
            reasons.append(REASON_LEGEND)
        if any(_contains(area, cx, cy) for area in context.title_block_areas):
            reasons.append(REASON_TITLE_BLOCK)
    if (
        candidate.method == ResolutionMethod.COORDINATE_LOOKUP
        and not context.sheet_has_registered_ne
    ):
        reasons.append(REASON_COORDINATE_WITHOUT_NE)
    return tuple(reasons)


def partition_anchors(
    candidates: Sequence[LocationMatchCandidate],
    context: AnchorContext,
) -> tuple[list[LocationMatchCandidate], list[AnchorRejection]]:
    """Filter first. The kept list is what ranking is allowed to see."""
    kept: list[LocationMatchCandidate] = []
    rejected: list[AnchorRejection] = []
    for candidate in candidates:
        reasons = anchor_rejection_reasons(candidate, context)
        if reasons:
            rejected.append(AnchorRejection(candidate=candidate, reasons=reasons))
        else:
            kept.append(candidate)
    return kept, rejected


def insufficient_rationale(rejections: Sequence[AnchorRejection]) -> str:
    """Status word plus the distinct reasons, in a stable order."""
    order = (REASON_LEGEND, REASON_TITLE_BLOCK, REASON_COORDINATE_WITHOUT_NE)
    present = {reason for rejection in rejections for reason in rejection.reasons}
    sentences = [reason for reason in order if reason in present]
    for rejection in rejections:
        for reason in rejection.reasons:
            if reason not in sentences:
                sentences.append(reason)
    if not sentences:
        return "insufficient"
    return "insufficient: " + " ".join(sentences)
