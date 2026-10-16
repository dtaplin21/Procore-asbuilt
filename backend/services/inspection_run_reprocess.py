"""Re-run inspection PDF investigation and location matching for an existing run."""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy.orm import Session

from models.inspection_run import InspectionRun
from models.models import EvidenceRecord
from services.inspection_matching_jobs import enqueue_inspection_match_job
from services.storage import StorageService


def reprocess_inspection_run(
    db: Session,
    *,
    project_id: int,
    run_id: int,
) -> tuple[int, int]:
    """Enqueue a full re-investigation + match for an existing inspection run.

    Returns ``(inspection_run_id, job_id)``.
    """
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

    meta = dict(cast(dict[str, Any] | None, evidence.meta) or {})
    match_inv = meta.get("matchInvestigation")
    if isinstance(match_inv, dict):
        refreshed = dict(match_inv)
        refreshed.pop("at", None)
        refreshed.pop("investigation_complete", None)
        meta["matchInvestigation"] = refreshed
    evidence.meta = meta  # type: ignore[assignment]
    db.flush()

    storage.update_inspection_run_status(
        run_id,
        "processing",
        clear_error_message=True,
    )

    job = enqueue_inspection_match_job(
        db,
        project_id=project_id,
        inspection_id=str(evidence_id),
        drawing_id=master_drawing_id,
        page=1,
        inspection_run_id=run_id,
        force_investigate=True,
    )
    return run_id, cast(int, job.id)
