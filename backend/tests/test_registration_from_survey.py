"""Tests for survey-based registration transform computation."""

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.orm import Session

from ai.pipelines.drawing_location_resolver import RegistrationTransform
from ai.pipelines.location_match_orchestrator import _project_aux_bbox_to_master
from ai.pipelines.registration_from_survey import (
    ControlPointPair,
    compute_registration_for_linked_drawings,
    compute_registration_from_control_points,
    match_control_points,
    project_bbox_to_master,
    project_polyline_to_master,
)
from ai.pipelines.location_match_orchestrator import _ScopedSurveyPoint
from models.drawing_survey_point import DrawingSurveyPoint
from models.models import Drawing


def test_compute_registration_from_control_points_fits_translate_and_scale() -> None:
    pairs = (
        ControlPointPair(
            aux_xy=(0.2, 0.2),
            master_xy=(0.5, 0.47),
            northing=0.0,
            easting=0.0,
        ),
        ControlPointPair(
            aux_xy=(0.3, 0.25),
            master_xy=(0.55, 0.49),
            northing=0.0,
            easting=1.0,
        ),
    )

    transform = compute_registration_from_control_points(pairs)

    assert transform is not None
    assert transform.rotation_degrees == pytest.approx(0.0)
    assert project_polyline_to_master([(0.2, 0.2)], transform)[0] == pytest.approx(
        (0.5, 0.47)
    )
    assert project_polyline_to_master([(0.3, 0.25)], transform)[0] == pytest.approx(
        (0.55, 0.49)
    )


def test_compute_registration_from_control_points_single_pair_translate_only() -> None:
    transform = compute_registration_from_control_points(
        [
            ControlPointPair(
                aux_xy=(0.162, 0.208),
                master_xy=(0.518, 0.472),
                station="11+14.23",
                pairing_method="station",
            )
        ]
    )

    assert transform is not None
    assert transform.scale_x == pytest.approx(1.0)
    assert transform.scale_y == pytest.approx(1.0)
    assert transform.translate_x == pytest.approx(0.356)
    assert transform.translate_y == pytest.approx(0.264)
    assert project_polyline_to_master([(0.162, 0.208)], transform)[0] == pytest.approx(
        (0.518, 0.472)
    )


def test_match_control_points_pairs_by_station_without_master_ne(
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

    db_session.add_all(
        [
            DrawingSurveyPoint(
                drawing_id=aux_id,
                page=1,
                northing=2131764.84,
                easting=6051541.82,
                station="11+14.23",
                label_bbox_json={"x0": 0.15, "y0": 0.20, "x1": 0.17, "y1": 0.22},
                source="auto_index",
            ),
            DrawingSurveyPoint(
                drawing_id=master_id,
                page=1,
                northing=0.0,
                easting=0.0,
                station="11+14.23",
                label_bbox_json={"x0": 0.50, "y0": 0.46, "x1": 0.54, "y1": 0.48},
                source="manual",
                meta_json={"pairing": "station"},
            ),
        ]
    )
    db_session.commit()

    pairs = match_control_points(
        db_session,
        aux_drawing_id=aux_id,
        master_drawing_id=master_id,
    )

    assert len(pairs) == 1
    assert pairs[0].pairing_method == "station"
    transform, count, aux_drawing_id = compute_registration_for_linked_drawings(
        db_session,
        linked_drawing_ids=[aux_id],
        master_drawing_id=master_id,
    )
    assert count == 1
    assert aux_drawing_id == aux_id
    assert transform is not None


def test_project_bbox_to_master_uses_registration_transform() -> None:
    transform = RegistrationTransform(
        scale_x=1.0,
        scale_y=1.0,
        translate_x=0.356,
        translate_y=0.264,
        rotation_degrees=0.0,
    )
    aux_bbox = (0.162, 0.208, 0.170, 0.213)
    projected = project_bbox_to_master(aux_bbox, transform)

    assert projected[0] == pytest.approx(0.518, abs=0.01)
    assert projected[1] == pytest.approx(0.472, abs=0.01)


def test_match_control_points_pairs_shared_ne_on_aux_and_master(
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

    shared_n = 2131764.84
    shared_e = 6051541.82
    db_session.add_all(
        [
            DrawingSurveyPoint(
                drawing_id=aux_id,
                page=1,
                northing=shared_n,
                easting=shared_e,
                station="11+14.23",
                label_bbox_json={"x0": 0.15, "y0": 0.20, "x1": 0.17, "y1": 0.22},
                source="auto_index",
            ),
            DrawingSurveyPoint(
                drawing_id=master_id,
                page=1,
                northing=shared_n,
                easting=shared_e,
                station="11+14.23",
                label_bbox_json={"x0": 0.50, "y0": 0.46, "x1": 0.54, "y1": 0.48},
                source="auto_index",
            ),
            DrawingSurveyPoint(
                drawing_id=aux_id,
                page=1,
                northing=2131755.56,
                easting=6051476.07,
                station="11+14.23",
                label_bbox_json={"x0": 0.25, "y0": 0.24, "x1": 0.27, "y1": 0.26},
                source="auto_index",
            ),
            DrawingSurveyPoint(
                drawing_id=master_id,
                page=1,
                northing=2131755.56,
                easting=6051476.07,
                station="11+14.23",
                label_bbox_json={"x0": 0.55, "y0": 0.47, "x1": 0.57, "y1": 0.49},
                source="auto_index",
            ),
        ]
    )
    db_session.commit()

    pairs = match_control_points(
        db_session,
        aux_drawing_id=aux_id,
        master_drawing_id=master_id,
    )

    assert len(pairs) == 2
    transform, count, aux_drawing_id = compute_registration_for_linked_drawings(
        db_session,
        linked_drawing_ids=[aux_id],
        master_drawing_id=master_id,
    )
    assert count == 2
    assert aux_drawing_id == aux_id
    assert transform is not None
    for pair in pairs:
        assert project_polyline_to_master([pair.aux_xy], transform)[0] == pytest.approx(
            pair.master_xy,
            abs=0.01,
        )


def test_project_aux_bbox_to_master_with_computed_registration(
    db_session: Session,
    project,
) -> None:
    from services.storage import StorageService

    storage = StorageService(db_session)
    master = storage.create_drawing(
        project_id=cast(int, project.id),
        source="upload",
        name="Master.pdf",
        storage_key="drawings/master-reg.pdf",
        content_type="application/pdf",
    )
    aux = Drawing(
        project_id=project.id,
        source="linked_evidence",
        name="Install.pdf",
        storage_key="linked/install-reg.pdf",
        content_type="application/pdf",
    )
    db_session.add(aux)
    db_session.flush()
    master_id = cast(int, master.id)
    aux_id = cast(int, aux.id)

    db_session.add_all(
        [
            DrawingSurveyPoint(
                drawing_id=aux_id,
                page=1,
                northing=2131764.84,
                easting=6051541.82,
                station="11+14.23",
                label_bbox_json={"x0": 0.10, "y0": 0.20, "x1": 0.14, "y1": 0.24},
                source="auto_index",
            ),
            DrawingSurveyPoint(
                drawing_id=master_id,
                page=1,
                northing=2131764.84,
                easting=6051541.82,
                station="11+14.23",
                label_bbox_json={"x0": 0.48, "y0": 0.44, "x1": 0.52, "y1": 0.48},
                source="auto_index",
            ),
            DrawingSurveyPoint(
                drawing_id=aux_id,
                page=1,
                northing=2131755.56,
                easting=6051476.07,
                station="11+14.23",
                label_bbox_json={"x0": 0.30, "y0": 0.25, "x1": 0.34, "y1": 0.29},
                source="auto_index",
            ),
            DrawingSurveyPoint(
                drawing_id=master_id,
                page=1,
                northing=2131755.56,
                easting=6051476.07,
                station="11+14.23",
                label_bbox_json={"x0": 0.58, "y0": 0.46, "x1": 0.62, "y1": 0.50},
                source="auto_index",
            ),
        ]
    )
    db_session.commit()

    transform, _, _ = compute_registration_for_linked_drawings(
        db_session,
        linked_drawing_ids=[aux_id],
        master_drawing_id=master_id,
    )
    assert transform is not None

    aux_point = _ScopedSurveyPoint(
        drawing_id=aux_id,
        page=1,
        northing=2131764.84,
        easting=6051541.82,
        station="11+14.23",
        structure_label=None,
        label_bbox_json={"x0": 0.10, "y0": 0.20, "x1": 0.14, "y1": 0.24},
        ocr_confidence=0.95,
    )
    projected = _project_aux_bbox_to_master(
        db_session,
        aux_point=aux_point,
        master_drawing_id=master_id,
        registration_transform=transform,
    )

    assert projected is not None
    assert projected[0] == pytest.approx(0.48, abs=0.02)
    assert projected[1] == pytest.approx(0.44, abs=0.02)

    aux_polyline = ((0.10, 0.20), (0.30, 0.25), (0.30, 0.27))
    master_polyline = project_polyline_to_master(aux_polyline, transform)
    assert len(master_polyline) == 3
    assert master_polyline[0][0] < master_polyline[-1][0]
