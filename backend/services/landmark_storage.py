"""Persist extracted landmarks on drawings."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ai.pipelines.landmark_extractor import LandmarkRecord
from models.drawing_landmark import DrawingLandmark


def persist_landmarks(
    session: Session,
    drawing_id: int,
    landmarks: list[LandmarkRecord],
    *,
    source: str,
) -> int:
    session.query(DrawingLandmark).filter(
        DrawingLandmark.drawing_id == drawing_id,
        DrawingLandmark.source == source,
    ).delete(synchronize_session=False)

    for record in landmarks:
        session.add(
            DrawingLandmark(
                drawing_id=drawing_id,
                page=record.page,
                landmark_type=record.landmark_type,
                bbox_json=record.bbox_json,
                hu_moments_json=record.hu_moments_json,
                ocr_confidence=record.ocr_confidence,
                source=source,
                meta_json=record.meta_json,
            )
        )

    session.flush()
    return len(landmarks)
