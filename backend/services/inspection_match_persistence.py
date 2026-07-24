"""Persist inspection match results with backend-only scores."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal, cast

from sqlalchemy.orm import Session

from ai.pipelines.inspection_mapping import UNMAPPED_GEOMETRY
from models.drawing_match_candidate import DrawingMatchCandidate
from models.drawing_overlay import DrawingOverlay
from models.inspection_run import InspectionRun
from models.models import EvidenceRecord
from services.storage import StorageService

logger = logging.getLogger(__name__)

MATCH_SCORE_THRESHOLD = 0.75

MatchStatus = Literal["matched", "needs_review", "no_match"]


@dataclass(frozen=True)
class InternalMatchCandidate:
    score: float
    bbox: tuple[float, float, float, float] | None = None
    page: int = 1
    region_id: int | None = None
    source: str = "clue_match"
    rank: int | None = None


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
) -> None:
    """Write frontend-safe overlay state: match_status and optional bbox only."""
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
        return

    master_drawing_id = int(drawing_id)
    meta_patch = {"match_status": status}

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
        if status == "matched" and bbox is not None:
            setattr(overlay, "geometry", bbox_to_geometry(bbox, page=page))
            if region_id is not None:
                setattr(overlay, "region_id", region_id)
        session.commit()
        return

    geometry = bbox_to_geometry(bbox if status == "matched" else None, page=page)
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
    return {
        "page": page,
        "type": "rect",
        "x": x0,
        "y": y0,
        "width": x1 - x0,
        "height": y1 - y0,
        "label": "inspection_match",
    }
