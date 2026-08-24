"""Autonomous inspection location agent orchestrator."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

from sqlalchemy.orm import Session

from ai.agents.evidence_dossier import EvidenceDossier, build_evidence_dossier
from ai.pipelines.clue_fusion_scorer import (
    FusedCandidateScore,
    fuse_candidate_scores,
    select_fused_winner,
)
from ai.pipelines.drawing_location_resolver import ResolutionMethod
from ai.pipelines.location_match_orchestrator import generate_all_location_candidates
from ai.pipelines.scope_geometry import ScopeGeometry, ScopeKind, bbox_to_scope_rect, clamp_fractional_bbox, infer_scope_kind
from ai.pipelines.scope_line_tracer import trace_scope_geometry
from ai.pipelines.vision_location_reasoner import (
    apply_vision_to_fused_scores,
    should_invoke_vision,
)
from models.models import DrawingRendition
from services.file_storage import resolve_stored_file_path
from services.inspection_match_persistence import (
    MATCH_SCORE_THRESHOLD,
    AgentMatchResult,
    MatchStatus,
    persist_agent_match_result,
)
from services.master_drawing_index_readiness import get_master_drawing_index_readiness

logger = logging.getLogger(__name__)

MAX_INVESTIGATION_STEPS = 8
_MAJOR_CONFLICT_THRESHOLD = 2


class InspectionLocationAgent:
    def run(
        self,
        session: Session,
        *,
        evidence_id: int,
        master_drawing_id: int,
        page: int = 1,
        inspection_run_id: int | None = None,
    ) -> AgentMatchResult:
        """Investigate evidence and resolve a scoped overlay on the master drawing."""
        readiness = get_master_drawing_index_readiness(session, master_drawing_id)
        if not readiness.is_ready_for_matching:
            result = AgentMatchResult(
                status="index_pending",
                scope=None,
                region_id=None,
                page=page,
                rationale=(
                    f"Master drawing index not ready "
                    f"(status={readiness.index_status}, regions={readiness.region_count})."
                ),
                fused_score=None,
            )
            persist_agent_match_result(
                session,
                evidence_id=evidence_id,
                master_drawing_id=master_drawing_id,
                result=result,
                ranked_scores=[],
                page=page,
                inspection_run_id=inspection_run_id,
            )
            return result

        dossier = build_evidence_dossier(
            session,
            evidence_id=evidence_id,
            master_drawing_id=master_drawing_id,
            page=page,
            investigate=True,
        )

        if _auxiliary_drawings_need_index(session, dossier):
            result = AgentMatchResult(
                status="index_pending",
                scope=None,
                region_id=None,
                page=page,
                rationale="Linked auxiliary drawings are still indexing.",
                fused_score=None,
            )
            persist_agent_match_result(
                session,
                evidence_id=evidence_id,
                master_drawing_id=master_drawing_id,
                result=result,
                ranked_scores=[],
                page=page,
                inspection_run_id=inspection_run_id,
            )
            return result

        candidates = generate_all_location_candidates(
            session,
            evidence_id=evidence_id,
            master_drawing_id=master_drawing_id,
            page=page,
        )
        if not candidates:
            result = AgentMatchResult(
                status="no_match",
                scope=None,
                region_id=None,
                page=page,
                rationale="No location candidates generated.",
                fused_score=None,
            )
            persist_agent_match_result(
                session,
                evidence_id=evidence_id,
                master_drawing_id=master_drawing_id,
                result=result,
                ranked_scores=[],
                page=page,
                inspection_run_id=inspection_run_id,
            )
            return result

        ranked_scores = fuse_candidate_scores(dossier, candidates)
        master_png_path = _master_rendition_path(session, master_drawing_id, page)
        if should_invoke_vision(ranked_scores, dossier) and master_png_path is not None:
            ranked_scores = apply_vision_to_fused_scores(
                dossier,
                ranked_scores,
                master_png_path=master_png_path,
            )

        winner = select_fused_winner(ranked_scores)
        if winner is None and _has_unprojected_aux_coordinate_match(candidates):
            result = AgentMatchResult(
                status="needs_review",
                scope=None,
                region_id=None,
                page=page,
                rationale=(
                    "aux_coords_unprojected: survey coordinates matched on a linked "
                    "drawing but could not be projected onto the master sheet."
                ),
                fused_score=None,
            )
            persist_agent_match_result(
                session,
                evidence_id=evidence_id,
                master_drawing_id=master_drawing_id,
                result=result,
                ranked_scores=ranked_scores,
                page=page,
                inspection_run_id=inspection_run_id,
            )
            return result

        if winner is None:
            result = AgentMatchResult(
                status="no_match",
                scope=None,
                region_id=None,
                page=page,
                rationale="No actionable fused candidate.",
                fused_score=None,
            )
            persist_agent_match_result(
                session,
                evidence_id=evidence_id,
                master_drawing_id=master_drawing_id,
                result=result,
                ranked_scores=ranked_scores,
                page=page,
                inspection_run_id=inspection_run_id,
            )
            return result

        scope_kind = infer_scope_kind(dossier)
        anchor_bbox = winner.candidate.bbox_fractional
        scope: ScopeGeometry | None = None
        if anchor_bbox is not None:
            safe_anchor = clamp_fractional_bbox(anchor_bbox)
            try:
                scope = trace_scope_geometry(
                    dossier,
                    anchor_bbox=safe_anchor,
                    scope_kind=scope_kind,
                    page=page,
                    session=session,
                    master_png_path=master_png_path,
                )
            except ValueError:
                scope = None
            if scope is None:
                scope = bbox_to_scope_rect(
                    safe_anchor,
                    page=page,
                    scope_kind=scope_kind,
                )

        status = _decide_match_status(
            winner,
            scope=scope,
            scope_kind=scope_kind,
        )
        rationale = winner.rationale
        if scope is not None and scope.meta:
            source = scope.meta.get("source")
            if source:
                rationale = f"{rationale} | scope={source}"

        result = AgentMatchResult(
            status=status,
            scope=scope,
            region_id=winner.candidate.region_id,
            page=winner.candidate.page,
            rationale=rationale,
            fused_score=winner.fused_score,
        )
        persist_agent_match_result(
            session,
            evidence_id=evidence_id,
            master_drawing_id=master_drawing_id,
            result=result,
            ranked_scores=ranked_scores,
            page=page,
            inspection_run_id=inspection_run_id,
        )
        return result


def _decide_match_status(
    winner: FusedCandidateScore,
    *,
    scope: ScopeGeometry | None,
    scope_kind: ScopeKind,
) -> MatchStatus:
    del scope_kind  # reserved for future scope-specific rules

    if winner.fused_score <= 0:
        return "no_match"

    major_conflicts = len(winner.conflicts) >= _MAJOR_CONFLICT_THRESHOLD
    ambiguous_line = bool(scope and scope.meta and scope.meta.get("ambiguous"))
    borderline = winner.fused_score < MATCH_SCORE_THRESHOLD

    if major_conflicts and winner.fused_score < MATCH_SCORE_THRESHOLD:
        return "no_match"

    if (
        winner.fused_score >= MATCH_SCORE_THRESHOLD
        and not major_conflicts
        and not ambiguous_line
    ):
        return "matched"

    if borderline or ambiguous_line or major_conflicts:
        return "needs_review"

    return "needs_review"


def _has_unprojected_aux_coordinate_match(candidates: list[object]) -> bool:
    for candidate in candidates:
        notes = str(getattr(candidate, "notes", "") or "")
        method = getattr(candidate, "method", None)
        if method == ResolutionMethod.COORDINATE_LOOKUP and "aux_coords_unprojected" in notes:
            return True
    return False


def _auxiliary_drawings_need_index(session: Session, dossier: EvidenceDossier) -> bool:
    if dossier.investigation_meta.get("auxiliary_index_pending"):
        return True
    for drawing in dossier.auxiliary_drawings:
        readiness = get_master_drawing_index_readiness(session, cast(int, drawing.id))
        if not readiness.is_ready_for_matching:
            return True
    return False


def _master_rendition_path(
    session: Session,
    master_drawing_id: int,
    page: int,
) -> Path | None:
    rendition = (
        session.query(DrawingRendition)
        .filter(
            DrawingRendition.drawing_id == master_drawing_id,
            DrawingRendition.page_number == page,
        )
        .order_by(DrawingRendition.id.desc())
        .first()
    )
    if rendition is None:
        return None

    storage_key = cast(str | None, rendition.image_storage_key)
    if not storage_key:
        return None

    resolved = resolve_stored_file_path(storage_key)
    if resolved is None or not resolved.is_file():
        return None
    return resolved
