"""Persist extracted survey points on drawings."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ai.pipelines.survey_point_extractor import SurveyPointRecord
from models.drawing_survey_point import DrawingSurveyPoint


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
