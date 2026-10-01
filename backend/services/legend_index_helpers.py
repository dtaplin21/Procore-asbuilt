"""Legend row clustering helpers for master index + sheet digitization."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ai.pipelines.legend_line_row_builder import (
    LegendLineRow,
    cluster_legend_line_rows,
    format_legend_row_manifest_text,
    legend_context_block,
)
from config import settings
from models.drawing_text_element import DrawingTextElement


def parse_fractional_rect(value: str | None) -> tuple[float, float, float, float] | None:
    """Parse ``x0,y0,x1,y1`` fractional bounds from env or CLI."""
    if not value or not str(value).strip():
        return None
    parts = [p.strip() for p in str(value).split(",")]
    if len(parts) != 4:
        raise ValueError(f"Expected four comma-separated fractions, got {value!r}")
    x0, y0, x1, y1 = (float(p) for p in parts)
    return x0, y0, x1, y1


def resolved_legend_rect() -> tuple[float, float, float, float] | None:
    return parse_fractional_rect(settings.drawing_index_legend_rect)


def _legend_cluster_sources() -> frozenset[str]:
    raw = (settings.drawing_index_legend_cluster_sources or "").strip()
    if not raw:
        return frozenset({"native_pdf", "document_ai"})
    return frozenset(s.strip().lower() for s in raw.split(",") if s.strip())


def text_elements_for_legend_clustering(
    session: Session,
    drawing_id: int,
    page: int = 1,
) -> list[DrawingTextElement]:
    """All indexed tokens on a page (no label cap), optionally filtered by OCR source."""
    rows = (
        session.query(DrawingTextElement)
        .filter(
            DrawingTextElement.master_drawing_id == int(drawing_id),
            DrawingTextElement.page == int(page),
        )
        .order_by(DrawingTextElement.id.asc())
        .all()
    )
    allowed = _legend_cluster_sources()
    if not allowed:
        return rows
    return [r for r in rows if str(r.source).lower() in allowed]


def cluster_legend_rows_for_drawing(
    session: Session,
    drawing_id: int,
    *,
    page: int = 1,
    legend_rect: tuple[float, float, float, float] | None = None,
) -> list[LegendLineRow]:
    rect = legend_rect if legend_rect is not None else resolved_legend_rect()
    elements = text_elements_for_legend_clustering(session, drawing_id, page=page)
    return cluster_legend_line_rows(elements, legend_rect=rect)


def legend_rows_to_audit_meta(rows: list[LegendLineRow]) -> list[dict[str, Any]]:
    return [
        {
            "index": index,
            "text": format_legend_row_manifest_text(row.text),
            "label_bbox": {
                "x0": row.label_bbox[0],
                "y0": row.label_bbox[1],
                "x1": row.label_bbox[2],
                "y1": row.label_bbox[3],
            },
            "swatch_bbox": {
                "x0": row.swatch_bbox[0],
                "y0": row.swatch_bbox[1],
                "x1": row.swatch_bbox[2],
                "y1": row.swatch_bbox[3],
            },
        }
        for index, row in enumerate(rows, start=1)
    ]


def legend_index_ai_payload(rows: list[LegendLineRow]) -> dict[str, Any]:
    """Structured legend summary for index stats / LLM context."""
    labels = [format_legend_row_manifest_text(row.text) for row in rows]
    return {
        "legend_line_labels": labels,
        "legend_context_block": legend_context_block(rows),
    }
