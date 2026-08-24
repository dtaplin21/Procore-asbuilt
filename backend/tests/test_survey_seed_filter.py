"""Orchestrator tests for untrusted survey seed filtering."""

from __future__ import annotations

from typing import cast

from ai.pipelines.location_match_orchestrator import _scoped_point_from_row
from models.drawing_survey_point import DrawingSurveyPoint


def test_scoped_point_from_row_rejects_baseline_seed() -> None:
    row = DrawingSurveyPoint(
        drawing_id=661,
        page=1,
        northing=2131764.84,
        easting=6051541.82,
        station="11+14.23",
        structure_label="SMH",
        label_bbox_json={"x0": 0.518, "y0": 0.472, "x1": 0.566, "y1": 0.514},
        source="pre2_baseline_seed",
        ocr_confidence=0.95,
    )
    assert _scoped_point_from_row(row) is None


def test_scoped_point_from_row_accepts_auto_index() -> None:
    row = DrawingSurveyPoint(
        drawing_id=661,
        page=1,
        northing=2131764.84,
        easting=6051541.82,
        station="11+14.23",
        structure_label="SMH",
        label_bbox_json={"x0": 0.518, "y0": 0.472, "x1": 0.566, "y1": 0.514},
        source="auto_index",
        ocr_confidence=0.95,
    )
    scoped = _scoped_point_from_row(row)
    assert scoped is not None
    assert cast(int, scoped.drawing_id) == 661
