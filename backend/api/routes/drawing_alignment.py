"""
Drawing regions API.

User-defined regions on master drawings for inspection mapping.
"""
from typing import List, cast

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.dependencies import get_db, get_idempotency_key
from services.idempotency import begin_idempotent_operation, finish_idempotent_operation
from models.schemas import (
    DrawingRegionCreate,
    DrawingRegionResponse,
)
from services.storage import StorageService

router = APIRouter(prefix="/api/projects", tags=["drawing-alignment"])


def _ensure_master_drawing_in_project(
    storage: StorageService,
    project_id: int,
    master_drawing_id: int,
) -> None:
    """Raise 404 if master drawing does not belong to project.

    If the project has a canonical ``master_drawing_id``, raise 409 when the path
    does not match (workspace routes must use the project's master sheet).
    """
    drawing = storage.get_drawing(project_id, master_drawing_id)
    if drawing is None:
        raise HTTPException(
            status_code=404,
            detail=f"Drawing {master_drawing_id} not found in project",
        )
    project = storage.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    canonical_id = getattr(project, "master_drawing_id", None)
    if canonical_id is not None and int(canonical_id) != int(master_drawing_id):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Drawing {master_drawing_id} is not this project's canonical master; "
                f"use master drawing id {int(canonical_id)} (project.masterDrawingId on dashboard summary)."
            ),
        )


@router.post(
    "/{project_id}/drawings/{master_drawing_id}/regions",
    response_model=DrawingRegionResponse,
)
def create_drawing_region(
    project_id: int,
    master_drawing_id: int,
    body: DrawingRegionCreate,
    idempotency_key: str = Depends(get_idempotency_key),
    db: Session = Depends(get_db),
) -> DrawingRegionResponse:
    """
    Create a user-defined region on a master drawing.
    Validates that master_drawing belongs to project.
    """
    request_fingerprint = {
        "project_id": project_id,
        "master_drawing_id": master_drawing_id,
        "label": body.label,
        "page": body.page,
        "inspection_type_tags": body.inspection_type_tags,
        "location_tags": body.location_tags,
    }
    scope = f"drawing_region:{master_drawing_id}:{body.label}:{body.page}"

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
        if row_status == "completed" and cached_resp:
            return DrawingRegionResponse(**cached_resp)
        if row_status == "in_progress":
            raise HTTPException(status_code=409, detail="Request already in progress")
        if row_status == "failed" and cached_resp:
            return DrawingRegionResponse(**cached_resp)

    storage = StorageService(db)
    _ensure_master_drawing_in_project(storage, project_id, master_drawing_id)

    region = storage.create_drawing_region(
        master_drawing_id,
        label=body.label,
        page=body.page,
        geometry=body.geometry,
        inspection_type_tags=body.inspection_type_tags,
        location_tags=body.location_tags,
    )
    response = DrawingRegionResponse.model_validate(region)
    finish_idempotent_operation(
        db,
        row_id=cast(int, idem_row.id),
        response_payload=response.model_dump(mode="json"),
        resource_reference={"region_id": cast(int, region.id)},
    )
    return response


@router.get(
    "/{project_id}/drawings/{master_drawing_id}/regions",
    response_model=List[DrawingRegionResponse],
)
def list_drawing_regions(
    project_id: int,
    master_drawing_id: int,
    db: Session = Depends(get_db),
) -> List[DrawingRegionResponse]:
    """List all regions for a master drawing."""
    storage = StorageService(db)
    _ensure_master_drawing_in_project(storage, project_id, master_drawing_id)

    regions = storage.list_drawing_regions(master_drawing_id)
    return [DrawingRegionResponse.model_validate(r) for r in regions]
