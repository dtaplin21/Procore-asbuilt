"""Tests for survey point coordinate matching."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ai.pipelines.survey_point_matcher import (
    confidence_for_distance,
    match_survey_points,
)


@dataclass
class _Point:
    northing: float
    easting: float
    ocr_confidence: float = 0.95


def test_confidence_for_distance_two_and_half_feet() -> None:
    assert confidence_for_distance(2.5) == pytest.approx(0.96)


def test_survey_point_matcher_two_and_half_feet() -> None:
    evidence = [_Point(northing=2131764.84, easting=6051541.82)]
    master = [_Point(northing=2131767.34, easting=6051541.82)]

    match = match_survey_points(evidence, master)

    assert match is not None
    assert match.distance_ft == pytest.approx(2.5)
    assert match.confidence == pytest.approx(0.96)


def test_survey_point_matcher_rejects_six_feet() -> None:
    evidence = [_Point(northing=2131764.84, easting=6051541.82)]
    master = [_Point(northing=2131770.84, easting=6051541.82)]

    match = match_survey_points(evidence, master)

    assert match is None
    assert confidence_for_distance(6.0) == 0.0
