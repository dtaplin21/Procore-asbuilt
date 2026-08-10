"""Tests for plain-text survey point + station extraction."""

from __future__ import annotations

from ai.pipelines.survey_point_extractor import (
    extract_stations_from_text,
    extract_survey_points_from_plain_text,
)


def test_extract_stations_from_text() -> None:
    stations = extract_stations_from_text("SSMH, STA. 10+90.95 near N 2131764.84")
    assert stations == ["10+90.95"]


def test_plain_text_extract_attaches_nearby_station() -> None:
    text = (
        "Install at SSMH STA. 10+90.95 "
        "N 2131764.84 E 6051541.82 on sheet C4.20"
    )
    points = extract_survey_points_from_plain_text(text, scale_source="test")
    assert len(points) == 1
    assert points[0].northing == 2131764.84
    assert points[0].easting == 6051541.82
    assert points[0].station == "10+90.95"
    assert points[0].structure_label == "SSMH"
