"""
Inspection runs API.

Create and list inspection runs for a project.
"""
import logging
from typing import Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.dependencies import get_db, get_idempotency_key
from services.idempotency import begin_idempotent_operation, finish_idempotent_operation
from ai.pipelines.inspection_mapping import run_inspection_mapping
from models.schemas import (
    InspectionRunCreate,
    InspectionRunListResponse,
    InspectionRunProgressResponse,
    InspectionRunReprocessResponse,
    InspectionRunResponse,
)
from api.schemas.inspection_match_response import BboxResponse, InspectionMatchStatusResponse
from services.inspection_matching_jobs import load_inspection_match_status
from services.inspection_run_deletion import delete_inspection_run_from_project
from services.inspection_run_activity import inspection_run_to_response
from services.inspection_run_progress import get_run_progress
from services.storage import StorageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["inspections"])
match_router = APIRouter(prefix="/api/inspections", tags=["inspections"])


@match_router.get(
    "/{inspection_id}/match-status",
    response_model=InspectionMatchStatusResponse,
)
def get_match_status(
    inspection_id: str,
    db: Session = Depends(get_db),
) -> InspectionMatchStatusResponse:
    """Return frontend-safe inspection match status (no confidence or score)."""
    record = load_inspection_match_status(db, inspection_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Inspection not found")

    bbox = None
    if record.bbox is not None:
        x, y, width, height = record.bbox
        bbox = BboxResponse(x=x, y=y, width=width, height=height)

    return InspectionMatchStatusResponse(
        inspection_id=inspection_id,
        match_status=record.match_status,
        bbox=bbox,
    )


def _ensure_project_exists(storage: StorageService, project_id: int) -> None:
    """Raise 404 if project does not exist."""
    if storage.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")


def _ensure_drawing_in_project(
    storage: StorageService,
    project_id: int,
    master_drawing_id: int,
) -> None:
    """Raise 404 if drawing does not belong to project."""
    drawing = storage.get_drawing(project_id, master_drawing_id)
    if drawing is None:
        raise HTTPException(
            status_code=404,
            detail=f"Drawing {master_drawing_id} not found in project",
        )


def _ensure_evidence_in_project(
    storage: StorageService,
    project_id: int,
    evidence_id: int,
) -> None:
    """Raise 404 if evidence does not belong to project."""
    evidence = storage.get_evidence_record(project_id, evidence_id)
    if evidence is None:
        raise HTTPException(
            status_code=404,
            detail=f"Evidence {evidence_id} not found in project",
        )


@router.post(
    "/{project_id}/inspections/runs",
    response_model=InspectionRunResponse,
    status_code=201,
)
def create_inspection_run(
    project_id: int,
    body: InspectionRunCreate,
    idempotency_key: str = Depends(get_idempotency_key),
    db: Session = Depends(get_db),
) -> InspectionRunResponse:
    """
    Create an inspection run and run the pipeline (MVP: synchronous).

    Validates drawing and evidence belong to project. Creates run with status queued,
    then kicks off the inspection mapping pipeline.
    """
    request_fingerprint = {
        "project_id": project_id,
        "master_drawing_id": body.master_drawing_id,
        "evidence_id": body.evidence_id,
        "skip_pipeline": body.skip_pipeline,
    }
    scope = (
        f"inspection_run:{project_id}:{body.master_drawing_id}:"
        f"{body.evidence_id or 'none'}:{'defer' if body.skip_pipeline else 'run'}"
    )

    try:
        idem_row, should_execute = begin_idempotent_operation(
            db,
            scope=scope,
            idempotency_key=idempotency_key,
            request_payload=request_fingerprint,
            ttl_minutes=60,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not should_execute:
        row_status = getattr(idem_row, "status", None)
        cached_resp = dict(getattr(idem_row, "response_payload", None) or {})
        if row_status == "completed":
            return InspectionRunResponse(**cached_resp)
        if row_status == "in_progress":
            raise HTTPException(status_code=409, detail="Request already in progress")
        if row_status == "failed":
            return InspectionRunResponse(**cached_resp)

    storage = StorageService(db)
    _ensure_project_exists(storage, project_id)
    _ensure_drawing_in_project(storage, project_id, body.master_drawing_id)

    if body.evidence_id is not None:
        _ensure_evidence_in_project(storage, project_id, body.evidence_id)

    run = storage.create_inspection_run(
        project_id=project_id,
        master_drawing_id=body.master_drawing_id,
        evidence_id=body.evidence_id,
        inspection_type=body.inspection_type,
    )

    if body.skip_pipeline:
        response = InspectionRunResponse.model_validate(run)
        finish_idempotent_operation(
            db,
            row_id=cast(int, idem_row.id),
            response_payload=response.model_dump(mode="json"),
            resource_reference={"inspection_run_id": cast(int, run.id)},
        )
        return response

    # MVP: run pipeline synchronously
    result = run_inspection_mapping(db, run)

    if result.get("error"):
        # Pipeline returned error; run status already updated to failed
        # Re-fetch run for response (status/error_message updated)
        run = storage.get_inspection_run(project_id, cast(int, run.id))
        if run is None:
            raise HTTPException(status_code=500, detail="Run created but not found after pipeline")
        response = InspectionRunResponse.model_validate(run)
        finish_idempotent_operation(
            db,
            row_id=cast(int, idem_row.id),
            response_payload=response.model_dump(mode="json"),
            resource_reference={"inspection_run_id": cast(int, run.id)},
        )
        return response

    # Re-fetch run for fresh status/updated_at after pipeline
    run = storage.get_inspection_run(project_id, cast(int, run.id))
    if run is None:
        raise HTTPException(status_code=500, detail="Run not found after pipeline")
    response = InspectionRunResponse.model_validate(run)
    finish_idempotent_operation(
        db,
        row_id=cast(int, idem_row.id),
        response_payload=response.model_dump(mode="json"),
        resource_reference={"inspection_run_id": cast(int, run.id)},
    )
    return response


@router.get(
    "/{project_id}/inspections/runs",
    response_model=InspectionRunListResponse,
)
def list_inspection_runs(
    project_id: int,
    master_drawing_id: Optional[int] = Query(None, description="Filter by master drawing"),
    status: Optional[str] = Query(None, description="Filter by status (queued, processing, complete, failed)"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    db: Session = Depends(get_db),
) -> InspectionRunListResponse:
    """List inspection runs for a project. Sorted by created_at desc. Paginated."""
    storage = StorageService(db)
    _ensure_project_exists(storage, project_id)

    items, total = storage.list_inspection_runs(
        project_id,
        master_drawing_id=master_drawing_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return InspectionRunListResponse(
        items=[inspection_run_to_response(db, r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


def _queue_inspection_run_job(
    db: Session,
    *,
    project_id: int,
    run_id: int,
    queue_fn,
    queued_status: str = "processing",
) -> InspectionRunReprocessResponse:
    storage = StorageService(db)
    _ensure_project_exists(storage, project_id)
    try:
        run_id_out, job_id = queue_fn(
            db,
            project_id=project_id,
            run_id=run_id,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Inspection run not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return InspectionRunReprocessResponse(
        inspection_run_id=run_id_out,
        job_id=job_id,
        status=queued_status,
    )


@router.get(
    "/{project_id}/inspections/runs/{run_id}/progress",
    response_model=InspectionRunProgressResponse,
)
def get_inspection_run_progress(
    project_id: int,
    run_id: int,
    db: Session = Depends(get_db),
) -> InspectionRunProgressResponse:
    """Coarse AI pipeline progress for polling while a run is active."""
    storage = StorageService(db)
    _ensure_project_exists(storage, project_id)
    run = storage.get_inspection_run(project_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Inspection run not found")
    payload = get_run_progress(db, project_id=project_id, run_id=run_id)
    if payload is None:
        return InspectionRunProgressResponse(run_id=run_id)
    return InspectionRunProgressResponse.model_validate({"run_id": run_id, **payload})


@router.get("/{project_id}/inspections/runs/{run_id}/placement-forensics")
def inspection_run_placement_forensics_route(
    project_id: int,
    run_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """OCR corpus, dossier/vision inputs, scope trace path, and placement blockers."""
    from scripts.export_inspection_placement_forensics import export_forensics

    storage = StorageService(db)
    _ensure_project_exists(storage, project_id)
    try:
        return export_forensics(db, run_id=run_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Inspection run not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{project_id}/inspections/runs/{run_id}/index-inventory")
def inspection_run_index_inventory_route(
    project_id: int,
    run_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Structured report of indexed pages, clues, and linked drawings for a run."""
    from services.inspection_index_export import build_inspection_index_inventory

    storage = StorageService(db)
    _ensure_project_exists(storage, project_id)
    try:
        return build_inspection_index_inventory(
            db,
            project_id=project_id,
            run_id=run_id,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Inspection run not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/{project_id}/inspections/runs/{run_id}/reindex",
    response_model=InspectionRunReprocessResponse,
)
def reindex_inspection_run_route(
    project_id: int,
    run_id: int,
    db: Session = Depends(get_db),
) -> InspectionRunReprocessResponse:
    """Re-follow linked PDFs and refresh clues (no master placement)."""
    from services.inspection_run_reprocess import reindex_inspection_run

    return _queue_inspection_run_job(
        db,
        project_id=project_id,
        run_id=run_id,
        queue_fn=reindex_inspection_run,
        queued_status="indexing",
    )


@router.post(
    "/{project_id}/inspections/runs/{run_id}/rematch",
    response_model=InspectionRunReprocessResponse,
)
def rematch_inspection_run_route(
    project_id: int,
    run_id: int,
    db: Session = Depends(get_db),
) -> InspectionRunReprocessResponse:
    """Re-run location matching using existing indexed clues (no link re-follow)."""
    from services.inspection_run_reprocess import rematch_inspection_run

    return _queue_inspection_run_job(
        db,
        project_id=project_id,
        run_id=run_id,
        queue_fn=rematch_inspection_run,
        queued_status="matching",
    )


@router.post(
    "/{project_id}/inspections/runs/{run_id}/reprocess",
    response_model=InspectionRunReprocessResponse,
)
def reprocess_inspection_run_route(
    project_id: int,
    run_id: int,
    db: Session = Depends(get_db),
) -> InspectionRunReprocessResponse:
    """Index linked files then re-run placement in one worker job."""
    from services.inspection_run_reprocess import reprocess_inspection_run

    return _queue_inspection_run_job(
        db,
        project_id=project_id,
        run_id=run_id,
        queue_fn=reprocess_inspection_run,
    )


@router.delete("/{project_id}/inspections/runs/{run_id}")
def delete_inspection_run(
    project_id: int,
    run_id: int,
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    """Delete an inspection run, its evidence file, overlays, and pipeline data."""
    storage = StorageService(db)
    _ensure_project_exists(storage, project_id)

    deleted = delete_inspection_run_from_project(
        db,
        project_id=project_id,
        run_id=run_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Inspection run not found")

    return {"ok": True}
