"""Strict inspection placement (no fallbacks)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from ai.agents.inspection_location_agent import InspectionLocationAgent
from ai.pipelines.clue_fusion_scorer import FusedCandidateScore
from ai.pipelines.drawing_location_resolver import ResolutionMethod
from ai.pipelines.location_match_orchestrator import LocationMatchCandidate
from services.inspection_placement_errors import (
    INSPECTION_NO_ANCHOR_INTERSECTING_LINE,
    INSPECTION_NO_FUSED_WINNER,
    INSPECTION_NO_MASTER_SHEET_LINE,
    InspectionPlacementError,
)
from services.inspection_match_persistence import MATCH_SCORE_THRESHOLD
from tests.test_inspection_location_agent import (
    _seed_ready_master_run,
    _utility_line_dossier,
)


@patch(
    "ai.agents.inspection_location_agent.apply_vision_to_fused_scores",
    side_effect=lambda _dossier, scores, **kwargs: scores,
)
@patch("ai.agents.inspection_location_agent.generate_all_location_candidates")
@patch("ai.agents.inspection_location_agent.build_evidence_dossier")
@patch("ai.agents.inspection_location_agent.placement_strict_enabled", return_value=True)
def test_strict_raises_when_no_fused_winner(
    _strict: object,
    mock_build_dossier: object,
    mock_generate_candidates: object,
    _vision: object,
    db_session: Session,
) -> None:
    _run, evidence_id, master_drawing_id, region_id = _seed_ready_master_run(db_session)
    mock_build_dossier.return_value = _utility_line_dossier(
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
        region_id=region_id,
    )
    mock_generate_candidates.return_value = [
        LocationMatchCandidate(
            method=ResolutionMethod.REFERENCE_LOOKUP,
            confidence=0.5,
            bbox_fractional=None,
            page=1,
        )
    ]

    agent = InspectionLocationAgent()
    with pytest.raises(InspectionPlacementError) as exc_info:
        agent.run(db_session, evidence_id=evidence_id, master_drawing_id=master_drawing_id)

    assert exc_info.value.code == INSPECTION_NO_FUSED_WINNER


@patch(
    "ai.agents.inspection_location_agent.apply_vision_to_fused_scores",
    side_effect=lambda _dossier, scores, **kwargs: scores,
)
@patch("ai.agents.inspection_location_agent.resolve_master_sheet_line_scope")
@patch("ai.agents.inspection_location_agent.fuse_candidate_scores")
@patch("ai.agents.inspection_location_agent.generate_all_location_candidates")
@patch("ai.agents.inspection_location_agent.build_evidence_dossier")
@patch("ai.agents.inspection_location_agent.placement_strict_enabled", return_value=True)
def test_strict_raises_when_no_sheet_line(
    _strict: object,
    mock_build_dossier: object,
    mock_generate_candidates: object,
    mock_fuse_scores: object,
    mock_resolve: object,
    _vision: object,
    db_session: Session,
) -> None:
    _run, evidence_id, master_drawing_id, region_id = _seed_ready_master_run(db_session)
    mock_build_dossier.return_value = _utility_line_dossier(
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
        region_id=region_id,
    )
    candidate = LocationMatchCandidate(
        method=ResolutionMethod.REFERENCE_LOOKUP,
        confidence=0.92,
        bbox_fractional=(0.10, 0.20, 0.50, 0.40),
        page=1,
        region_id=region_id,
    )
    mock_generate_candidates.return_value = [candidate]
    mock_fuse_scores.return_value = [
        FusedCandidateScore(
            candidate=candidate,
            fused_score=MATCH_SCORE_THRESHOLD + 0.1,
            clue_hits=(),
            conflicts=(),
            rationale="region hit",
        )
    ]
    mock_resolve.side_effect = ValueError("no lines")

    agent = InspectionLocationAgent()
    with pytest.raises(InspectionPlacementError) as exc_info:
        agent.run(db_session, evidence_id=evidence_id, master_drawing_id=master_drawing_id)

    assert exc_info.value.code == INSPECTION_NO_MASTER_SHEET_LINE


@patch(
    "ai.agents.inspection_location_agent.apply_vision_to_fused_scores",
    side_effect=lambda _dossier, scores, **kwargs: scores,
)
@patch("ai.agents.inspection_location_agent.resolve_master_sheet_line_scope")
@patch("ai.agents.inspection_location_agent.fuse_candidate_scores")
@patch("ai.agents.inspection_location_agent.generate_all_location_candidates")
@patch("ai.agents.inspection_location_agent.build_evidence_dossier")
@patch("ai.agents.inspection_location_agent.placement_strict_enabled", return_value=True)
def test_strict_raises_when_no_anchor_intersecting_line(
    _strict: object,
    mock_build_dossier: object,
    mock_generate_candidates: object,
    mock_fuse_scores: object,
    mock_resolve: object,
    _vision: object,
    db_session: Session,
) -> None:
    _run, evidence_id, master_drawing_id, region_id = _seed_ready_master_run(db_session)
    mock_build_dossier.return_value = _utility_line_dossier(
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
        region_id=region_id,
    )
    candidate = LocationMatchCandidate(
        method=ResolutionMethod.REFERENCE_LOOKUP,
        confidence=0.92,
        bbox_fractional=(0.10, 0.20, 0.50, 0.40),
        page=1,
        region_id=region_id,
    )
    mock_generate_candidates.return_value = [candidate]
    mock_fuse_scores.return_value = [
        FusedCandidateScore(
            candidate=candidate,
            fused_score=MATCH_SCORE_THRESHOLD + 0.1,
            clue_hits=(),
            conflicts=(),
            rationale="region hit",
        )
    ]
    mock_resolve.side_effect = ValueError(
        "[INSPECTION_NO_ANCHOR_INTERSECTING_LINE] No digitized SheetLine intersects the anchor."
    )

    agent = InspectionLocationAgent()
    with pytest.raises(InspectionPlacementError) as exc_info:
        agent.run(db_session, evidence_id=evidence_id, master_drawing_id=master_drawing_id)

    assert exc_info.value.code == INSPECTION_NO_ANCHOR_INTERSECTING_LINE
