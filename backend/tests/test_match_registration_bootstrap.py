"""Tests for master/aux registration bootstrap."""

from __future__ import annotations

from typing import cast

from ai.pipelines.station_label_composition import extract_station_control_points_from_elements
from dataclasses import dataclass
from models.drawing_survey_point import DrawingSurveyPoint
from models.models import Drawing
from services.match_registration_bootstrap import bootstrap_master_station_controls
from sqlalchemy.orm import Session


@dataclass
class _El:
    page: int
    text: str
    bbox_json: dict[str, float]
    ocr_confidence: float = 0.9


def test_bootstrap_master_station_controls_pairs_aux_station(
    db_session: Session,
    project,
) -> None:
    project_id = cast(int, project.id)
    master = Drawing(
        project_id=project_id,
        source="upload",
        name="Master.pdf",
        content_type="application/pdf",
        processing_status="ready",
        index_status="ready",
    )
    aux = Drawing(
        project_id=project_id,
        source="linked_evidence",
        name="Install.pdf",
        content_type="application/pdf",
        processing_status="ready",
        index_status="ready",
    )
    db_session.add_all([master, aux])
    db_session.flush()
    master_id = cast(int, master.id)
    aux_id = cast(int, aux.id)

    db_session.add(
        DrawingSurveyPoint(
            drawing_id=aux_id,
            page=1,
            northing=2131764.84,
            easting=6051541.82,
            station="10+90.95",
            label_bbox_json={"x0": 0.15, "y0": 0.20, "x1": 0.17, "y1": 0.22},
            source="auto_index",
        )
    )
    db_session.commit()

    elements = [
        _El(1, "10", {"x0": 0.40, "y0": 0.30, "x1": 0.42, "y1": 0.32}),
        _El(1, "+", {"x0": 0.42, "y0": 0.30, "x1": 0.43, "y1": 0.32}),
        _El(1, "90.95", {"x0": 0.43, "y0": 0.30, "x1": 0.48, "y1": 0.32}),
    ]
    assert len(extract_station_control_points_from_elements(elements)) == 1

    from models.drawing_text_element import DrawingTextElement

    for el in elements:
        db_session.add(
            DrawingTextElement(
                master_drawing_id=master_id,
                page=el.page,
                text=el.text,
                text_normalized=el.text.upper(),
                bbox_json=el.bbox_json,
                ocr_confidence=el.ocr_confidence,
                source="document_ai",
            )
        )
    db_session.commit()

    count = bootstrap_master_station_controls(
        db_session,
        master_drawing_id=master_id,
        linked_drawing_ids=[aux_id],
        target_stations={"10+90.95"},
    )
    assert count >= 1

    master_rows = (
        db_session.query(DrawingSurveyPoint)
        .filter(DrawingSurveyPoint.drawing_id == master_id)
        .all()
    )
    assert any(cast(str | None, row.station) == "10+90.95" for row in master_rows)
