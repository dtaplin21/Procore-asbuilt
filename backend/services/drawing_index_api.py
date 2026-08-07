"""Helpers for drawing auto-index API responses (Phase 7)."""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy.orm import Session

from models.drawing_survey_point import DrawingSurveyPoint
from models.drawing_text_element import DrawingTextElement
from models.models import Drawing
from models.schemas import (
    DrawingIndexStatusResponse,
    DrawingSurveyPointResponse,
    DrawingTextElementResponse,
)


def drawing_index_status_response(drawing: Drawing) -> DrawingIndexStatusResponse:
    stats_raw = getattr(drawing, "index_stats_json", None)
    stats = dict(stats_raw) if isinstance(stats_raw, dict) else None

    scale_raw = getattr(drawing, "scale_json", None)
    scale = dict(scale_raw) if isinstance(scale_raw, dict) else None

    error_raw = getattr(drawing, "index_error", None)
    error = str(error_raw).strip() if error_raw else None

    return DrawingIndexStatusResponse(
        status=str(getattr(drawing, "index_status", "pending") or "pending"),
        stats=stats,
        scale=scale,
        error=error,
        indexed_at=getattr(drawing, "indexed_at", None),
    )


def list_drawing_text_elements(
    session: Session,
    *,
    master_drawing_id: int,
    page: int,
    limit: int,
) -> tuple[list[DrawingTextElementResponse], int]:
    query = session.query(DrawingTextElement).filter(
        DrawingTextElement.master_drawing_id == master_drawing_id,
        DrawingTextElement.page == page,
    )
    total = query.count()
    rows = (
        query.order_by(DrawingTextElement.id.asc())
        .offset(0)
        .limit(limit)
        .all()
    )
    items = [
        DrawingTextElementResponse(
            id=cast(int, row.id),
            page=cast(int, row.page),
            text=str(row.text),
            text_normalized=str(row.text_normalized),
            bbox_json=dict(row.bbox_json) if isinstance(row.bbox_json, dict) else {},
            legend_expansion=getattr(row, "legend_expansion", None),
            legend_codes_json=row.legend_codes_json if isinstance(row.legend_codes_json, list) else None,
            source=str(row.source),
        )
        for row in rows
    ]
    return items, total


def list_drawing_survey_points(
    session: Session,
    *,
    drawing_id: int,
    page: int,
    limit: int,
) -> tuple[list[DrawingSurveyPointResponse], int]:
    query = session.query(DrawingSurveyPoint).filter(
        DrawingSurveyPoint.drawing_id == drawing_id,
        DrawingSurveyPoint.page == page,
    )

    total = query.count()
    rows = (
        query.order_by(
            DrawingSurveyPoint.page.asc(),
            DrawingSurveyPoint.id.asc(),
        )
        .offset(0)
        .limit(limit)
        .all()
    )
    items = [
        DrawingSurveyPointResponse(
            id=cast(int, row.id),
            northing=cast(float, row.northing),
            easting=cast(float, row.easting),
            station=cast(str, row.station) if row.station is not None else None,
            structure_label=(
                cast(str, row.structure_label) if row.structure_label is not None else None
            ),
            label_bbox_json=(
                dict(row.label_bbox_json)
                if isinstance(row.label_bbox_json, dict)
                else {}
            ),
            page=cast(int, row.page),
            source=str(row.source),
        )
        for row in rows
    ]
    return items, total
