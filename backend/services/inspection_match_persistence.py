"""Persist inspection match results with backend-only scores."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast

from sqlalchemy.orm import Session

from services.overlay_geometry import UNMAPPED_GEOMETRY
from models.drawing_match_candidate import DrawingMatchCandidate
from models.drawing_overlay import DrawingOverlay
from models.inspection_run import InspectionRun
from models.models import EvidenceRecord
from services.storage import StorageService

if TYPE_CHECKING:
    from ai.pipelines.clue_fusion_scorer import FusedCandidateScore
    from ai.pipelines.scope_geometry import ScopeGeometry

logger = logging.getLogger(__name__)

MATCH_SCORE_THRESHOLD = 0.75

MatchStatus = Literal["matched", "needs_review", "no_match", "index_pending"]


@dataclass(frozen=True)
class InternalMatchCandidate:
    score: float
    bbox: tuple[float, float, float, float] | None = None
    page: int = 1
    region_id: int | None = None
    source: str = "clue_match"
    rank: int | None = None
    meta_json: dict[str, Any] | None = None


@dataclass(frozen=True)
class AgentMatchResult:
    status: MatchStatus
    scope: ScopeGeometry | None
    region_id: int | None
    page: int
    rationale: str
    fused_score: float | None


def match_status_from_internal_score(internal_score: float) -> MatchStatus:
    return "matched" if internal_score >= MATCH_SCORE_THRESHOLD else "needs_review"


def record_internal_match_candidate(
    session: Session,
    *,
    inspection_id: str,
    drawing_id: str | int,
    candidate: InternalMatchCandidate,
    inspection_run_id: int | None = None,
) -> DrawingMatchCandidate:
    """Persist a backend-only scored candidate row."""
    run_id = resolve_inspection_run_id(
        session,
        inspection_id,
        inspection_run_id=inspection_run_id,
    )
    row = DrawingMatchCandidate(
        inspection_id=str(inspection_id),
        inspection_run_id=run_id,
        master_drawing_id=int(drawing_id),
        page=int(candidate.page),
        region_id=candidate.region_id,
        score=float(candidate.score),
        bbox_json=list(candidate.bbox) if candidate.bbox is not None else None,
        source=candidate.source,
        rank=candidate.rank,
        meta_json=dict(candidate.meta_json) if candidate.meta_json is not None else None,
    )
    session.add(row)
    session.flush()
    return row


def persist_inspection_match_overlay(
    session: Session,
    *,
    inspection_id: str,
    drawing_id: str | int,
    status: MatchStatus,
    bbox: tuple[float, float, float, float] | None,
    page: int = 1,
    region_id: int | None = None,
    inspection_run_id: int | None = None,
    scope: ScopeGeometry | None = None,
) -> int | None:
    """Write frontend-safe overlay state: match_status and optional geometry."""
    run_id = resolve_inspection_run_id(
        session,
        inspection_id,
        inspection_run_id=inspection_run_id,
    )
    if run_id is None:
        logger.warning(
            "inspection_match_missing_run",
            extra={"inspection_id": inspection_id, "match_status": status},
        )
        return None

    master_drawing_id = int(drawing_id)
    meta_patch = {"match_status": status}
    has_resolved_geometry = status in ("matched", "needs_review") and (
        scope is not None or bbox is not None
    )

    overlay = (
        session.query(DrawingOverlay)
        .filter(
            DrawingOverlay.inspection_run_id == run_id,
            DrawingOverlay.master_drawing_id == master_drawing_id,
        )
        .order_by(DrawingOverlay.id.desc())
        .first()
    )

    if overlay is not None:
        current_meta = overlay.meta if isinstance(overlay.meta, dict) else {}
        setattr(overlay, "meta", {**current_meta, **meta_patch})
        if has_resolved_geometry:
            setattr(
                overlay,
                "geometry",
                scope_to_geometry(
                    scope,
                    fallback_bbox=bbox,
                    page=page,
                ),
            )
            if region_id is not None:
                setattr(overlay, "region_id", region_id)
        session.commit()
        return cast(int, overlay.id)

    geometry = scope_to_geometry(
        scope if status in ("matched", "needs_review") else None,
        fallback_bbox=bbox if status in ("matched", "needs_review") else None,
        page=page,
    )
    storage = StorageService(session)
    created = storage.create_drawing_overlay(
        master_drawing_id,
        geometry,
        "unknown",
        meta=meta_patch,
        inspection_run_id=run_id,
        label="Inspection match",
    )
    if region_id is not None:
        setattr(created, "region_id", region_id)
        session.commit()
    return cast(int, created.id)


def finalize_inspection_match_from_internal_candidate(
    session: Session,
    *,
    inspection_id: str,
    drawing_id: str | int,
    candidate: InternalMatchCandidate,
    inspection_run_id: int | None = None,
) -> MatchStatus:
    """Record internal score, then persist frontend-safe overlay status."""
    record_internal_match_candidate(
        session,
        inspection_id=inspection_id,
        drawing_id=drawing_id,
        candidate=candidate,
        inspection_run_id=inspection_run_id,
    )
    status = match_status_from_internal_score(candidate.score)
    persist_inspection_match_overlay(
        session,
        inspection_id=inspection_id,
        drawing_id=drawing_id,
        status=status,
        bbox=candidate.bbox if status == "matched" else None,
        page=candidate.page,
        region_id=candidate.region_id,
        inspection_run_id=inspection_run_id,
    )
    return status


def resolve_inspection_run_id(
    session: Session,
    inspection_id: str,
    *,
    inspection_run_id: int | None = None,
) -> int | None:
    """Map an API/job identifier to an inspection run id.

    ``inspection_run_id`` wins when provided (upload/job path). Otherwise
    ``inspection_id`` may be an evidence record id or a run id. Evidence ids
    are resolved before run ids so numeric collisions (e.g. evidence 266 vs
    run 266) attach to the run that owns that evidence file.
    """
    if inspection_run_id is not None:
        run = (
            session.query(InspectionRun)
            .filter(InspectionRun.id == inspection_run_id)
            .first()
        )
        if run is not None:
            return inspection_run_id

    if not inspection_id.isdigit():
        return None

    numeric_id = int(inspection_id)

    evidence = (
        session.query(EvidenceRecord)
        .filter(EvidenceRecord.id == numeric_id)
        .first()
    )
    if evidence is not None:
        run = (
            session.query(InspectionRun)
            .filter(InspectionRun.evidence_id == numeric_id)
            .order_by(InspectionRun.id.desc())
            .first()
        )
        if run is not None:
            return cast(int, run.id)

    run = (
        session.query(InspectionRun)
        .filter(InspectionRun.id == numeric_id)
        .first()
    )
    if run is not None:
        return numeric_id

    run = (
        session.query(InspectionRun)
        .filter(InspectionRun.evidence_id == numeric_id)
        .order_by(InspectionRun.id.desc())
        .first()
    )
    if run is not None:
        return cast(int, run.id)

    return None


def scope_to_geometry(
    scope: ScopeGeometry | None,
    *,
    fallback_bbox: tuple[float, float, float, float] | None = None,
    page: int,
) -> dict[str, Any]:
    """Prefer ScopeGeometry; fall back to rect from bbox; else UNMAPPED_GEOMETRY."""
    if scope is not None:
        try:
            geometry = scope.to_geometry_json()
        except ValueError:
            geometry = None
        if geometry is not None:
            geometry["label"] = "inspection_match"
            return geometry

    if fallback_bbox is not None:
        from ai.pipelines.scope_geometry import clamp_fractional_bbox

        return bbox_to_geometry(clamp_fractional_bbox(fallback_bbox), page=page)

    geometry = dict(UNMAPPED_GEOMETRY)
    geometry["page"] = page
    return geometry


def bbox_to_geometry(
    bbox: tuple[float, float, float, float] | None,
    *,
    page: int,
) -> dict[str, Any]:
    if bbox is None:
        geometry = dict(UNMAPPED_GEOMETRY)
        geometry["page"] = page
        return geometry

    x0, y0, x1, y1 = bbox
    from ai.pipelines.scope_geometry import clamp_fractional_bbox

    x0, y0, x1, y1 = clamp_fractional_bbox((x0, y0, x1, y1))
    return {
        "page": page,
        "type": "rect",
        "x": x0,
        "y": y0,
        "width": x1 - x0,
        "height": y1 - y0,
        "label": "inspection_match",
    }


def persist_agent_match_result(
    session: Session,
    *,
    evidence_id: int,
    master_drawing_id: int,
    result: AgentMatchResult,
    ranked_scores: list[FusedCandidateScore],
    page: int = 1,
    inspection_run_id: int | None = None,
) -> int | None:
    """Persist fused candidates (with rationale meta) and frontend-safe overlay scope."""
    inspection_id = str(evidence_id)
    bbox = _fallback_bbox_for_persist(result, ranked_scores)

    for rank, fused in enumerate(ranked_scores, start=1):
        record_internal_match_candidate(
            session,
            inspection_id=inspection_id,
            drawing_id=master_drawing_id,
            candidate=InternalMatchCandidate(
                score=float(fused.fused_score),
                bbox=fused.candidate.bbox_fractional,
                page=int(fused.candidate.page),
                region_id=fused.candidate.region_id,
                source="inspection_location_agent",
                rank=rank,
                meta_json=_fused_score_to_candidate_meta(fused),
            ),
            inspection_run_id=inspection_run_id,
        )

    overlay_id = persist_inspection_match_overlay(
        session,
        inspection_id=inspection_id,
        drawing_id=master_drawing_id,
        status=result.status,
        bbox=bbox if result.status in ("matched", "needs_review") else None,
        page=page,
        region_id=result.region_id,
        inspection_run_id=inspection_run_id,
        scope=result.scope if result.status in ("matched", "needs_review") else None,
    )
    if overlay_id is None:
        return None

    overlay = session.get(DrawingOverlay, overlay_id)
    if overlay is None:
        return overlay_id

    current_meta = overlay.meta if isinstance(overlay.meta, dict) else {}
    agent_meta = {
        **current_meta,
        "match_status": result.status,
        "agent_rationale": result.rationale,
        "agent_fused_score": result.fused_score,
        "agent_candidates": [
            {"rank": rank, **_fused_score_to_candidate_meta(fused)}
            for rank, fused in enumerate(ranked_scores, start=1)
        ],
    }
    setattr(overlay, "meta", agent_meta)
    session.commit()
    return overlay_id


def _fused_score_to_candidate_meta(fused: FusedCandidateScore) -> dict[str, Any]:
    return {
        "rationale": fused.rationale,
        "clue_hits": [
            {
                "clue_value": hit.clue_value,
                "dimension": hit.dimension,
                "weight": hit.weight,
            }
            for hit in fused.clue_hits
        ],
        "conflicts": list(fused.conflicts),
        "fused_score": fused.fused_score,
    }


def _fallback_bbox_for_persist(
    result: AgentMatchResult,
    ranked_scores: list[FusedCandidateScore],
) -> tuple[float, float, float, float] | None:
    if result.scope is not None:
        scope = result.scope
        if (
            scope.type == "rect"
            and scope.x is not None
            and scope.y is not None
            and scope.width is not None
            and scope.height is not None
        ):
            return (
                scope.x,
                scope.y,
                scope.x + scope.width,
                scope.y + scope.height,
            )
        envelope = _bbox_from_polyline_scope(scope)
        if envelope is not None:
            return envelope

    if ranked_scores:
        return ranked_scores[0].candidate.bbox_fractional
    return None


def _bbox_from_polyline_scope(
    scope: ScopeGeometry,
) -> tuple[float, float, float, float] | None:
    if scope.type != "polyline" or not scope.points:
        return None
    xs = [point[0] for point in scope.points]
    ys = [point[1] for point in scope.points]
    return (min(xs), min(ys), max(xs), max(ys))
