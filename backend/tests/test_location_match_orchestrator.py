"""Tests for location_match_orchestrator selection and status helpers."""

from __future__ import annotations

from types import SimpleNamespace

from ai.pipelines.drawing_location_resolver import ResolutionMethod
from ai.pipelines.location_match_orchestrator import (
    LocationMatchResult,
    MethodCandidate,
    _enrich_evidence_stations,
    match_status_from_result,
    select_best_location_match,
)
from ai.pipelines.survey_point_extractor import SurveyPointRecord
from services.inspection_match_persistence import MATCH_SCORE_THRESHOLD


def _survey_point(*, station: str | None = None) -> SurveyPointRecord:
    return SurveyPointRecord(
        page=1,
        northing=2131764.84,
        easting=6051541.82,
        station=station,
        structure_label=None,
        label_bbox_json={"x0": 0.0, "y0": 0.0, "x1": 0.01, "y1": 0.01},
        northing_bbox_json=None,
        easting_bbox_json=None,
        ocr_confidence=0.9,
        meta_json={},
    )


def test_enrich_evidence_stations_from_clue_text() -> None:
    clues = [
        SimpleNamespace(clue_value="SSMH, STA. 10+90.95", value=None),
    ]
    enriched = _enrich_evidence_stations(
        [_survey_point(station=None)],
        clues=clues,
        evidence_text="",
    )
    assert len(enriched) == 1
    assert enriched[0].station == "10+90.95"


def test_enrich_evidence_stations_keeps_existing_station() -> None:
    clues = [SimpleNamespace(clue_value="STA. 11+00.00", value=None)]
    enriched = _enrich_evidence_stations(
        [_survey_point(station="10+90.95")],
        clues=clues,
        evidence_text="STA. 11+00.00",
    )
    assert enriched[0].station == "10+90.95"


def test_select_best_location_match_picks_highest_confidence() -> None:
    candidates = [
        MethodCandidate(
            method=ResolutionMethod.REFERENCE_LOOKUP,
            confidence=0.80,
            bbox_fractional=(0.1, 0.1, 0.2, 0.2),
        ),
        MethodCandidate(
            method=ResolutionMethod.COORDINATE_LOOKUP,
            confidence=0.96,
            bbox_fractional=(0.3, 0.3, 0.4, 0.4),
        ),
    ]
    winner = select_best_location_match(candidates)
    assert winner is not None
    assert winner.method == ResolutionMethod.COORDINATE_LOOKUP


def test_select_best_location_match_tiebreaks_by_method_priority_within_epsilon() -> None:
    candidates = [
        MethodCandidate(
            method=ResolutionMethod.REFERENCE_LOOKUP,
            confidence=0.960,
            bbox_fractional=(0.1, 0.1, 0.2, 0.2),
        ),
        MethodCandidate(
            method=ResolutionMethod.COORDINATE_LOOKUP,
            confidence=0.955,
            bbox_fractional=(0.3, 0.3, 0.4, 0.4),
        ),
    ]
    winner = select_best_location_match(candidates)
    assert winner is not None
    assert winner.method == ResolutionMethod.COORDINATE_LOOKUP


def test_select_best_location_match_ignores_candidates_without_bbox() -> None:
    candidates = [
        MethodCandidate(
            method=ResolutionMethod.REFERENCE_LOOKUP,
            confidence=0.99,
            bbox_fractional=None,
        ),
        MethodCandidate(
            method=ResolutionMethod.STATION_LOOKUP,
            confidence=0.70,
            bbox_fractional=(0.1, 0.1, 0.2, 0.2),
        ),
    ]
    winner = select_best_location_match(candidates)
    assert winner is not None
    assert winner.method == ResolutionMethod.STATION_LOOKUP


def test_match_status_from_result_contour_always_needs_review() -> None:
    result = LocationMatchResult(
        master_drawing_id=661,
        method=ResolutionMethod.CONTOUR_MATCH,
        confidence=0.99,
        bbox_fractional=(0.1, 0.1, 0.2, 0.2),
        page=1,
    )
    assert match_status_from_result(result) == "needs_review"


def test_match_status_from_result_coordinate_matched_at_threshold() -> None:
    result = LocationMatchResult(
        master_drawing_id=661,
        method=ResolutionMethod.COORDINATE_LOOKUP,
        confidence=MATCH_SCORE_THRESHOLD,
        bbox_fractional=(0.1, 0.1, 0.2, 0.2),
        page=1,
    )
    assert match_status_from_result(result) == "matched"


def test_match_status_from_result_unresolved_is_no_match() -> None:
    result = LocationMatchResult.unresolved(661)
    assert match_status_from_result(result) == "no_match"
