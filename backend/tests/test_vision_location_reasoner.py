"""Tests for vision location reasoner (PR-G G-1)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from ai.agents.evidence_dossier import (
    EvidenceDossier,
    ExpandedClue,
    MasterDrawingContext,
)
from ai.pipelines.clue_fusion_scorer import ClueHit, FusedCandidateScore
from ai.pipelines.drawing_location_resolver import ResolutionMethod
from ai.pipelines.evidence_kind_classifier import EvidenceKind
from ai.pipelines.location_match_orchestrator import LocationMatchCandidate
from ai.pipelines.scope_geometry import ScopeKind
from ai.pipelines.scope_line_tracer import trace_scope_geometry
from ai.pipelines.vision_location_reasoner import (
    apply_vision_to_fused_scores,
    reason_over_master_crop,
    should_invoke_vision,
)
from models.models import EvidenceRecord


def _minimal_dossier(*, evidence_text: str = "") -> EvidenceDossier:
    evidence = cast(EvidenceRecord, SimpleNamespace(id=1, project_id=2, meta={}))
    return EvidenceDossier(
        evidence_id=357,
        project_id=2,
        master_drawing_id=661,
        evidence=evidence,
        extraction=None,
        clues=(),
        expanded_clues=(
            ExpandedClue(
                original_value="33-Sanitary Sewerage",
                clue_type="trade",
                expanded_values=("SS", "SANITARY SEWER"),
                confidence=0.9,
            ),
        ),
        evidence_text=evidence_text,
        base_text=evidence_text,
        evidence_kind=EvidenceKind.FORM,
        linked_attachments=(),
        auxiliary_drawings=(),
        photo_paths=(),
        survey_points_meta=(),
        master_context=MasterDrawingContext(
            master_drawing_id=661,
            regions=(),
            total_region_count=0,
            untagged_region_count=0,
            scoped_survey_points=(),
            candidate_tiles=(),
            legend_codes_near_candidates=("SS",),
        ),
        investigation_meta={},
    )


def _fused_candidate(
    *,
    region_id: int,
    fused_score: float,
    method: ResolutionMethod = ResolutionMethod.REFERENCE_LOOKUP,
    confidence: float = 0.7,
    clue_hits: tuple[ClueHit, ...] = (),
) -> FusedCandidateScore:
    return FusedCandidateScore(
        candidate=LocationMatchCandidate(
            method=method,
            confidence=confidence,
            bbox_fractional=(0.1 * region_id, 0.2, 0.1 * region_id + 0.05, 0.25),
            page=1,
            region_id=region_id,
        ),
        fused_score=fused_score,
        clue_hits=clue_hits,
        conflicts=(),
        rationale="deterministic",
    )


def test_should_invoke_vision_for_utility_line_dossier() -> None:
    dossier = _minimal_dossier(
        evidence_text="Sanitary sewer lateral run along corridor",
    )
    scores = [_fused_candidate(region_id=10, fused_score=0.9)]

    assert should_invoke_vision(scores, dossier) is True


def test_should_invoke_vision_for_low_top_score() -> None:
    dossier = _minimal_dossier(evidence_text="Field inspection at COLO parking lot")
    scores = [_fused_candidate(region_id=10, fused_score=0.4)]

    assert should_invoke_vision(scores, dossier) is True


@patch("ai.pipelines.vision_location_reasoner._vision_chat_completion")
def test_reason_over_master_crop_trace_line(mock_vision, tmp_path: Path) -> None:
    png_path = tmp_path / "master.png"
    png_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    mock_vision.return_value = """
    {
      "confidence": 0.88,
      "polyline_points": [[0.41, 0.38], [0.43, 0.39], [0.45, 0.40]],
      "highlight_detected": false,
      "rationale": "Sanitary sewer line visible in crop"
    }
    """

    result = reason_over_master_crop(
        master_png_path=png_path,
        dossier_summary="Underground sanitary sewer at COLO",
        candidate_bboxes=[(0.40, 0.35, 0.50, 0.45)],
        task="trace_line",
    )

    assert result.polyline_points is not None
    assert len(result.polyline_points) == 3
    assert result.confidence == 0.88
    assert "Sanitary sewer" in result.rationale
    mock_vision.assert_called_once()


@patch("ai.pipelines.vision_location_reasoner.reason_over_master_crop")
def test_apply_vision_to_fused_scores_boosts_selected_candidate(mock_reason) -> None:
    dossier = _minimal_dossier(evidence_text="Sanitary sewer at COLO")
    scores = [
        _fused_candidate(region_id=20, fused_score=0.72),
        _fused_candidate(region_id=10, fused_score=0.68),
    ]
    mock_reason.return_value = SimpleNamespace(
        best_candidate_index=1,
        confidence=0.9,
        bbox_fractional=None,
        polyline_points=None,
        highlight_detected=False,
        rationale="COLO corridor match",
    )

    updated = apply_vision_to_fused_scores(
        dossier,
        scores,
        master_png_path=Path("/tmp/master.png"),
    )

    assert updated[0].candidate.region_id == 10
    assert updated[0].fused_score > scores[1].fused_score
    assert "vision=COLO corridor match" in updated[0].rationale


def test_apply_vision_skips_strong_coordinate_winner() -> None:
    dossier = _minimal_dossier(evidence_text="Sanitary sewer run")
    coordinate_winner = _fused_candidate(
        region_id=10,
        fused_score=0.95,
        method=ResolutionMethod.COORDINATE_LOOKUP,
        confidence=0.96,
        clue_hits=(
            ClueHit(
                clue_value="coordinate:n=1,e=2",
                dimension="coordinate",
                weight=0.35,
            ),
        ),
    )
    scores = [
        coordinate_winner,
        _fused_candidate(region_id=20, fused_score=0.5),
    ]

    with patch("ai.pipelines.vision_location_reasoner.reason_over_master_crop") as mock_reason:
        updated = apply_vision_to_fused_scores(
            dossier,
            scores,
            master_png_path=Path("/tmp/master.png"),
        )

    assert updated == scores
    mock_reason.assert_not_called()


@patch("ai.pipelines.vision_location_reasoner.reason_over_master_crop")
def test_trace_scope_geometry_uses_vision_when_deterministic_trace_fails(
    mock_reason,
    tmp_path: Path,
) -> None:
    png_path = tmp_path / "master.png"
    png_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    mock_reason.return_value = SimpleNamespace(
        best_candidate_index=None,
        confidence=0.82,
        bbox_fractional=None,
        polyline_points=((0.12, 0.22), (0.18, 0.24), (0.24, 0.26)),
        highlight_detected=False,
        rationale="Traced SS line",
    )

    dossier = _minimal_dossier(evidence_text="Sanitary sewer lateral run")
    scope = trace_scope_geometry(
        dossier,
        anchor_bbox=(0.10, 0.20, 0.30, 0.40),
        scope_kind=ScopeKind.UTILITY_LINE,
        page=1,
        master_png_path=png_path,
    )

    assert scope.type == "polyline"
    assert scope.points is not None
    assert len(scope.points) == 3
    assert scope.meta is not None
    assert scope.meta.get("source") == "vision_trace"
    mock_reason.assert_called_once()
