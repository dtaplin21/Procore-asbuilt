"""Anchor rejection happens before ranking."""

from __future__ import annotations

from ai.pipelines.anchor_eligibility import (
    REASON_COORDINATE_WITHOUT_NE,
    REASON_LEGEND,
    REASON_TITLE_BLOCK,
    AnchorContext,
    insufficient_rationale,
    partition_anchors,
)
from ai.pipelines.drawing_location_resolver import ResolutionMethod
from ai.pipelines.location_match_orchestrator import LocationMatchCandidate

_LEGEND = (0.70, 0.02, 0.98, 0.135)
_NO_NE = AnchorContext(
    legend_areas=(_LEGEND,),
    title_block_areas=((0.75, 0.75, 1.0, 1.0), (0.88, 0.0, 1.0, 1.0)),
    sheet_has_registered_ne=False,
)
_WITH_NE = AnchorContext(
    legend_areas=(_LEGEND,),
    title_block_areas=((0.75, 0.75, 1.0, 1.0), (0.88, 0.0, 1.0, 1.0)),
    sheet_has_registered_ne=True,
)


def _candidate(
    method: ResolutionMethod,
    bbox: tuple[float, float, float, float],
    *,
    confidence: float,
) -> LocationMatchCandidate:
    return LocationMatchCandidate(
        method=method,
        confidence=confidence,
        bbox_fractional=bbox,
        page=1,
    )


def test_legend_and_unregistered_coordinate_lose_to_a_lower_score() -> None:
    legend_coordinate = _candidate(
        ResolutionMethod.COORDINATE_LOOKUP,
        (0.849, 0.029, 0.862, 0.051),
        confidence=0.98,
    )
    station = _candidate(
        ResolutionMethod.STATION_LOOKUP,
        (0.20, 0.30, 0.24, 0.34),
        confidence=0.50,
    )
    scored = [(0.659, legend_coordinate), (0.502, station)]

    kept, rejected = partition_anchors([legend_coordinate, station], _NO_NE)

    assert kept == [station]
    assert rejected[0].candidate is legend_coordinate
    assert REASON_LEGEND in rejected[0].reasons
    assert REASON_COORDINATE_WITHOUT_NE in rejected[0].reasons
    ranked = sorted(
        (score, candidate) for score, candidate in scored if candidate in kept
    )
    assert ranked[-1][1] is station
    rationale = insufficient_rationale(rejected)
    assert rationale.startswith("insufficient:")
    assert "legend" in rationale
    assert "registered N/E" in rationale


def test_title_block_box_is_rejected_before_a_plan_anchor() -> None:
    title_block = _candidate(
        ResolutionMethod.REFERENCE_LOOKUP,
        (0.91, 0.40, 0.96, 0.48),
        confidence=0.9,
    )
    plan = _candidate(
        ResolutionMethod.STATION_LOOKUP,
        (0.30, 0.40, 0.34, 0.44),
        confidence=0.4,
    )

    kept, rejected = partition_anchors([title_block, plan], _WITH_NE)

    assert kept == [plan]
    assert rejected[0].reasons == (REASON_TITLE_BLOCK,)


def test_coordinate_in_the_plan_is_kept_when_the_sheet_has_registered_ne() -> None:
    coordinate = _candidate(
        ResolutionMethod.COORDINATE_LOOKUP,
        (0.16, 0.20, 0.18, 0.22),
        confidence=0.98,
    )

    kept, rejected = partition_anchors([coordinate], _WITH_NE)

    assert kept == [coordinate]
    assert rejected == []


def test_coordinate_in_the_plan_is_insufficient_without_registered_ne() -> None:
    coordinate = _candidate(
        ResolutionMethod.COORDINATE_LOOKUP,
        (0.16, 0.20, 0.18, 0.22),
        confidence=0.98,
    )

    kept, rejected = partition_anchors([coordinate], _NO_NE)

    assert kept == []
    assert rejected[0].reasons == (REASON_COORDINATE_WITHOUT_NE,)
    assert insufficient_rationale(rejected) == (
        "insufficient: " + REASON_COORDINATE_WITHOUT_NE
    )
