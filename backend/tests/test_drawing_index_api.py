"""Tests for drawing auto-index API endpoints (Phase 7)."""

from __future__ import annotations

from typing import cast
from unittest.mock import patch

from models.drawing_survey_point import DrawingSurveyPoint
from models.drawing_text_element import DrawingTextElement
from models.models import Drawing, JobQueue
from services.drawing_index_jobs import JOB_TYPE
from services.storage import StorageService


def _drawing_base(db_session, project) -> tuple[int, int]:
    storage = StorageService(db_session)
    drawing = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="Master.pdf",
        storage_key="projects/1/drawings/master.pdf",
        content_type="application/pdf",
    )
    drawing_id = cast(int, drawing.id)
    project_id = cast(int, project.id)
    return project_id, drawing_id


def test_get_drawing_includes_index_fields(client, db_session, project) -> None:
    project_id, drawing_id = _drawing_base(db_session, project)
    row = db_session.get(Drawing, drawing_id)
    assert row is not None
    setattr(row, "index_status", "ready")
    setattr(
        row,
        "index_stats_json",
        {"pages": 3, "regions": 842, "text_elements": 1200, "scale_found": True},
    )
    setattr(row, "scale_json", {"raw_text": '1" = 10\'', "real_feet_per_paper_inch": 10.0})
    db_session.commit()

    response = client.get(f"/api/projects/{project_id}/drawings/{drawing_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["indexStatus"] == "ready"
    assert body["indexStatsJson"]["regions"] == 842
    assert body["scaleJson"]["raw_text"] == '1" = 10\''


def test_get_drawing_index_status(client, db_session, project) -> None:
    project_id, drawing_id = _drawing_base(db_session, project)
    row = db_session.get(Drawing, drawing_id)
    assert row is not None
    setattr(row, "index_status", "processing")
    setattr(row, "index_stats_json", {"pages": 1, "regions": 0, "text_elements": 0})
    db_session.commit()

    response = client.get(
        f"/api/projects/{project_id}/drawings/{drawing_id}/index-status"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processing"
    assert body["stats"]["pages"] == 1
    assert body["scale"] is None
    assert body["error"] is None


@patch("api.routes.drawings.settings")
@patch("api.routes.drawings.enqueue_drawing_index_job")
def test_reindex_drawing_enqueues_job(
    mock_enqueue,
    mock_settings,
    client,
    db_session,
    project,
) -> None:
    mock_settings.drawing_index_enabled = True
    project_id, drawing_id = _drawing_base(db_session, project)
    row = db_session.get(Drawing, drawing_id)
    assert row is not None
    setattr(row, "processing_status", "ready")
    setattr(row, "index_status", "ready")
    db_session.commit()

    mock_enqueue.return_value = JobQueue(
        id=999,
        user_id=1,
        company_id=1,
        project_id=project_id,
        job_type=JOB_TYPE,
        status="pending",
        input_data={"drawing_id": drawing_id},
    )

    response = client.post(
        f"/api/projects/{project_id}/drawings/{drawing_id}/reindex"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == 999
    assert body["index_status"] == "pending"
    mock_enqueue.assert_called_once()


def test_list_drawing_text_elements(client, db_session, project) -> None:
    project_id, drawing_id = _drawing_base(db_session, project)
    db_session.add_all(
        [
            DrawingTextElement(
                master_drawing_id=drawing_id,
                page=1,
                text="SS",
                text_normalized="ss",
                bbox_json={"x0": 0.1, "y0": 0.1, "x1": 0.12, "y1": 0.12},
                ocr_confidence=0.95,
                source="native_pdf",
            ),
            DrawingTextElement(
                master_drawing_id=drawing_id,
                page=1,
                text="COLO",
                text_normalized="colo",
                bbox_json={"x0": 0.2, "y0": 0.2, "x1": 0.24, "y1": 0.22},
                ocr_confidence=0.95,
                source="native_pdf",
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        f"/api/projects/{project_id}/drawings/{drawing_id}/text-elements?page=1&limit=500"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert len(body["items"]) == 2
    texts = {item["text"] for item in body["items"]}
    assert texts == {"SS", "COLO"}


def test_list_drawing_survey_points(client, db_session, project) -> None:
    project_id, drawing_id = _drawing_base(db_session, project)
    db_session.add_all(
        [
            DrawingSurveyPoint(
                drawing_id=drawing_id,
                page=1,
                northing=2131764.84,
                easting=6051541.82,
                station="12+50",
                structure_label="SS-1",
                label_bbox_json={"x0": 0.1, "y0": 0.1, "x1": 0.2, "y1": 0.15},
                source="auto_index",
            ),
            DrawingSurveyPoint(
                drawing_id=drawing_id,
                page=1,
                northing=2131800.0,
                easting=6051600.0,
                station=None,
                structure_label=None,
                label_bbox_json={"x0": 0.3, "y0": 0.3, "x1": 0.4, "y1": 0.35},
                source="auto_index",
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        f"/api/projects/{project_id}/drawings/{drawing_id}/survey-points?page=1&limit=500"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert len(body["items"]) == 2

    first = body["items"][0]
    assert first["northing"] == 2131764.84
    assert first["easting"] == 6051541.82
    assert first["station"] == "12+50"
    assert first["structure_label"] == "SS-1"
    assert first["label_bbox_json"]["x0"] == 0.1
    assert first["page"] == 1
    assert first["source"] == "auto_index"


def test_list_drawing_survey_points_not_found(client, db_session, project) -> None:
    project_id, _drawing_id = _drawing_base(db_session, project)
    response = client.get(
        f"/api/projects/{project_id}/drawings/999999/survey-points"
    )
    assert response.status_code == 404
