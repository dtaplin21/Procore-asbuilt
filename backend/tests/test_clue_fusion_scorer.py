"""Tests for clue fusion scorer (PR-D D-1)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from ai.agents.evidence_dossier import (
    EvidenceDossier,
    ExpandedClue,
    LinkedAttachmentSummary,
    MasterDrawingContext,
)
from ai.pipelines.document_text_extraction import BoundingBox
from ai.pipelines.drawing_location_resolver import MasterRegion, ResolutionMethod
from ai.pipelines.evidence_kind_classifier import EvidenceKind
from ai.pipelines.location_match_orchestrator import LocationMatchCandidate
from ai.pipelines.clue_fusion_scorer import (
    FusedCandidateScore,
    fuse_candidate_scores,
    fuse_with_llm_tiebreak,
    select_fused_winner,
    _should_invoke_llm_tiebreak,
)
from models.models import EvidenceRecord


def _bbox(x: float, y: float, w: float, h: float) -> BoundingBox:
    return BoundingBox(x=x, y=y, width=w, height=h, page_width=1.0, page_height=1.0)


def _region(
    region_id: str,
    *,
    x: float,
    y: float,
    location_labels: tuple[str, ...],
    inspection_types: tuple[str, ...] = ("Underground Sanitary Sewer #1",),
) -> MasterRegion:
    return MasterRegion(
        region_id=region_id,
        master_drawing_id="1",
        inspection_types=inspection_types,
        location_labels=location_labels,
        bbox_on_master=_bbox(x, y, 0.08, 0.09),
    )


def _mock_dossier(
    *,
    regions: tuple[MasterRegion, ...],
    tiles: tuple[SimpleNamespace, ...] = (),
    legend_codes: tuple[str, ...] = ("SS", "SSMH"),
) -> EvidenceDossier:
    evidence = cast(EvidenceRecord, SimpleNamespace(id=1, project_id=2, meta={}))
    master_context = MasterDrawingContext(
        master_drawing_id=661,
        regions=regions,
        total_region_count=len(regions),
        untagged_region_count=0,
        scoped_survey_points=(),
        candidate_tiles=tiles,
        legend_codes_near_candidates=legend_codes,
    )
    expanded_clues = (
        ExpandedClue(
            original_value="COLO",
            clue_type="location_text",
            expanded_values=("COLO",),
            confidence=0.9,
        ),
        ExpandedClue(
            original_value="33-Sanitary Sewerage",
            clue_type="trade",
            expanded_values=("SS", "SANITARY SEWER", "33-Sanitary Sewerage"),
            confidence=0.85,
        ),
    )
    return EvidenceDossier(
        evidence_id=357,
        project_id=2,
        master_drawing_id=661,
        evidence=evidence,
        extraction=None,
        clues=(),
        expanded_clues=expanded_clues,
        evidence_text="Underground Sanitary Sewer at COLO",
        base_text="Underground Sanitary Sewer at COLO",
        evidence_kind=EvidenceKind.FORM,
        linked_attachments=(
            LinkedAttachmentSummary(
                url="https://example.com/install.pdf",
                filename="C4.20 Install.pdf",
                page_count=1,
                text_preview="Underground Sanitary Sewer at COLO parking lot",
                drawing_id=900,
            ),
        ),
        auxiliary_drawings=(),
        photo_paths=(),
        survey_points_meta=(),
        master_context=master_context,
        investigation_meta={},
    )


def test_fuse_candidate_scores_colo_candidate_wins() -> None:
    colo_region = _region("10", x=0.10, y=0.20, location_labels=("COLO",))
    roof_region = _region("20", x=0.70, y=0.70, location_labels=("ROOF",))

    colo_candidate = LocationMatchCandidate(
        method=ResolutionMethod.REFERENCE_LOOKUP,
        confidence=0.72,
        bbox_fractional=(0.10, 0.20, 0.18, 0.29),
        page=1,
        region_id=10,
        source_drawing_id=661,
        supporting_clues=("location:COLO", "inspection_type:Underground Sanitary Sewer #1"),
    )
    elsewhere_candidate = LocationMatchCandidate(
        method=ResolutionMethod.REFERENCE_LOOKUP,
        confidence=0.74,
        bbox_fractional=(0.70, 0.70, 0.78, 0.79),
        page=1,
        region_id=20,
        source_drawing_id=661,
        supporting_clues=("location:ROOF",),
    )

    tiles = (
        SimpleNamespace(
            text="COLO sanitary sewer SS-3",
            bbox_normalized=(0.11, 0.21, 0.17, 0.27),
            page=1,
            region_id=10,
            text_element_id=1,
            drawing_id="661",
            confidence=0.9,
        ),
        SimpleNamespace(
            text="ROOF DRAINAGE PLAN",
            bbox_normalized=(0.71, 0.71, 0.77, 0.77),
            page=1,
            region_id=20,
            text_element_id=2,
            drawing_id="661",
            confidence=0.8,
        ),
    )

    dossier = _mock_dossier(regions=(colo_region, roof_region), tiles=tiles)
    scores = fuse_candidate_scores(
        dossier,
        [elsewhere_candidate, colo_candidate],
    )
    winner = select_fused_winner(scores)

    assert winner is not None
    assert winner.candidate.region_id == 10
    assert scores[0].candidate.region_id == 10
    assert scores[0].fused_score > scores[1].fused_score

    dimensions = {hit.dimension for hit in winner.clue_hits if hit.weight > 0}
    assert "location" in dimensions
    assert "inspection_type" in dimensions
    assert "legend" in dimensions


def test_select_fused_winner_returns_none_without_actionable_scores() -> None:
    candidate = LocationMatchCandidate(
        method=ResolutionMethod.REFERENCE_LOOKUP,
        confidence=0.0,
        bbox_fractional=None,
        page=1,
    )
    dossier = _mock_dossier(regions=())
    scores = fuse_candidate_scores(dossier, [candidate])
    assert select_fused_winner(scores) is None


def _fused_score(
    candidate: LocationMatchCandidate,
    *,
    fused_score: float,
) -> FusedCandidateScore:
    return FusedCandidateScore(
        candidate=candidate,
        fused_score=fused_score,
        clue_hits=(),
        conflicts=(),
        rationale="deterministic",
    )


def test_should_invoke_llm_tiebreak_for_close_top_two() -> None:
    candidate_a = LocationMatchCandidate(
        method=ResolutionMethod.REFERENCE_LOOKUP,
        confidence=0.72,
        bbox_fractional=(0.10, 0.20, 0.18, 0.29),
        page=1,
        region_id=10,
    )
    candidate_b = LocationMatchCandidate(
        method=ResolutionMethod.REFERENCE_LOOKUP,
        confidence=0.71,
        bbox_fractional=(0.70, 0.70, 0.78, 0.79),
        page=1,
        region_id=20,
    )
    scores = [
        _fused_score(candidate_a, fused_score=0.70),
        _fused_score(candidate_b, fused_score=0.68),
    ]

    assert _should_invoke_llm_tiebreak(scores) is True


def test_should_invoke_llm_tiebreak_for_low_top_score() -> None:
    candidate = LocationMatchCandidate(
        method=ResolutionMethod.REFERENCE_LOOKUP,
        confidence=0.5,
        bbox_fractional=(0.1, 0.1, 0.2, 0.2),
        page=1,
    )
    scores = [_fused_score(candidate, fused_score=0.40)]

    assert _should_invoke_llm_tiebreak(scores) is True


def test_fuse_with_llm_tiebreak_skips_clear_winner() -> None:
    colo_region = _region("10", x=0.10, y=0.20, location_labels=("COLO",))
    roof_region = _region("20", x=0.70, y=0.70, location_labels=("ROOF",))
    colo_candidate = LocationMatchCandidate(
        method=ResolutionMethod.REFERENCE_LOOKUP,
        confidence=0.72,
        bbox_fractional=(0.10, 0.20, 0.18, 0.29),
        page=1,
        region_id=10,
        supporting_clues=("location:COLO",),
    )
    roof_candidate = LocationMatchCandidate(
        method=ResolutionMethod.REFERENCE_LOOKUP,
        confidence=0.74,
        bbox_fractional=(0.70, 0.70, 0.78, 0.79),
        page=1,
        region_id=20,
        supporting_clues=("location:ROOF",),
    )
    tiles = (
        SimpleNamespace(
            text="COLO sanitary sewer SS-3",
            bbox_normalized=(0.11, 0.21, 0.17, 0.27),
            page=1,
            region_id=10,
            text_element_id=1,
            drawing_id="661",
            confidence=0.9,
        ),
    )
    dossier = _mock_dossier(regions=(colo_region, roof_region), tiles=tiles)
    scores = fuse_candidate_scores(dossier, [colo_candidate, roof_candidate])

    with patch("ai.pipelines.clue_fusion_scorer._call_fusion_llm") as mock_llm:
        result = fuse_with_llm_tiebreak(dossier, scores)

    assert result is None
    mock_llm.assert_not_called()


def test_fuse_with_llm_tiebreak_returns_none_without_api_key() -> None:
    candidate = LocationMatchCandidate(
        method=ResolutionMethod.REFERENCE_LOOKUP,
        confidence=0.5,
        bbox_fractional=(0.1, 0.1, 0.2, 0.2),
        page=1,
    )
    scores = [_fused_score(candidate, fused_score=0.4)]
    dossier = _mock_dossier(regions=())

    with patch("ai.pipelines.clue_fusion_scorer._call_fusion_llm", return_value=None):
        assert fuse_with_llm_tiebreak(dossier, scores) is None


@patch("ai.pipelines.clue_fusion_scorer._call_fusion_llm")
def test_fuse_with_llm_tiebreak_reorders_ambiguous_candidate(mock_llm) -> None:
    colo_region = _region("10", x=0.10, y=0.20, location_labels=("COLO",))
    roof_region = _region("20", x=0.70, y=0.70, location_labels=("ROOF",))
    colo_candidate = LocationMatchCandidate(
        method=ResolutionMethod.REFERENCE_LOOKUP,
        confidence=0.72,
        bbox_fractional=(0.10, 0.20, 0.18, 0.29),
        page=1,
        region_id=10,
        supporting_clues=("location:COLO",),
    )
    roof_candidate = LocationMatchCandidate(
        method=ResolutionMethod.REFERENCE_LOOKUP,
        confidence=0.74,
        bbox_fractional=(0.70, 0.70, 0.78, 0.79),
        page=1,
        region_id=20,
        supporting_clues=("location:ROOF",),
    )
    dossier = _mock_dossier(regions=(colo_region, roof_region))
    scores = [
        _fused_score(roof_candidate, fused_score=0.70),
        _fused_score(colo_candidate, fused_score=0.68),
    ]
    mock_llm.return_value = {
        "best_index": 1,
        "confidence": 0.82,
        "rationale": "COLO matches sanitary sewer location terms.",
        "conflicts": [],
    }

    result = fuse_with_llm_tiebreak(dossier, scores)

    assert result is not None
    assert result.candidate.region_id == 10
    assert "llm=COLO matches sanitary sewer location terms." in result.rationale
    assert result.fused_score >= scores[1].fused_score
    mock_llm.assert_called_once()
