"""Tests for inspection location agent (PR-H H-1)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from ai.agents.evidence_dossier import (
    EvidenceDossier,
    ExpandedClue,
    MasterDrawingContext,
)
from ai.agents.inspection_location_agent import InspectionLocationAgent
from ai.pipelines.candidate_tile_selector import CandidateTile
from ai.pipelines.clue_fusion_scorer import FusedCandidateScore
from ai.pipelines.document_text_extraction import BoundingBox
from ai.pipelines.drawing_location_resolver import MasterRegion, ResolutionMethod
from ai.pipelines.evidence_kind_classifier import EvidenceKind
from ai.pipelines.location_match_orchestrator import LocationMatchCandidate
from ai.pipelines.scope_geometry import ScopeKind
from models.drawing_match_candidate import DrawingMatchCandidate
from models.drawing_overlay import DrawingOverlay
from models.inspection_run import InspectionRun
from models.models import Company, Drawing, EvidenceRecord, Project
from services.inspection_match_persistence import MATCH_SCORE_THRESHOLD
from services.storage import StorageService


def _unique() -> str:
    return uuid.uuid4().hex[:12]


def _bbox(x: float, y: float, w: float, h: float) -> BoundingBox:
    return BoundingBox(x=x, y=y, width=w, height=h, page_width=1.0, page_height=1.0)


def _utility_line_dossier(
    *,
    evidence_id: int,
    master_drawing_id: int,
    region_id: int,
) -> EvidenceDossier:
    evidence = cast(
        EvidenceRecord,
        SimpleNamespace(id=evidence_id, project_id=2, meta={}),
    )
    return EvidenceDossier(
        evidence_id=evidence_id,
        project_id=2,
        master_drawing_id=master_drawing_id,
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
        evidence_text="Sanitary sewer lateral run in corridor",
        base_text="Sanitary sewer lateral run in corridor",
        evidence_kind=EvidenceKind.FORM,
        linked_attachments=(),
        auxiliary_drawings=(),
        photo_paths=(),
        survey_points_meta=(),
        master_context=MasterDrawingContext(
            master_drawing_id=master_drawing_id,
            regions=(
                MasterRegion(
                    region_id=str(region_id),
                    master_drawing_id=str(master_drawing_id),
                    inspection_types=("Underground Sanitary Sewer #1",),
                    location_labels=("COLO",),
                    bbox_on_master=_bbox(0.1, 0.2, 0.08, 0.09),
                ),
            ),
            total_region_count=1,
            untagged_region_count=0,
            scoped_survey_points=(),
            candidate_tiles=(
                CandidateTile(
                    drawing_id=str(master_drawing_id),
                    page=1,
                    text="SS-3",
                    confidence=0.9,
                    bbox_normalized=(0.14, 0.24, 0.18, 0.26),
                    text_element_id=1,
                ),
                CandidateTile(
                    drawing_id=str(master_drawing_id),
                    page=1,
                    text="SS-4",
                    confidence=0.9,
                    bbox_normalized=(0.34, 0.28, 0.38, 0.30),
                    text_element_id=2,
                ),
            ),
            legend_codes_near_candidates=("SS",),
        ),
        investigation_meta={},
    )


def _seed_ready_master_run(db: Session) -> tuple[InspectionRun, int, int, int]:
    company = Company(name=f"Co {_unique()}", procore_company_id=f"pc-{_unique()}")
    db.add(company)
    db.flush()

    project = Project(
        company_id=company.id,
        procore_project_id=f"pp-{_unique()}",
        name="Test Project",
    )
    db.add(project)
    db.flush()

    drawing = Drawing(
        project_id=project.id,
        source="upload",
        name="Master",
        storage_key=f"drawings/{_unique()}.pdf",
        index_status="ready",
    )
    db.add(drawing)
    db.flush()

    storage = StorageService(db)
    region = storage.create_drawing_region(
        cast(int, drawing.id),
        label="Colo Parking",
        geometry={"type": "rect", "x": 0.1, "y": 0.2, "width": 0.08, "height": 0.09},
        location_tags=["COLO"],
        inspection_type_tags=["Underground Sanitary Sewer #1"],
    )

    evidence = EvidenceRecord(
        project_id=project.id,
        type="inspection_doc",
        title="Inspection PDF",
        storage_key=f"evidence/{_unique()}.pdf",
    )
    db.add(evidence)
    db.flush()

    run = InspectionRun(
        project_id=project.id,
        master_drawing_id=drawing.id,
        evidence_id=evidence.id,
        status="complete",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    return run, cast(int, evidence.id), cast(int, drawing.id), cast(int, region.id)


def test_agent_defers_when_master_index_not_ready(db_session: Session) -> None:
    run, evidence_id, master_drawing_id, _region_id = _seed_ready_master_run(db_session)
    drawing = db_session.get(Drawing, master_drawing_id)
    assert drawing is not None
    setattr(drawing, "index_status", "pending")
    db_session.commit()

    agent = InspectionLocationAgent()
    result = agent.run(
        db_session,
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
    )

    assert result.status == "index_pending"
    overlay = (
        db_session.query(DrawingOverlay)
        .filter(DrawingOverlay.inspection_run_id == run.id)
        .one()
    )
    overlay_meta = cast(dict, overlay.meta)
    assert overlay_meta["match_status"] == "index_pending"


@patch("ai.agents.inspection_location_agent.should_invoke_vision", return_value=False)
@patch("ai.agents.inspection_location_agent.fuse_candidate_scores")
@patch("ai.agents.inspection_location_agent.generate_all_location_candidates")
@patch("ai.agents.inspection_location_agent.build_evidence_dossier")
def test_agent_end_to_end_polyline_for_utility_line(
    mock_build_dossier,
    mock_generate_candidates,
    mock_fuse_scores,
    _mock_should_vision,
    db_session: Session,
) -> None:
    run, evidence_id, master_drawing_id, region_id = _seed_ready_master_run(db_session)
    dossier = _utility_line_dossier(
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
        region_id=region_id,
    )
    mock_build_dossier.return_value = dossier

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
            rationale="COLO + sanitary sewer region",
        )
    ]

    agent = InspectionLocationAgent()
    result = agent.run(
        db_session,
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
    )

    assert result.status == "matched"
    assert result.scope is not None
    assert result.scope.type == "polyline"
    assert result.scope.scope_kind == ScopeKind.UTILITY_LINE
    assert result.scope.points is not None
    assert len(result.scope.points) >= 2

    overlay = (
        db_session.query(DrawingOverlay)
        .filter(DrawingOverlay.inspection_run_id == run.id)
        .one()
    )
    geometry = cast(dict, overlay.geometry)
    assert geometry["type"] == "polyline"
    assert geometry.get("scope_kind") == ScopeKind.UTILITY_LINE.value
    assert len(cast(list, geometry.get("points"))) >= 2

    overlay_meta = cast(dict, overlay.meta)
    assert overlay_meta["match_status"] == "matched"
    assert overlay_meta["agent_rationale"]
    assert overlay_meta["agent_candidates"]

    candidates = (
        db_session.query(DrawingMatchCandidate)
        .filter(DrawingMatchCandidate.inspection_id == str(evidence_id))
        .all()
    )
    assert len(candidates) == 1
    assert cast(str, candidates[0].source) == "inspection_location_agent"
    candidate_meta = cast(dict, candidates[0].meta_json)
    assert candidate_meta["rationale"] == "COLO + sanitary sewer region"
    assert candidate_meta["fused_score"] == pytest.approx(MATCH_SCORE_THRESHOLD + 0.1)
    assert candidate_meta["conflicts"] == []
    assert candidate_meta["clue_hits"] == []


@patch("ai.agents.inspection_location_agent.should_invoke_vision", return_value=False)
@patch("ai.agents.inspection_location_agent.trace_scope_geometry")
@patch("ai.agents.inspection_location_agent.fuse_candidate_scores")
@patch("ai.agents.inspection_location_agent.generate_all_location_candidates")
@patch("ai.agents.inspection_location_agent.build_evidence_dossier")
def test_agent_passes_aux_source_drawing_id_to_scope_tracer(
    mock_build_dossier,
    mock_generate_candidates,
    mock_fuse_scores,
    mock_trace_scope,
    _mock_should_vision,
    db_session: Session,
) -> None:
    from ai.pipelines.scope_geometry import ScopeGeometry

    run, evidence_id, master_drawing_id, region_id = _seed_ready_master_run(db_session)
    dossier = _utility_line_dossier(
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
        region_id=region_id,
    )
    mock_build_dossier.return_value = dossier

    candidate = LocationMatchCandidate(
        method=ResolutionMethod.COORDINATE_LOOKUP,
        confidence=0.98,
        bbox_fractional=(0.16, 0.20, 0.18, 0.22),
        page=1,
        source_drawing_id=1084,
        notes="aux_coords_unprojected",
        contradicting_signals=("aux_coords_unprojected",),
    )
    mock_generate_candidates.return_value = [candidate]
    mock_fuse_scores.return_value = [
        FusedCandidateScore(
            candidate=candidate,
            fused_score=MATCH_SCORE_THRESHOLD + 0.1,
            clue_hits=(),
            conflicts=(),
            rationale="coordinate_lookup@0.98",
        )
    ]
    mock_trace_scope.return_value = ScopeGeometry(
        page=1,
        type="polyline",
        points=((0.10, 0.20), (0.29, 0.27)),
        scope_kind=ScopeKind.UTILITY_LINE,
        meta={"source": "aux_station_labels", "source_drawing_id": 1084},
    )

    agent = InspectionLocationAgent()
    agent.run(
        db_session,
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
    )

    mock_trace_scope.assert_called_once()
    assert mock_trace_scope.call_args.kwargs["source_drawing_id"] == 1084


@patch("ai.agents.inspection_location_agent.should_invoke_vision", return_value=False)
@patch("ai.agents.inspection_location_agent.trace_scope_geometry")
@patch("ai.agents.inspection_location_agent.fuse_candidate_scores")
@patch("ai.agents.inspection_location_agent.generate_all_location_candidates")
@patch("ai.agents.inspection_location_agent.build_evidence_dossier")
def test_agent_prefers_registration_aux_for_scope_tracing(
    mock_build_dossier,
    mock_generate_candidates,
    mock_fuse_scores,
    mock_trace_scope,
    _mock_should_vision,
    db_session: Session,
) -> None:
    from ai.pipelines.drawing_location_resolver import RegistrationTransform
    from ai.pipelines.scope_geometry import ScopeGeometry

    run, evidence_id, master_drawing_id, region_id = _seed_ready_master_run(db_session)
    dossier = _utility_line_dossier(
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
        region_id=region_id,
    )
    registered_aux_id = 1501
    dossier.evidence.meta = {
        "station_from": "10+00",
        "station_to": "10+90.95",
        "station_range_source_drawing_id": registered_aux_id,
        "registration_transform": {
            "scale_x": 2.0,
            "scale_y": 2.0,
            "translate_x": 0.30,
            "translate_y": 0.07,
            "rotation_degrees": 0.0,
            "registration_aux_drawing_id": registered_aux_id,
        },
    }
    mock_build_dossier.return_value = dossier

    wrong_aux_id = 1549
    candidate = LocationMatchCandidate(
        method=ResolutionMethod.REFERENCE_LOOKUP,
        confidence=0.94,
        bbox_fractional=(0.63, 0.18, 0.66, 0.20),
        page=1,
        source_drawing_id=wrong_aux_id,
    )
    mock_generate_candidates.return_value = [candidate]
    mock_fuse_scores.return_value = [
        FusedCandidateScore(
            candidate=candidate,
            fused_score=0.2,
            clue_hits=(),
            conflicts=(),
            rationale="reference_lookup@0.94",
        )
    ]
    mock_trace_scope.return_value = ScopeGeometry(
        page=1,
        type="polyline",
        points=((0.10, 0.20), (0.29, 0.27)),
        scope_kind=ScopeKind.UTILITY_LINE,
        meta={
            "source": "aux_plan_station_labels",
            "source_drawing_id": registered_aux_id,
        },
    )

    agent = InspectionLocationAgent()
    result = agent.run(
        db_session,
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
    )

    mock_trace_scope.assert_called_once()
    assert mock_trace_scope.call_args.kwargs["source_drawing_id"] == registered_aux_id
    assert result.scope is not None
    assert result.scope.points is not None
    assert result.scope.points[0][0] == pytest.approx(0.50, abs=0.02)


def _polyline_path_length(points: tuple[tuple[float, float], ...]) -> float:
    total = 0.0
    for index in range(1, len(points)):
        dx = points[index][0] - points[index - 1][0]
        dy = points[index][1] - points[index - 1][1]
        total += (dx * dx + dy * dy) ** 0.5
    return total


@patch("ai.agents.inspection_location_agent.should_invoke_vision", return_value=False)
@patch("ai.agents.inspection_location_agent.trace_scope_geometry")
@patch("ai.agents.inspection_location_agent.fuse_candidate_scores")
@patch("ai.agents.inspection_location_agent.generate_all_location_candidates")
@patch("ai.agents.inspection_location_agent.build_evidence_dossier")
def test_agent_projects_aux_polyline_to_master_with_registration_transform(
    mock_build_dossier,
    mock_generate_candidates,
    mock_fuse_scores,
    mock_trace_scope,
    _mock_should_vision,
    db_session: Session,
) -> None:
    from ai.pipelines.drawing_location_resolver import RegistrationTransform
    from ai.pipelines.scope_geometry import ScopeGeometry

    run, evidence_id, master_drawing_id, region_id = _seed_ready_master_run(db_session)
    dossier = _utility_line_dossier(
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
        region_id=region_id,
    )
    transform = RegistrationTransform(
        scale_x=2.0,
        scale_y=2.0,
        translate_x=0.30,
        translate_y=0.07,
        rotation_degrees=0.0,
    )
    dossier.evidence.meta = {
        "registration_transform": {
            "scale_x": transform.scale_x,
            "scale_y": transform.scale_y,
            "translate_x": transform.translate_x,
            "translate_y": transform.translate_y,
            "rotation_degrees": transform.rotation_degrees,
        }
    }
    mock_build_dossier.return_value = dossier

    aux_drawing_id = 1084
    candidate = LocationMatchCandidate(
        method=ResolutionMethod.COORDINATE_LOOKUP,
        confidence=0.98,
        bbox_fractional=(0.518, 0.472, 0.556, 0.480),
        page=1,
        source_drawing_id=aux_drawing_id,
    )
    mock_generate_candidates.return_value = [candidate]
    mock_fuse_scores.return_value = [
        FusedCandidateScore(
            candidate=candidate,
            fused_score=MATCH_SCORE_THRESHOLD + 0.1,
            clue_hits=(),
            conflicts=(),
            rationale="coordinate_lookup@0.98",
        )
    ]
    aux_polyline = (
        (0.10, 0.20),
        (0.20, 0.22),
        (0.29, 0.27),
        (0.30, 0.27),
    )
    mock_trace_scope.return_value = ScopeGeometry(
        page=1,
        type="polyline",
        points=aux_polyline,
        scope_kind=ScopeKind.UTILITY_LINE,
        meta={"source": "aux_survey_chain", "source_drawing_id": aux_drawing_id},
    )

    agent = InspectionLocationAgent()
    result = agent.run(
        db_session,
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
    )

    assert result.status == "matched"
    assert result.scope is not None
    assert result.scope.type == "polyline"
    assert result.scope.points is not None
    assert result.scope.points[0][0] == pytest.approx(0.50, abs=0.02)
    assert result.scope.points[0][1] == pytest.approx(0.47, abs=0.02)
    assert _polyline_path_length(result.scope.points) > 0.05
    assert result.scope.meta is not None
    assert result.scope.meta.get("projected_from_drawing_id") == aux_drawing_id

    overlay = (
        db_session.query(DrawingOverlay)
        .filter(DrawingOverlay.inspection_run_id == run.id)
        .one()
    )
    geometry = cast(dict, overlay.geometry)
    assert geometry["type"] == "polyline"
    points = cast(list[list[float]], geometry["points"])
    assert points[0][0] == pytest.approx(0.50, abs=0.02)
    assert points[0][1] == pytest.approx(0.47, abs=0.02)
    assert _polyline_path_length(tuple(tuple(p) for p in points)) > 0.05


@patch("ai.agents.inspection_location_agent.should_invoke_vision", return_value=False)
@patch("ai.agents.inspection_location_agent.trace_scope_geometry")
@patch("ai.agents.inspection_location_agent.fuse_candidate_scores")
@patch("ai.agents.inspection_location_agent.generate_all_location_candidates")
@patch("ai.agents.inspection_location_agent.build_evidence_dossier")
def test_agent_defers_aux_polyline_when_registration_transform_missing(
    mock_build_dossier,
    mock_generate_candidates,
    mock_fuse_scores,
    mock_trace_scope,
    _mock_should_vision,
    db_session: Session,
) -> None:
    from ai.pipelines.scope_geometry import ScopeGeometry

    run, evidence_id, master_drawing_id, region_id = _seed_ready_master_run(db_session)
    dossier = _utility_line_dossier(
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
        region_id=region_id,
    )
    mock_build_dossier.return_value = dossier

    aux_drawing_id = 1084
    candidate = LocationMatchCandidate(
        method=ResolutionMethod.COORDINATE_LOOKUP,
        confidence=0.98,
        bbox_fractional=(0.16, 0.20, 0.18, 0.22),
        page=1,
        source_drawing_id=aux_drawing_id,
        notes="aux_coords_unprojected",
        contradicting_signals=("aux_coords_unprojected",),
    )
    mock_generate_candidates.return_value = [candidate]
    mock_fuse_scores.return_value = [
        FusedCandidateScore(
            candidate=candidate,
            fused_score=MATCH_SCORE_THRESHOLD + 0.1,
            clue_hits=(),
            conflicts=(),
            rationale="coordinate_lookup@0.98",
        )
    ]
    mock_trace_scope.return_value = ScopeGeometry(
        page=1,
        type="polyline",
        points=((0.10, 0.20), (0.29, 0.27)),
        scope_kind=ScopeKind.UTILITY_LINE,
        meta={"source": "aux_station_labels", "source_drawing_id": aux_drawing_id},
    )

    agent = InspectionLocationAgent()
    result = agent.run(
        db_session,
        evidence_id=evidence_id,
        master_drawing_id=master_drawing_id,
    )

    assert result.status == "needs_review"
    assert result.scope is None
    assert "aux_coords_unprojected" in result.rationale

    overlay = (
        db_session.query(DrawingOverlay)
        .filter(DrawingOverlay.inspection_run_id == run.id)
        .one()
    )
    geometry = cast(dict, overlay.geometry)
    assert geometry["type"] != "polyline"
