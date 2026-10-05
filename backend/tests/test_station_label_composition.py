"""Tests for composed plan-view station OCR recovery."""

from __future__ import annotations

from dataclasses import dataclass

from ai.pipelines.station_label_composition import extract_station_control_points_from_elements


@dataclass
class _El:
    page: int
    text: str
    bbox_json: dict[str, float]
    ocr_confidence: float = 0.9


def test_compose_station_from_split_tokens() -> None:
    elements = [
        _El(1, "10", {"x0": 0.40, "y0": 0.30, "x1": 0.42, "y1": 0.32}),
        _El(1, "+", {"x0": 0.42, "y0": 0.30, "x1": 0.43, "y1": 0.32}),
        _El(1, "90.95", {"x0": 0.43, "y0": 0.30, "x1": 0.48, "y1": 0.32}),
    ]
    points = extract_station_control_points_from_elements(elements)
    assert len(points) == 1
    assert points[0].station == "10+90.95"
    assert points[0].northing == 0.0
    assert points[0].meta_json.get("station_control") is True
