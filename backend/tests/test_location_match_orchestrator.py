"""Tests for location_match_orchestrator selection and status helpers."""

from __future__ import annotations

from ai.pipelines.drawing_location_resolver import ResolutionMethod
from ai.pipelines.location_match_orchestrator import (
    LocationMatchResult,
    MethodCandidate,
    match_status_from_result,
    select_best_location_match,
)
from services.inspection_match_persistence import MATCH_SCORE_THRESHOLD


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
