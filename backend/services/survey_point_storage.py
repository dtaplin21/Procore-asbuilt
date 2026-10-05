"""Persist extracted survey points on drawings."""

from __future__ import annotations

from typing import cast

from sqlalchemy.orm import Session

from ai.pipelines.survey_point_extractor import SurveyPointRecord
from models.drawing_survey_point import DrawingSurveyPoint


def persist_station_control_points(
    session: Session,
    drawing_id: int,
    points: list[SurveyPointRecord],
    *,
    source: str,
) -> int:
    """Upsert station-keyed controls without wiping N/E ``auto_index`` survey rows."""
    if not points:
        return 0

    existing = (
        session.query(DrawingSurveyPoint)
        .filter(
            DrawingSurveyPoint.drawing_id == drawing_id,
            DrawingSurveyPoint.source == source,
        )
        .all()
    )
    by_station = {
        (cast(str | None, row.station) or "").strip().upper(): row for row in existing
    }
    written = 0
    for point in points:
        station_key = (point.station or "").strip().upper()
        row = by_station.get(station_key)
        if row is None:
            session.add(
                DrawingSurveyPoint(
                    drawing_id=drawing_id,
                    page=point.page,
                    northing=point.northing,
                    easting=point.easting,
                    station=point.station,
                    structure_label=point.structure_label,
                    label_bbox_json=point.label_bbox_json,
                    northing_bbox_json=point.northing_bbox_json,
                    easting_bbox_json=point.easting_bbox_json,
                    ocr_confidence=point.ocr_confidence,
                    source=source,
                    meta_json=point.meta_json,
                )
            )
            written += 1
            continue
        row.page = point.page  # type: ignore[assignment]
        row.northing = point.northing  # type: ignore[assignment]
        row.easting = point.easting  # type: ignore[assignment]
        row.station = point.station  # type: ignore[assignment]
        row.structure_label = point.structure_label  # type: ignore[assignment]
        row.label_bbox_json = point.label_bbox_json  # type: ignore[assignment]
        row.northing_bbox_json = point.northing_bbox_json  # type: ignore[assignment]
        row.easting_bbox_json = point.easting_bbox_json  # type: ignore[assignment]
        row.ocr_confidence = point.ocr_confidence  # type: ignore[assignment]
        row.meta_json = point.meta_json  # type: ignore[assignment]
        written += 1

    session.flush()
    return written


def persist_survey_points(
    session: Session,
    drawing_id: int,
    points: list[SurveyPointRecord],
    *,
    source: str,
) -> int:
    session.query(DrawingSurveyPoint).filter(
        DrawingSurveyPoint.drawing_id == drawing_id,
        DrawingSurveyPoint.source == source,
    ).delete(synchronize_session=False)

    for point in points:
        session.add(
            DrawingSurveyPoint(
                drawing_id=drawing_id,
                page=point.page,
                northing=point.northing,
                easting=point.easting,
                station=point.station,
                structure_label=point.structure_label,
                label_bbox_json=point.label_bbox_json,
                northing_bbox_json=point.northing_bbox_json,
                easting_bbox_json=point.easting_bbox_json,
                ocr_confidence=point.ocr_confidence,
                source=source,
                meta_json=point.meta_json,
            )
        )

    session.flush()
    return len(points)
