"""Hard-delete an inspection run and related project data."""

from __future__ import annotations

import logging
from typing import Any, Optional, cast

from sqlalchemy.orm import Session

from models.document_extraction import DocumentExtraction
from models.drawing_match_candidate import DrawingMatchCandidate
from models.drawing_overlay import DrawingOverlay, UnresolvedEvidence
from models.inspection_run import InspectionRun
from models.models import EvidenceDrawingLink, EvidenceRecord, InspectionResult, JobQueue
from models.review_queue_item import ReviewQueueItem
from services.file_storage import get_file_path
from services.inspection_matching_jobs import JOB_TYPE_INSPECTION_MATCH
from services.storage import StorageService

logger = logging.getLogger(__name__)

_LINKED_EVIDENCE_SOURCE = "linked_evidence"


def _linked_drawing_ids_from_evidence_meta(meta: dict[str, Any] | None) -> list[int]:
    investigation = (meta or {}).get("matchInvestigation") or {}
    raw = investigation.get("linked_drawing_ids") or []
    out: list[int] = []
    seen: set[int] = set()
    for value in raw:
        try:
            drawing_id = int(value)
        except (TypeError, ValueError):
            continue
        if drawing_id in seen:
            continue
        seen.add(drawing_id)
        out.append(drawing_id)
    return out


def _collect_evidence_linked_drawing_ids(
    db: Session,
    *,
    project_id: int,
    evidence_id: int,
    evidence_meta: dict[str, Any] | None,
) -> list[int]:
    drawing_ids = _linked_drawing_ids_from_evidence_meta(evidence_meta)
    seen = set(drawing_ids)
    links = (
        db.query(EvidenceDrawingLink)
        .filter(
            EvidenceDrawingLink.project_id == project_id,
            EvidenceDrawingLink.evidence_id == evidence_id,
        )
        .all()
    )
    for link in links:
        drawing_id = cast(int, link.drawing_id)
        if drawing_id in seen:
            continue
        seen.add(drawing_id)
        drawing_ids.append(drawing_id)
    return drawing_ids


def _drawing_referenced_by_other_evidence(
    db: Session,
    *,
    project_id: int,
    drawing_id: int,
    exclude_evidence_id: int,
) -> bool:
    other_link_count = (
        db.query(EvidenceDrawingLink)
        .filter(
            EvidenceDrawingLink.project_id == project_id,
            EvidenceDrawingLink.drawing_id == drawing_id,
            EvidenceDrawingLink.evidence_id != exclude_evidence_id,
        )
        .count()
    )
    if other_link_count > 0:
        return True

    other_evidence = (
        db.query(EvidenceRecord)
        .filter(
            EvidenceRecord.project_id == project_id,
            EvidenceRecord.id != exclude_evidence_id,
        )
        .all()
    )
    for row in other_evidence:
        for linked_id in _linked_drawing_ids_from_evidence_meta(
            cast(dict[str, Any] | None, row.meta)
        ):
            if linked_id == drawing_id:
                return True
    return False


def _delete_orphaned_linked_drawings_for_evidence(
    storage: StorageService,
    db: Session,
    *,
    project_id: int,
    evidence_id: int,
    drawing_ids: list[int],
) -> None:
    """Remove auxiliary linked-evidence sheets that belonged only to this evidence."""
    project = storage.get_project(project_id)
    master_drawing_id = (
        cast(int, project.master_drawing_id)
        if project is not None and project.master_drawing_id is not None
        else None
    )

    for drawing_id in drawing_ids:
        if master_drawing_id is not None and drawing_id == master_drawing_id:
            continue
        if _drawing_referenced_by_other_evidence(
            db,
            project_id=project_id,
            drawing_id=drawing_id,
            exclude_evidence_id=evidence_id,
        ):
            continue

        drawing = storage.get_drawing(project_id, drawing_id)
        if drawing is None:
            continue
        if cast(str, drawing.source) != _LINKED_EVIDENCE_SOURCE:
            continue

        try:
            storage.delete_drawing_hard(project_id, drawing_id)
        except ValueError:
            logger.warning(
                "delete_inspection_run_from_project: linked drawing %s missing during cleanup",
                drawing_id,
            )


def delete_inspection_run_from_project(
    db: Session,
    *,
    project_id: int,
    run_id: int,
) -> bool:
    """Delete an inspection run, its evidence file, and related pipeline rows."""
    storage = StorageService(db)
    run = storage.get_inspection_run(project_id, run_id)
    if run is None:
        return False

    evidence_id = cast(Optional[int], getattr(run, "evidence_id", None))
    file_id = str(evidence_id) if evidence_id is not None else None
    storage_key: Optional[str] = None
    linked_drawing_ids_to_cleanup: list[int] = []

    if evidence_id is not None:
        evidence = storage.get_evidence_record(project_id, evidence_id)
        if evidence is not None:
            storage_key = cast(Optional[str], evidence.storage_key)
            linked_drawing_ids_to_cleanup = _collect_evidence_linked_drawing_ids(
                db,
                project_id=project_id,
                evidence_id=evidence_id,
                evidence_meta=cast(dict[str, Any] | None, evidence.meta),
            )

    pending_jobs = (
        db.query(JobQueue)
        .filter(
            JobQueue.project_id == project_id,
            JobQueue.job_type == JOB_TYPE_INSPECTION_MATCH,
        )
        .all()
    )
    for job in pending_jobs:
        input_data = getattr(job, "input_data", None) or {}
        if file_id and str(input_data.get("inspection_id")) == file_id:
            db.delete(job)

    if file_id:
        db.query(DrawingMatchCandidate).filter(
            DrawingMatchCandidate.inspection_id == file_id
        ).delete(synchronize_session=False)
        db.query(DocumentExtraction).filter(
            DocumentExtraction.file_id == file_id
        ).delete(synchronize_session=False)
        db.query(ReviewQueueItem).filter(
            ReviewQueueItem.file_id == file_id
        ).delete(synchronize_session=False)

    db.query(DrawingOverlay).filter(
        DrawingOverlay.inspection_run_id == run_id
    ).delete(synchronize_session=False)
    db.query(UnresolvedEvidence).filter(
        UnresolvedEvidence.inspection_run_id == run_id
    ).delete(synchronize_session=False)
    db.query(DrawingMatchCandidate).filter(
        DrawingMatchCandidate.inspection_run_id == run_id
    ).delete(synchronize_session=False)
    db.query(InspectionResult).filter(
        InspectionResult.inspection_run_id == run_id
    ).delete(synchronize_session=False)

    db.delete(run)
    db.commit()

    if evidence_id is not None:
        remaining_runs = (
            db.query(InspectionRun)
            .filter(InspectionRun.evidence_id == evidence_id)
            .count()
        )
        if remaining_runs == 0:
            db.query(EvidenceDrawingLink).filter(
                EvidenceDrawingLink.project_id == project_id,
                EvidenceDrawingLink.evidence_id == evidence_id,
            ).delete(synchronize_session=False)

            evidence = storage.get_evidence_record(project_id, evidence_id)
            if evidence is not None:
                storage_key = cast(Optional[str], evidence.storage_key) or storage_key
                db.delete(evidence)
                db.commit()

            _delete_orphaned_linked_drawings_for_evidence(
                storage,
                db,
                project_id=project_id,
                evidence_id=evidence_id,
                drawing_ids=linked_drawing_ids_to_cleanup,
            )

    if storage_key:
        try:
            get_file_path(storage_key).unlink(missing_ok=True)
        except OSError as exc:
            logger.warning(
                "delete_inspection_run_from_project: could not remove file %s: %s",
                storage_key,
                exc,
            )

    return True
