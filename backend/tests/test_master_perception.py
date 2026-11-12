"""Perception payload is the stored extraction, with vocabulary classified on read."""

from __future__ import annotations

from typing import cast
from unittest.mock import patch

from models.drawing_survey_point import DrawingSurveyPoint
from models.drawing_text_element import DrawingTextElement
from models.models import Drawing, Project
from services.storage import StorageService


def _master(db_session, project: Project) -> int:
    storage = StorageService(db_session)
    drawing = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="U2.C4.00",
        storage_key="projects/1/drawings/master.pdf",
        content_type="application/pdf",
    )
    drawing_id = cast(int, drawing.id)
    project.master_drawing_id = drawing_id
    row = db_session.get(Drawing, drawing_id)
    assert row is not None
    row.index_stats_json = {
        "sheetEntityGraph": {
            "1": {
                "page": 1,
                "lines": [
                    {
                        "points": [[0.1, 0.5], [0.4, 0.5]],
                        "confidence": 0.9,
                        "source": "pdf_vector",
                    }
                ],
            }
        }
    }
    db_session.add(
        DrawingTextElement(
            master_drawing_id=drawing_id,
            page=1,
            text="Rough In",
            text_normalized="rough in",
            bbox_json={"x0": 0.2, "y0": 0.2, "x1": 0.28, "y1": 0.24},
            ocr_confidence=0.91,
            source="native_pdf",
        )
    )
    db_session.add(
        DrawingTextElement(
            master_drawing_id=drawing_id,
            page=1,
            text="10+05.00",
            text_normalized="10+05.00",
            bbox_json={"x0": 0.4, "y0": 0.3, "x1": 0.48, "y1": 0.34},
            ocr_confidence=0.4,
            source="native_pdf",
        )
    )
    db_session.add(
        DrawingSurveyPoint(
            drawing_id=drawing_id,
            page=1,
            northing=100.0,
            easting=200.0,
            station="10+05.00",
            label_bbox_json={"x0": 0.4, "y0": 0.3, "x1": 0.48, "y1": 0.34},
            ocr_confidence=0.4,
            source="auto_index",
        )
    )
    db_session.commit()
    return drawing_id


def test_perception_classifies_stored_ocr_and_keeps_digitized_lines(client, db_session, project) -> None:
    drawing_id = _master(db_session, project)
    response = client.get(f"/api/testing/masters/{drawing_id}/perception?page=1")
    assert response.status_code == 200
    body = response.json()

    rough = next(item for item in body["ocr"] if item["text"] == "Rough In")
    assert rough["category"] == "inspection_type"
    assert rough["bbox"]["x"] == 200

    station = next(item for item in body["ocr"] if item["isStationLabel"])
    assert station["stationLabel"] == "10+05.00"
    assert station["parsedStation"] == 1005

    assert body["pipes"][0]["source"] == "sheet_digitization"
    assert body["pipes"][0]["polyline"][0] == {"x": 100, "y": 500}
    assert body["edges"] is None
    assert any("Canny" in warning for warning in body["warnings"])
    assert body["registration"]["quality"] == "fail"
    assert body["registration"]["pointCount"] == 1
    assert any("control-point starvation" in warning for warning in body["warnings"])


@patch("services.master_perception.settings")
def test_perception_warns_when_digitization_is_off(mock_settings, client, db_session, project) -> None:
    mock_settings.sheet_digitization_enabled = False
    drawing_id = _master(db_session, project)
    row = db_session.get(Drawing, drawing_id)
    assert row is not None
    row.index_stats_json = {}
    db_session.commit()

    response = client.get(f"/api/testing/masters/{drawing_id}/perception?page=1")
    assert response.status_code == 200
    warnings = response.json()["warnings"]
    assert any("SHEET_DIGITIZATION_ENABLED=false" in warning for warning in warnings)
    assert response.json()["pipes"] == []
