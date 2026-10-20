"""Autonomous inspection location agent orchestrator."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from sqlalchemy.orm import Session

from ai.agents.evidence_dossier import EvidenceDossier, build_evidence_dossier
from ai.pipelines.clue_fusion_scorer import (
    FusedCandidateScore,
    fuse_candidate_scores,
    select_fused_winner,
    _is_unprojected_aux_coordinate,
)
from ai.pipelines.drawing_location_resolver import ResolutionMethod
from ai.pipelines.drawing_location_resolver import RegistrationTransform
from ai.pipelines.location_match_orchestrator import (
    LocationMatchCandidate,
    generate_all_location_candidates,
)
from ai.pipelines.scope_geometry import (
    ScopeGeometry,
    ScopeKind,
    clamp_fractional_bbox,
)
from ai.pipelines.scope_line_tracer import resolve_master_sheet_line_scope
from ai.pipelines.vision_location_reasoner import apply_vision_to_fused_scores
from models.models import DrawingRendition
from services.file_storage import resolve_stored_file_path
from services.inspection_match_persistence import (
    AgentMatchResult,
    persist_agent_match_result,
)
from services.inspection_placement_errors import (
    INSPECTION_INVALID_SCOPE,
    INSPECTION_NO_ANCHOR_BBOX,
    INSPECTION_NO_CANDIDATES,
    INSPECTION_NO_FUSED_WINNER,
    InspectionPlacementError,
    placement_strict_enabled,
)
from services.master_drawing_index_readiness import get_master_drawing_index_readiness

logger = logging.getLogger(__name__)

MAX_INVESTIGATION_STEPS = 8

class InspectionLocationAgent:
    def run(
        self,
        session: Session,
        *,
        evidence_id: int,
        master_drawing_id: int,
        page: int = 1,
        inspection_run_id: int | None = None,
        force_investigate: bool = False,
        investigate: bool = True,
    ) -> AgentMatchResult:
        """Investigate evidence and resolve a scoped overlay on the master drawing."""
        readiness = get_master_drawing_index_readiness(session, master_drawing_id)
        if not readiness.is_ready_for_matching:
            result = AgentMatchResult(
                status="index_pending",
                scope=None,
                region_id=None,
                page=page,
                rationale=readiness.not_ready_message(),
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
            investigate=investigate,
            force_investigate=force_investigate,
        )

        from services.inspection_run_progress import get_inspection_progress

        progress = get_inspection_progress()

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

        if progress is not None:
            progress.set_phase("matching")

        candidates = generate_all_location_candidates(
            session,
            evidence_id=evidence_id,
            master_drawing_id=master_drawing_id,
            page=page,
        )
        strict = placement_strict_enabled()
        if strict and not candidates:
            raise InspectionPlacementError(
                INSPECTION_NO_CANDIDATES,
                "No location candidates were generated for this evidence on the master drawing.",
            )

        ranked_scores = fuse_candidate_scores(dossier, candidates) if candidates else []
        master_png_path = _master_rendition_path(session, master_drawing_id, page)
        if master_png_path is not None and ranked_scores:
            ranked_scores = apply_vision_to_fused_scores(
                dossier,
                ranked_scores,
                master_png_path=master_png_path,
            )

        winner, placement_note = _pick_placement_winner(
            ranked_scores,
            master_drawing_id=master_drawing_id,
            session=session,
            page=page,
            strict=strict,
        )

        anchor_bbox = _master_scope_anchor_bbox(
            winner,
            ranked_scores,
            master_drawing_id=master_drawing_id,
            session=session,
            page=page,
            strict=strict,
        )
        if anchor_bbox is None:
            if strict:
                raise InspectionPlacementError(
                    INSPECTION_NO_ANCHOR_BBOX,
                    "Could not derive a master-sheet anchor bbox from fused location candidates.",
                )
            anchor_bbox = (0.35, 0.25, 0.65, 0.55)
        safe_anchor = clamp_fractional_bbox(anchor_bbox)

        if progress is not None:
            progress.set_phase("tracing")

        try:
            scope = _resolve_master_line_placement_scope(
                session,
                dossier=dossier,
                master_drawing_id=master_drawing_id,
                page=page,
                anchor_bbox=safe_anchor,
                strict=strict,
            )
        except ValueError as exc:
            if strict:
                from services.inspection_placement_errors import (
                    inspection_placement_error_from_value_error,
                )

                raise inspection_placement_error_from_value_error(exc) from exc
            logger.warning(
                "inspection_master_sheet_line_missing",
                extra={
                    "evidence_id": evidence_id,
                    "master_drawing_id": master_drawing_id,
                    "error": str(exc),
                },
            )
            result = AgentMatchResult(
                status="index_pending",
                scope=None,
                region_id=winner.candidate.region_id,
                page=page,
                rationale=str(exc),
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

        if strict and (scope.meta or {}).get("source") != "sheet_line":
            raise InspectionPlacementError(
                INSPECTION_INVALID_SCOPE,
                f"Placement scope must be master sheet_line, got {scope.meta!r}.",
            )

        rationale = winner.rationale
        if placement_note:
            rationale = f"{rationale} | {placement_note}"
        if scope.meta:
            source = scope.meta.get("source")
            if source:
                rationale = f"{rationale} | scope={source}"

        result = AgentMatchResult(
            status="matched",
            scope=scope,
            region_id=winner.candidate.region_id,
            page=winner.candidate.page,
            rationale=rationale,
            fused_score=winner.fused_score,
        )
        if progress is not None:
            progress.set_phase("saving_overlay")
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


def _resolve_master_line_placement_scope(
    session: Session,
    *,
    dossier: EvidenceDossier,
    master_drawing_id: int,
    page: int,
    anchor_bbox: tuple[float, float, float, float],
    strict: bool,
) -> ScopeGeometry:
    """Always place on a master plan SheetLine (never aux polylines or anchor rects)."""
    return resolve_master_sheet_line_scope(
        session,
        dossier=dossier,
        master_drawing_id=master_drawing_id,
        page=page,
        anchor_bbox=anchor_bbox,
        strict=strict,
    )


def _pick_placement_winner(
    ranked_scores: Sequence[FusedCandidateScore],
    *,
    master_drawing_id: int,
    session: Session,
    page: int,
    strict: bool,
) -> tuple[FusedCandidateScore, str | None]:
    """Choose a location anchor; inspection always receives a master SheetLine overlay."""
    winner = select_fused_winner(list(ranked_scores))
    if strict:
        if winner is None:
            raise InspectionPlacementError(
                INSPECTION_NO_FUSED_WINNER,
                "No fused location candidate met strict placement requirements "
                "(positive fused score and valid master bbox).",
            )
        return winner, None

    if winner is None:
        winner = _fallback_fused_score_for_master_placement(
            ranked_scores,
            master_drawing_id=master_drawing_id,
        )
    if winner is None and ranked_scores:
        with_bbox = [
            fused
            for fused in ranked_scores
            if fused.candidate.bbox_fractional is not None
        ]
        if with_bbox:
            winner = max(
                with_bbox,
                key=lambda item: (item.fused_score, item.candidate.confidence),
            )
            return winner, "placement_fallback=best_bbox_candidate"

    if winner is not None:
        return winner, None

    corridor = clamp_fractional_bbox((0.12, 0.22, 0.92, 0.78))
    from ai.pipelines.master_utility_anchor import utility_corridor_anchor_for_drawing

    legend_corridor = utility_corridor_anchor_for_drawing(
        session,
        master_drawing_id,
        page=page,
    )
    anchor = legend_corridor or corridor
    synthetic = LocationMatchCandidate(
        method=ResolutionMethod.REFERENCE_LOOKUP,
        confidence=0.05,
        bbox_fractional=anchor,
        page=page,
        source_drawing_id=master_drawing_id,
        notes="synthetic_plan_corridor_anchor",
    )
    return (
        FusedCandidateScore(
            candidate=synthetic,
            fused_score=0.01,
            clue_hits=(),
            conflicts=(),
            rationale="placement_fallback=plan_corridor",
        ),
        "placement_fallback=plan_corridor",
    )


def _resolve_scope_source_drawing_id(
    dossier: EvidenceDossier,
    winner_source_drawing_id: int | None,
    *,
    master_drawing_id: int,
    registration_transform: RegistrationTransform | None,
) -> int | None:
    """Prefer the aux sheet used for station range when building utility scope."""
    meta = cast(dict[str, Any] | None, getattr(dossier.evidence, "meta", None))
    station_range_aux_id: int | None = None
    if isinstance(meta, dict):
        raw_station_source = meta.get("station_range_source_drawing_id")
        if raw_station_source is not None:
            try:
                station_range_aux_id = int(raw_station_source)
            except (TypeError, ValueError):
                station_range_aux_id = None

    if registration_transform is not None:
        if isinstance(meta, dict):
            reg_aux_id = _registration_aux_drawing_id_from_meta(meta)
            if reg_aux_id is not None:
                return reg_aux_id
        if station_range_aux_id is not None and station_range_aux_id != int(
            master_drawing_id
        ):
            return station_range_aux_id
        return winner_source_drawing_id

    if (
        station_range_aux_id is not None
        and station_range_aux_id != int(master_drawing_id)
    ):
        return station_range_aux_id

    if (
        winner_source_drawing_id is not None
        and int(winner_source_drawing_id) == int(master_drawing_id)
    ):
        return int(master_drawing_id)
    return None


def _fallback_fused_score_for_master_placement(
    ranked_scores: Sequence[FusedCandidateScore],
    *,
    master_drawing_id: int,
) -> FusedCandidateScore | None:
    """Pick a master-local candidate when coordinate fusion penalizes aux-only winners."""
    candidates = [
        fused
        for fused in ranked_scores
        if fused.fused_score > 0
        and fused.candidate.bbox_fractional is not None
        and not _is_unprojected_aux_coordinate(fused.candidate, master_drawing_id)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.fused_score, item.candidate.confidence))


def _master_scope_anchor_bbox(
    winner: FusedCandidateScore,
    ranked_scores: Sequence[FusedCandidateScore],
    *,
    master_drawing_id: int,
    session: Session | None = None,
    page: int = 1,
    strict: bool = False,
) -> tuple[float, float, float, float] | None:
    """Avoid anchoring master scope traces on unprojected auxiliary coordinate boxes."""
    candidate = winner.candidate
    bbox = candidate.bbox_fractional
    if bbox is None:
        return None
    if not _is_unprojected_aux_coordinate(candidate, master_drawing_id):
        return bbox

    for fused in ranked_scores:
        alt = fused.candidate
        if alt.bbox_fractional is None:
            continue
        if _is_unprojected_aux_coordinate(alt, master_drawing_id):
            continue
        if alt.source_drawing_id is None or int(alt.source_drawing_id) == int(
            master_drawing_id
        ):
            return alt.bbox_fractional

    corridor = _utility_corridor_anchor_bbox(ranked_scores, master_drawing_id=master_drawing_id)
    if corridor is not None:
        return corridor

    if session is not None:
        from ai.pipelines.master_utility_anchor import utility_corridor_anchor_for_drawing

        legend_corridor = utility_corridor_anchor_for_drawing(
            session,
            master_drawing_id,
            page=page,
        )
        if legend_corridor is not None:
            return legend_corridor

    if strict:
        return None

    # Last resort (non-strict): search the plan-view band on the master sheet (not the aux pin).
    return clamp_fractional_bbox((0.12, 0.22, 0.92, 0.78))


def _utility_corridor_anchor_bbox(
    ranked_scores: Sequence[FusedCandidateScore],
    *,
    master_drawing_id: int,
) -> tuple[float, float, float, float] | None:
    """Expand a search window on the master sheet around legend / clue tile hits."""
    for fused in ranked_scores:
        candidate = fused.candidate
        if candidate.bbox_fractional is None:
            continue
        if candidate.source_drawing_id is not None and int(candidate.source_drawing_id) != int(
            master_drawing_id
        ):
            continue
        x0, y0, x1, y1 = candidate.bbox_fractional
        pad_x = max(0.08, (x1 - x0) * 4.0)
        pad_y = max(0.08, (y1 - y0) * 4.0)
        return clamp_fractional_bbox(
            (
                max(0.0, x0 - pad_x),
                max(0.0, y0 - pad_y),
                min(1.0, x1 + pad_x),
                min(1.0, y1 + pad_y),
            )
        )
    return None


def _registration_aux_drawing_id(evidence: object) -> int | None:
    meta = cast(dict[str, Any] | None, getattr(evidence, "meta", None))
    if not isinstance(meta, dict):
        return None
    return _registration_aux_drawing_id_from_meta(meta)


def _registration_aux_drawing_id_from_meta(meta: dict[str, Any]) -> int | None:
    raw = meta.get("registration_transform")
    if not isinstance(raw, dict):
        return None
    reg_aux = raw.get("registration_aux_drawing_id")
    if reg_aux is None:
        return None
    try:
        return int(reg_aux)
    except (TypeError, ValueError):
        return None


def _has_unprojected_aux_coordinate_match(
    candidates: Sequence[LocationMatchCandidate],
) -> bool:
    for candidate in candidates:
        if (
            candidate.method == ResolutionMethod.COORDINATE_LOOKUP
            and "aux_coords_unprojected" in candidate.notes
        ):
            return True
    return False


def _auxiliary_drawings_need_index(session: Session, dossier: EvidenceDossier) -> bool:
    if dossier.investigation_meta.get("auxiliary_index_pending"):
        return True
    needing_index = dossier.investigation_meta.get("drawing_ids_needing_index")
    if isinstance(needing_index, list):
        for drawing_id in needing_index:
            try:
                did = int(drawing_id)
            except (TypeError, ValueError):
                continue
            readiness = get_master_drawing_index_readiness(session, did)
            if not readiness.is_ready_for_matching:
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
