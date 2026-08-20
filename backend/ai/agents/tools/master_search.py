"""Structured DB search tools for the agent (read-only)."""

from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy.orm import Session

from ai.pipelines.candidate_tile_selector import CandidateTile, find_candidate_tiles_from_clues
from ai.pipelines.drawing_location_resolver import MasterRegion
from services.legend_lookup import expand_abbreviation, find_codes_for_term
from services.region_index_loader import build_region_index


def search_master_by_clues(
    session: Session,
    *,
    drawing_ids: tuple[int, ...],
    clues: Sequence[Any],
    project_id: int | None,
    page: int = 1,
    limit_per_drawing: int = 20,
) -> list[CandidateTile]:
    """Search one or more drawings for tiles matching clues (legend-aware scoring)."""
    if not drawing_ids or not clues:
        return []

    merged: list[CandidateTile] = []
    seen: set[tuple[Any, ...]] = set()

    for drawing_id in drawing_ids:
        tiles = find_candidate_tiles_from_clues(
            session,
            drawing_id=drawing_id,
            page=page,
            clues=clues,
            limit=limit_per_drawing,
            project_id=project_id,
        )
        for tile in tiles:
            key = (
                tile.drawing_id,
                tile.page,
                tile.region_id,
                tile.text_element_id,
                tile.bbox_normalized,
                tile.text,
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(tile)

    return merged


def expand_term_with_legend(
    session: Session,
    term: str,
    *,
    project_id: int | None = None,
) -> list[str]:
    """Expand a clue/abbrev via legend (e.g. ``SS`` → ``SANITARY SEWER`` + related codes)."""
    cleaned = (term or "").strip()
    if not cleaned:
        return []

    expanded: list[str] = [cleaned]

    expansion = expand_abbreviation(session, cleaned, project_id)
    if expansion:
        expanded.append(expansion)

    expanded.extend(find_codes_for_term(session, cleaned, project_id))

    seen: set[str] = set()
    result: list[str] = []
    for value in expanded:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def load_master_regions(
    session: Session,
    master_drawing_id: int,
    *,
    include_untagged: bool = False,
) -> list[MasterRegion]:
    """Read-only region index for agent master search."""
    return build_region_index(
        session,
        master_drawing_id,
        include_untagged=include_untagged,
    ).regions
