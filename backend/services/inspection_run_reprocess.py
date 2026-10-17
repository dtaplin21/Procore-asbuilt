"""Re-run inspection indexing and/or location matching for an existing run."""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy.orm import Session

from models.inspection_run import InspectionRun
from models.models import EvidenceRecord
from services.inspection_matching_jobs import enqueue_inspection_match_job
from services.storage import StorageService


def _load_run_context(
    db: Session,
    *,
    project_id: int,
    run_id: int,
) -> tuple[InspectionRun, int, int]:
    storage = StorageService(db)
    run = storage.get_inspection_run(project_id, run_id)
    if run is None:
        raise LookupError("Inspection run not found")

    evidence_id = cast(int | None, run.evidence_id)
    master_drawing_id = cast(int | None, run.master_drawing_id)
    if evidence_id is None:
        raise ValueError("Inspection run has no evidence file uploaded yet")
    if master_drawing_id is None:
        raise ValueError("Inspection run has no master drawing")

    evidence = storage.get_evidence_record(project_id, evidence_id)
    if evidence is None:
        raise LookupError("Evidence not found")

    return run, evidence_id, master_drawing_id


def _clear_investigation_freshness(db: Session, evidence_id: int) -> None:
    evidence = db.get(EvidenceRecord, evidence_id)
    if evidence is None:
        return
    meta = dict(cast(dict[str, Any] | None, evidence.meta) or {})
    match_inv = meta.get("matchInvestigation")
    if isinstance(match_inv, dict):
        refreshed = dict(match_inv)
        refreshed.pop("at", None)
        refreshed.pop("investigation_complete", None)
        meta["matchInvestigation"] = refreshed
    evidence.meta = meta  # type: ignore[assignment]
    db.flush()


def _mark_run_processing(db: Session, run_id: int) -> None:
    StorageService(db).update_inspection_run_status(
        run_id,
        "processing",
        clear_error_message=True,
    )


def reindex_inspection_run(
    db: Session,
    *,
    project_id: int,
    run_id: int,
) -> tuple[int, int]:
    """Enqueue PDF investigation / linked-file indexing only (no master placement)."""
    _load_run_context(db, project_id=project_id, run_id=run_id)
    run = db.get(InspectionRun, run_id)
    assert run is not None
    evidence_id = cast(int, run.evidence_id)
    master_drawing_id = cast(int, run.master_drawing_id)

    _clear_investigation_freshness(db, evidence_id)
    _mark_run_processing(db, run_id)

    job = enqueue_inspection_match_job(
        db,
        project_id=project_id,
        inspection_id=str(evidence_id),
        drawing_id=master_drawing_id,
        page=1,
        inspection_run_id=run_id,
        index_only=True,
        force_investigate=True,
    )
    return run_id, cast(int, job.id)


def rematch_inspection_run(
    db: Session,
    *,
    project_id: int,
    run_id: int,
) -> tuple[int, int]:
    """Enqueue location matching only (uses indexed clues; does not re-follow PDF links)."""
    _load_run_context(db, project_id=project_id, run_id=run_id)
    run = db.get(InspectionRun, run_id)
    assert run is not None
    evidence_id = cast(int, run.evidence_id)
    master_drawing_id = cast(int, run.master_drawing_id)

    _mark_run_processing(db, run_id)

    job = enqueue_inspection_match_job(
        db,
        project_id=project_id,
        inspection_id=str(evidence_id),
        drawing_id=master_drawing_id,
        page=1,
        inspection_run_id=run_id,
        match_only=True,
    )
    return run_id, cast(int, job.id)


def reprocess_inspection_run(
    db: Session,
    *,
    project_id: int,
    run_id: int,
) -> tuple[int, int]:
    """Enqueue index + match in one worker job (index phase then placement phase)."""
    _load_run_context(db, project_id=project_id, run_id=run_id)
    run = db.get(InspectionRun, run_id)
    assert run is not None
    evidence_id = cast(int, run.evidence_id)
    master_drawing_id = cast(int, run.master_drawing_id)

    _clear_investigation_freshness(db, evidence_id)
    _mark_run_processing(db, run_id)

    job = enqueue_inspection_match_job(
        db,
        project_id=project_id,
        inspection_id=str(evidence_id),
        drawing_id=master_drawing_id,
        page=1,
        inspection_run_id=run_id,
        index_only=True,
        chain_match=True,
        force_investigate=True,
    )
    return run_id, cast(int, job.id)
