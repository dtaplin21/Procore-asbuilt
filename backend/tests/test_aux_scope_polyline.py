"""Tests for auxiliary scoped survey polyline builder."""

from __future__ import annotations

from ai.pipelines.aux_scope_polyline import build_aux_survey_polyline
from ai.pipelines.survey_point_extractor import SurveyPointRecord


def _point(
    *,
    drawing_id: int,
    station: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> SurveyPointRecord:
    return SurveyPointRecord(
        page=1,
        northing=2_131_700.0,
        easting=6_051_500.0,
        station=station,
        structure_label=None,
        label_bbox_json={"x0": x0, "y0": y0, "x1": x1, "y1": y1},
        northing_bbox_json=None,
        easting_bbox_json=None,
        ocr_confidence=0.9,
        meta_json={"drawing_id": drawing_id},
    )


def test_build_aux_survey_polyline_orders_vertices_by_chainage() -> None:
    scoped_points = (
        _point(drawing_id=1084, station="10+90.95", x0=0.27, y0=0.26, x1=0.31, y1=0.28),
        _point(drawing_id=1084, station="10+00", x0=0.08, y0=0.18, x1=0.12, y1=0.22),
        _point(drawing_id=1084, station="11+14.23", x0=0.15, y0=0.20, x1=0.17, y1=0.22),
        _point(drawing_id=1084, station="10+71", x0=0.18, y0=0.19, x1=0.22, y1=0.23),
    )

    result = build_aux_survey_polyline(
        scoped_points,
        station_from="10+00",
        station_to="10+90.95",
    )

    assert result is not None
    assert result.source_drawing_id == 1084
    assert result.stations == ("10+00", "10+71", "10+90.95")
    assert len(result.points) == 3
    assert result.points[0][0] < result.points[1][0] < result.points[2][0]


def test_build_aux_survey_polyline_requires_three_points_in_range() -> None:
    scoped_points = (
        _point(drawing_id=1084, station="10+00", x0=0.08, y0=0.18, x1=0.12, y1=0.22),
        _point(drawing_id=1084, station="10+90.95", x0=0.27, y0=0.26, x1=0.31, y1=0.28),
    )

    assert (
        build_aux_survey_polyline(
            scoped_points,
            station_from="10+00",
            station_to="10+90.95",
        )
        is None
    )


def test_build_aux_survey_polyline_picks_drawing_with_most_in_range_points() -> None:
    sparse = (
        _point(drawing_id=1001, station="10+00", x0=0.08, y0=0.18, x1=0.12, y1=0.22),
        _point(drawing_id=1001, station="10+90.95", x0=0.27, y0=0.26, x1=0.31, y1=0.28),
    )
    rich = (
        _point(drawing_id=1084, station="10+00", x0=0.08, y0=0.18, x1=0.12, y1=0.22),
        _point(drawing_id=1084, station="10+71", x0=0.18, y0=0.19, x1=0.22, y1=0.23),
        _point(drawing_id=1084, station="10+90.95", x0=0.27, y0=0.26, x1=0.31, y1=0.28),
    )

    result = build_aux_survey_polyline(
        (*sparse, *rich),
        station_from="10+00",
        station_to="10+90.95",
    )

    assert result is not None
    assert result.source_drawing_id == 1084
    assert len(result.points) == 3
