"""Match evidence survey points to master survey points."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, Sequence

COORD_MATCH_TOLERANCE_FT = 3.0
COORD_MATCH_HIGH_CONF_FT = 1.0
COORD_MATCH_REJECT_FT = 5.0


class _SurveyPointLike(Protocol):
    @property
    def northing(self) -> float: ...

    @property
    def easting(self) -> float: ...

    @property
    def ocr_confidence(self) -> float: ...


@dataclass(frozen=True)
class SurveyPointMatch:
    evidence: _SurveyPointLike
    master: _SurveyPointLike
    distance_ft: float
    confidence: float


def euclidean_survey_distance_ft(a: _SurveyPointLike, b: _SurveyPointLike) -> float:
    return math.hypot(float(a.northing) - float(b.northing), float(a.easting) - float(b.easting))


def confidence_for_distance(distance_ft: float) -> float:
    if distance_ft <= COORD_MATCH_HIGH_CONF_FT:
        return 0.98
    if distance_ft <= COORD_MATCH_TOLERANCE_FT:
        return 0.96
    if distance_ft <= COORD_MATCH_REJECT_FT:
        return 0.80
    return 0.0


def match_survey_points(
    evidence_points: Sequence[_SurveyPointLike],
    master_points: Sequence[_SurveyPointLike],
) -> SurveyPointMatch | None:
    """Greedy v1: return the best single evidence/master pair for overlay placement."""
    if not evidence_points or not master_points:
        return None

    sorted_evidence = sorted(
        evidence_points,
        key=lambda point: -float(getattr(point, "ocr_confidence", 0)),
    )
    best: SurveyPointMatch | None = None

    for evidence in sorted_evidence:
        for master in master_points:
            distance_ft = euclidean_survey_distance_ft(evidence, master)
            confidence = confidence_for_distance(distance_ft)
            if confidence <= 0:
                continue
            candidate = SurveyPointMatch(
                evidence=evidence,
                master=master,
                distance_ft=distance_ft,
                confidence=confidence,
            )
            if best is None or candidate.confidence > best.confidence:
                best = candidate
            elif (
                best is not None
                and candidate.confidence == best.confidence
                and candidate.distance_ft < best.distance_ft
            ):
                best = candidate

    return best
