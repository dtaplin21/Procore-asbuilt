"""Candidate tile selection from extracted document clues.

This is the first narrowing step before expensive vision calls. Confidence is
backend-only and used only for ranking.

Candidate tiles are loaded from ``drawing_text_elements`` first (fine OCR/token
match), then ``drawing_regions`` (coarse tagged clusters). Overlapping tiles are
deduplicated with text-element matches preferred.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence, cast

from sqlalchemy.orm import Session

from ai.pipelines.clue_expander import expand_clue_value
from models.drawing_region import DrawingRegion
from models.drawing_text_element import DrawingTextElement
from services.region_index_loader import geometry_to_bounding_box

_BBOX_OVERLAP_THRESHOLD = 0.5
_BBOX_PAGE_EPSILON = 0.02
_GENERIC_LOCATION_CLUES = frozenset(
    {
        "utility",
        "site",
        "level",
        "floor",
        "corridor",
        "yard",
        "roof",
        "exterior",
        "interior",
        "area",
        "building",
    }
)


@dataclass(frozen=True)
class CandidateTile:
    """Searchable text region on a master drawing page."""

    drawing_id: str
    page: int
    text: str
    confidence: float
    bbox_normalized: tuple[float, float, float, float] | None
    region_id: int | None = None
    text_element_id: int | None = None


def _clue_value(clue: Any) -> str | None:
    raw = getattr(clue, "clue_value", None)
    if raw is None:
        raw = getattr(clue, "value", None)
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _clue_confidence(clue: Any) -> float:
    try:
        return float(getattr(clue, "confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _is_location_relevant(clue: Any) -> bool:
    return bool(getattr(clue, "location_relevant", False))


def _clue_matches_row(
    clue: Any,
    row_text: str,
    *,
    session: Session | None = None,
    project_id: int | None = None,
) -> bool:
    value = _clue_value(clue)
    if value is None:
        return False
    for expanded in expand_clue_value(value, session=session, project_id=project_id):
        if expanded.lower() in row_text:
            return True
    return False


def _bbox_from_json(bbox_json: object) -> tuple[float, float, float, float] | None:
    if not isinstance(bbox_json, dict):
        return None
    if all(key in bbox_json for key in ("x0", "y0", "x1", "y1")):
        return (
            float(bbox_json["x0"]),
            float(bbox_json["y0"]),
            float(bbox_json["x1"]),
            float(bbox_json["y1"]),
        )
    if all(key in bbox_json for key in ("x", "y", "width", "height")):
        x = float(bbox_json["x"])
        y = float(bbox_json["y"])
        width = float(bbox_json["width"])
        height = float(bbox_json["height"])
        return x, y, x + width, y + height
    return None


def bbox_on_page(
    bbox: tuple[float, float, float, float] | None,
    *,
    epsilon: float = _BBOX_PAGE_EPSILON,
) -> bool:
    """True when a fractional bbox lies within the page (0–1) with small slack."""
    if bbox is None:
        return False
    x0, y0, x1, y1 = bbox
    if x1 <= x0 or y1 <= y0:
        return False
    lo = -epsilon
    hi = 1.0 + epsilon
    return lo <= x0 <= hi and lo <= y0 <= hi and lo <= x1 <= hi and lo <= y1 <= hi


def _is_generic_location_clue(value: str) -> bool:
    tokens = value.strip().lower().split()
    return len(tokens) == 1 and tokens[0] in _GENERIC_LOCATION_CLUES


def _clue_specificity_bonus(value: str) -> float:
    tokens = [token for token in value.strip().split() if token]
    if len(tokens) <= 1:
        return 0.0
    return min(0.35, 0.12 * (len(tokens) - 1))


def _bbox_overlap_ratio(
    left: tuple[float, float, float, float] | None,
    right: tuple[float, float, float, float] | None,
) -> float:
    if left is None or right is None:
        return 0.0

    lx0, ly0, lx1, ly1 = left
    rx0, ry0, rx1, ry1 = right
    ix0 = max(lx0, rx0)
    iy0 = max(ly0, ry0)
    ix1 = min(lx1, rx1)
    iy1 = min(ly1, ry1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0

    intersection = (ix1 - ix0) * (iy1 - iy0)
    left_area = max((lx1 - lx0) * (ly1 - ly0), 1e-9)
    right_area = max((rx1 - rx0) * (ry1 - ry0), 1e-9)
    return intersection / min(left_area, right_area)


def _overlaps_existing_tile(
    tile: CandidateTile,
    kept: Sequence[CandidateTile],
    *,
    threshold: float = _BBOX_OVERLAP_THRESHOLD,
) -> bool:
    for existing in kept:
        if _bbox_overlap_ratio(tile.bbox_normalized, existing.bbox_normalized) >= threshold:
            return True
    return False


def _merge_candidate_tiles(
    text_element_tiles: Sequence[CandidateTile],
    region_tiles: Sequence[CandidateTile],
) -> list[CandidateTile]:
    """Prefer OCR text-element tiles; skip overlapping region tiles."""
    merged = list(text_element_tiles)
    for tile in region_tiles:
        if _overlaps_existing_tile(tile, merged):
            continue
        merged.append(tile)
    return merged


def _text_element_search_text(row: DrawingTextElement) -> str:
    parts: list[str] = []
    text = str(row.text).strip()
    if text:
        parts.append(text)

    expansion = row.legend_expansion
    if isinstance(expansion, str) and expansion.strip():
        parts.append(expansion.strip())

    codes = row.legend_codes_json
    if isinstance(codes, list):
        parts.extend(str(code).strip() for code in codes if str(code).strip())

    return " ".join(parts)


def _text_element_confidence(row: DrawingTextElement) -> float:
    ocr_confidence = float(cast(float, row.ocr_confidence))
    legend_expansion = getattr(row, "legend_expansion", None)
    legend_codes = getattr(row, "legend_codes_json", None)
    if legend_expansion or legend_codes:
        return max(0.85, ocr_confidence * 0.95)
    return max(0.80, ocr_confidence * 0.90)


def _load_text_element_tiles(
    session: Session,
    drawing_id: str | int,
    page: int,
) -> list[CandidateTile]:
    master_drawing_id = int(drawing_id)
    rows: list[DrawingTextElement] = (
        session.query(DrawingTextElement)
        .filter(
            DrawingTextElement.master_drawing_id == master_drawing_id,
            DrawingTextElement.page == page,
        )
        .order_by(DrawingTextElement.id.asc())
        .all()
    )

    tiles: list[CandidateTile] = []
    for row in rows:
        text = _text_element_search_text(row)
        if not text:
            continue
        tiles.append(
            CandidateTile(
                drawing_id=str(master_drawing_id),
                page=page,
                text=text,
                confidence=_text_element_confidence(row),
                bbox_normalized=_bbox_from_json(row.bbox_json),
                text_element_id=getattr(row, "id", None),
            )
        )
    return tiles


def _region_search_text(row: DrawingRegion) -> str:
    parts: list[str] = []
    label = getattr(row, "label", None)
    if isinstance(label, str) and label.strip():
        parts.append(label.strip())

    for field in ("location_tags", "inspection_type_tags"):
        tags = getattr(row, field, None) or []
        if isinstance(tags, (list, tuple)):
            parts.extend(str(tag).strip() for tag in tags if str(tag).strip())

    return " ".join(parts)


def _region_confidence(row: DrawingRegion) -> float:
    location_tags = getattr(row, "location_tags", None) or []
    inspection_tags = getattr(row, "inspection_type_tags", None) or []
    if location_tags or inspection_tags:
        return 0.75
    return 0.50


def _region_bbox_normalized(row: DrawingRegion) -> tuple[float, float, float, float] | None:
    geometry = getattr(row, "geometry", None)
    if not isinstance(geometry, dict):
        return None
    bbox = geometry_to_bounding_box(geometry)
    if bbox is None:
        return None
    return bbox.to_fractional()


def _load_region_tiles(
    session: Session,
    drawing_id: str | int,
    page: int,
) -> list[CandidateTile]:
    master_drawing_id = int(drawing_id)
    rows: list[DrawingRegion] = (
        session.query(DrawingRegion)
        .filter(
            DrawingRegion.master_drawing_id == master_drawing_id,
            DrawingRegion.page == page,
        )
        .order_by(DrawingRegion.id.asc())
        .all()
    )

    tiles: list[CandidateTile] = []
    for row in rows:
        text = _region_search_text(row)
        if not text:
            continue
        tiles.append(
            CandidateTile(
                drawing_id=str(master_drawing_id),
                page=page,
                text=text,
                confidence=_region_confidence(row),
                bbox_normalized=_region_bbox_normalized(row),
                region_id=getattr(row, "id", None),
            )
        )
    return tiles


def _load_candidate_tiles(
    session: Session,
    drawing_id: str | int,
    page: int,
) -> list[CandidateTile]:
    text_element_tiles = _load_text_element_tiles(session, drawing_id, page)
    region_tiles = _load_region_tiles(session, drawing_id, page)
    return _merge_candidate_tiles(text_element_tiles, region_tiles)


def _usable_location_clues(clues: Sequence[Any]) -> list[Any]:
    location_clues = [
        clue
        for clue in clues
        if _is_location_relevant(clue) and _clue_value(clue)
    ]
    if not location_clues:
        return []

    specific_values = {
        (_clue_value(clue) or "").strip().lower()
        for clue in location_clues
        if not _is_generic_location_clue(_clue_value(clue) or "")
    }
    if not specific_values:
        return location_clues

    # Prefer "Utility MR" over bare "Utility" when both are present.
    filtered: list[Any] = []
    for clue in location_clues:
        value = (_clue_value(clue) or "").strip()
        if not _is_generic_location_clue(value):
            filtered.append(clue)
            continue
        token = value.lower()
        if any(token in specific and specific != token for specific in specific_values):
            continue
        filtered.append(clue)
    return filtered or location_clues


def _match_score_for_tile(
    tile: CandidateTile,
    location_clues: Sequence[Any],
    *,
    session: Session | None = None,
    project_id: int | None = None,
) -> float:
    if not bbox_on_page(tile.bbox_normalized):
        return 0.0

    row_text = tile.text.lower()
    matched = [
        clue
        for clue in location_clues
        if _clue_matches_row(clue, row_text, session=session, project_id=project_id)
    ]
    if not matched:
        return 0.0

    best = 0.0
    for clue in matched:
        value = _clue_value(clue) or ""
        score = tile.confidence + _clue_confidence(clue) + _clue_specificity_bonus(value)
        if _is_generic_location_clue(value):
            score -= 0.25
        best = max(best, score)
    return best


def find_candidate_tiles_from_clues(
    session: Session,
    drawing_id: str | int,
    page: int,
    clues: Sequence[Any],
    limit: int = 20,
    project_id: int | None = None,
) -> list[CandidateTile]:
    location_clues = _usable_location_clues(clues)
    if not location_clues:
        return []

    tiles = _load_candidate_tiles(session, drawing_id, page)
    if not tiles:
        return []

    scored: list[tuple[float, CandidateTile]] = []

    for tile in tiles:
        internal_score = _match_score_for_tile(
            tile,
            location_clues,
            session=session,
            project_id=project_id,
        )
        if internal_score <= 0:
            continue
        scored.append((internal_score, tile))

    scored.sort(key=lambda item: -item[0])
    return [tile for _, tile in scored[:limit]]


def compute_tile_match_score(
    tile: CandidateTile,
    clues: Sequence[Any],
    *,
    session: Session | None = None,
    project_id: int | None = None,
) -> float:
    """Backend-only score used to choose matched vs needs_review."""
    location_clues = _usable_location_clues(clues)
    if not location_clues:
        return 0.0
    return _match_score_for_tile(
        tile,
        location_clues,
        session=session,
        project_id=project_id,
    )
