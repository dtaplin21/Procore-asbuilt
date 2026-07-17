"""Candidate tile selection from extracted document clues.

This is the first narrowing step before expensive vision calls. Confidence is
backend-only and used only for ranking.

This repo does not yet have a ``DrawingTextElement`` OCR table. Candidate tiles
are loaded from ``drawing_regions`` (label + location/inspection tags + geometry)
which is the existing master-drawing location index used by
``drawing_location_resolver.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from sqlalchemy.orm import Session

from ai.pipelines.clue_expander import expand_clue_value
from models.drawing_region import DrawingRegion
from services.region_index_loader import geometry_to_bounding_box


@dataclass(frozen=True)
class CandidateTile:
    """Searchable text region on a master drawing page."""

    drawing_id: str
    page: int
    text: str
    confidence: float
    bbox_normalized: tuple[float, float, float, float] | None
    region_id: int | None = None


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


def _clue_matches_row(clue: Any, row_text: str) -> bool:
    value = _clue_value(clue)
    if value is None:
        return False
    for expanded in expand_clue_value(value):
        if expanded.lower() in row_text:
            return True
    return False


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


def _load_candidate_tiles(
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


def find_candidate_tiles_from_clues(
    session: Session,
    drawing_id: str | int,
    page: int,
    clues: Sequence[Any],
    limit: int = 20,
) -> list[CandidateTile]:
    location_clues = [
        clue
        for clue in clues
        if _is_location_relevant(clue) and _clue_value(clue)
    ]

    if not location_clues:
        return []

    tiles = _load_candidate_tiles(session, drawing_id, page)
    if not tiles:
        return []

    scored: list[tuple[float, CandidateTile]] = []

    for tile in tiles:
        row_text = tile.text.lower()
        matched = [clue for clue in location_clues if _clue_matches_row(clue, row_text)]
        if not matched:
            continue

        strongest_clue_confidence = max(_clue_confidence(clue) for clue in matched)
        internal_score = tile.confidence + strongest_clue_confidence
        scored.append((internal_score, tile))

    scored.sort(key=lambda item: -item[0])
    return [tile for _, tile in scored[:limit]]


def compute_tile_match_score(tile: CandidateTile, clues: Sequence[Any]) -> float:
    """Backend-only score used to choose matched vs needs_review."""
    location_clues = [
        clue
        for clue in clues
        if _is_location_relevant(clue) and _clue_value(clue)
    ]
    if not location_clues:
        return 0.0

    row_text = tile.text.lower()
    matched = [clue for clue in location_clues if _clue_matches_row(clue, row_text)]
    if not matched:
        return 0.0

    strongest_clue_confidence = max(_clue_confidence(clue) for clue in matched)
    return tile.confidence + strongest_clue_confidence
