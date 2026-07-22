"""Hard-delete an inspection run and related project data."""

from __future__ import annotations

import logging
from typing import Optional, cast

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

    if evidence_id is not None:
        evidence = storage.get_evidence_record(project_id, evidence_id)
        if evidence is not None:
            storage_key = cast(Optional[str], evidence.storage_key)

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
