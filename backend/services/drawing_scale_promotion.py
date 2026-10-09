"""Apply viewport scale promotion after index seeding / sheet digitization."""

from __future__ import annotations

import logging
from typing import Any, cast

from sqlalchemy.orm import Session

from ai.pipelines.viewport_scale_promotion import (
    ScalePromotionResult,
    promote_scale,
    scale_promotion_audit_entries,
)
from models.drawing_viewport import DrawingViewport
from models.models import Drawing
from services.sheet_digitization import SHEET_ENTITY_GRAPH_KEY

logger = logging.getLogger(__name__)

_VIEWPORT_PROMOTION_SOURCE = "viewport_promotion"


def _viewport_ids_in_pages(pages: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for page_data in pages.values():
        if not isinstance(page_data, dict):
            continue
        for vp in page_data.get("viewports") or []:
            if isinstance(vp, dict) and vp.get("viewport_id"):
                ids.add(str(vp["viewport_id"]))
    return ids


def existing_scale_json_for_promotion(
    existing: dict[str, Any] | None,
    *,
    pages: dict[str, Any],
) -> dict[str, Any] | None:
    """Return scale to treat as set, or None when a stale promotion should be redone."""
    if not existing:
        return None
    if existing.get("source") != _VIEWPORT_PROMOTION_SOURCE:
        return existing
    source_vp = existing.get("source_viewport_id")
    known = _viewport_ids_in_pages(pages)
    if not known:
        return existing
    if source_vp and str(source_vp) in known:
        return existing
    return None


def _sheet_pages_from_viewports(session: Session, drawing_id: int) -> dict[str, Any]:
    rows = (
        session.query(DrawingViewport)
        .filter(DrawingViewport.drawing_id == int(drawing_id))
        .order_by(DrawingViewport.page.asc(), DrawingViewport.viewport_id.asc())
        .all()
    )
    pages: dict[str, Any] = {}
    for row in rows:
        page_key = str(int(row.page))
        pages.setdefault(page_key, {"viewports": []})
        bbox = row.bbox_json if isinstance(row.bbox_json, dict) else {}
        scale = row.scale_json if isinstance(row.scale_json, dict) else None
        pages[page_key]["viewports"].append(
            {
                "viewport_id": row.viewport_id,
                "kind": row.kind,
                "bbox_json": bbox,
                "scale": scale,
            }
        )
    return pages


def _resolve_sheet_entity_graph_pages(
    session: Session,
    drawing: Drawing,
) -> dict[str, Any]:
    db_pages = _sheet_pages_from_viewports(session, int(drawing.id))
    stats = cast(dict[str, Any] | None, drawing.index_stats_json)
    if not isinstance(stats, dict):
        return db_pages
    graphs = stats.get(SHEET_ENTITY_GRAPH_KEY)
    if not isinstance(graphs, dict) or not graphs:
        return db_pages
    graph_pages = dict(graphs)
    db_ids = _viewport_ids_in_pages(db_pages)
    graph_ids = _viewport_ids_in_pages(graph_pages)
    if db_ids and graph_ids and db_ids != graph_ids:
        logger.info(
            "viewport_scale_promotion prefer_db_viewports drawing_id=%s db_ids=%s graph_ids=%s",
            drawing.id,
            sorted(db_ids),
            sorted(graph_ids),
        )
        return db_pages
    return graph_pages if graph_pages else db_pages


def apply_viewport_scale_promotion(
    session: Session,
    drawing: Drawing,
) -> ScalePromotionResult:
    """Promote unambiguous viewport scale to ``drawing.scale_json`` and refresh stats."""
    pages = _resolve_sheet_entity_graph_pages(session, drawing)
    raw_existing = drawing.scale_json if isinstance(drawing.scale_json, dict) else None
    existing = existing_scale_json_for_promotion(raw_existing, pages=pages)
    if raw_existing is not None and existing is None:
        drawing.scale_json = None  # type: ignore[assignment]
        logger.info(
            "viewport_scale_promotion cleared_stale drawing_id=%s prior_viewport=%s",
            drawing.id,
            raw_existing.get("source_viewport_id"),
        )
    result = promote_scale(pages, existing)

    stats: dict[str, Any] = {}
    prior = cast(dict[str, Any] | None, drawing.index_stats_json)
    if isinstance(prior, dict):
        stats = dict(prior)

    stats.update(scale_promotion_audit_entries(result))
    if not result.ambiguous:
        stats.pop("scale_ambiguous", None)
        stats.pop("scale_candidates", None)
    if not result.promoted:
        stats.pop("scale_promotion", None)

    if result.promoted and result.scale_json is not None:
        drawing.scale_json = result.scale_json  # type: ignore[assignment]

    drawing.index_stats_json = stats  # type: ignore[assignment]
    session.flush()

    logger.info(
        "viewport_scale_promotion drawing_id=%s promoted=%s scale_found=%s ambiguous=%s reason=%s",
        drawing.id,
        result.promoted,
        result.scale_found,
        result.ambiguous,
        result.reason,
    )
    return result
