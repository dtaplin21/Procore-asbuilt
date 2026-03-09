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
from models.schemas import InspectionRunCreate, InspectionRunListResponse, InspectionRunResponse
from services.storage import StorageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["inspections"])


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
    }
    scope = f"inspection_run:{project_id}:{body.master_drawing_id}:{body.evidence_id or 'none'}"

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
        items=[InspectionRunResponse.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )
