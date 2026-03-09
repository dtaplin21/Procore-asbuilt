"""
Drawing regions and alignments API.

Phase 2: User-defined regions on master drawings and sub-drawing alignment linkage.
"""
from typing import List, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.dependencies import get_db, get_idempotency_key
from services.idempotency import begin_idempotent_operation, finish_idempotent_operation
from models.schemas import (
    DrawingRegionCreate,
    DrawingRegionResponse,
    DrawingAlignmentCreate,
    DrawingAlignmentResponse,
    DrawingAlignmentListResponse,
    AlignmentUpdate,
)
from services.storage import StorageService

router = APIRouter(prefix="/api/projects", tags=["drawing-alignment"])


def _ensure_master_drawing_in_project(
    storage: StorageService,
    project_id: int,
    master_drawing_id: int,
) -> None:
    """Raise 404 if master drawing does not belong to project."""
    drawing = storage.get_drawing(project_id, master_drawing_id)
    if drawing is None:
        raise HTTPException(
            status_code=404,
            detail=f"Drawing {master_drawing_id} not found in project",
        )


# ------------------------------------------------------------------
# Regions
# ------------------------------------------------------------------


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


# ------------------------------------------------------------------
# Alignments
# ------------------------------------------------------------------


@router.post(
    "/{project_id}/drawings/{master_drawing_id}/alignments",
    response_model=DrawingAlignmentResponse,
)
def create_drawing_alignment(
    project_id: int,
    master_drawing_id: int,
    body: DrawingAlignmentCreate,
    idempotency_key: str = Depends(get_idempotency_key),
    db: Session = Depends(get_db),
) -> DrawingAlignmentResponse:
    """
    Create a sub-drawing alignment to a master (and optionally a region).
    Validates master_drawing and sub_drawing belong to project.
    """
    request_fingerprint = {
        "project_id": project_id,
        "master_drawing_id": master_drawing_id,
        "sub_drawing_id": body.sub_drawing_id,
        "method": body.method,
        "region_id": body.region_id,
    }
    scope = f"drawing_alignment:{master_drawing_id}:{body.sub_drawing_id}:{body.method}:{body.region_id or 'none'}"

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
            return DrawingAlignmentResponse(**cached_resp)
        if row_status == "in_progress":
            raise HTTPException(status_code=409, detail="Request already in progress")
        if row_status == "failed" and cached_resp:
            return DrawingAlignmentResponse(**cached_resp)

    storage = StorageService(db)
    _ensure_master_drawing_in_project(storage, project_id, master_drawing_id)

    sub_drawing = storage.get_drawing(project_id, body.sub_drawing_id)
    if sub_drawing is None:
        raise HTTPException(
            status_code=404,
            detail=f"Sub-drawing {body.sub_drawing_id} not found in project",
        )

    if body.region_id is not None:
        region = storage.get_drawing_region(master_drawing_id, body.region_id)
        if region is None:
            raise HTTPException(
                status_code=404,
                detail=f"Region {body.region_id} not found on master drawing",
            )

    alignment = storage.create_drawing_alignment(
        master_drawing_id,
        body.sub_drawing_id,
        body.method,
        region_id=body.region_id,
    )
    response = DrawingAlignmentResponse.model_validate(alignment)
    finish_idempotent_operation(
        db,
        row_id=cast(int, idem_row.id),
        response_payload=response.model_dump(mode="json"),
        resource_reference={"alignment_id": cast(int, alignment.id)},
    )
    return response


@router.get(
    "/{project_id}/drawings/{master_drawing_id}/alignments",
    response_model=DrawingAlignmentListResponse,
)
def list_drawing_alignments(
    project_id: int,
    master_drawing_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> DrawingAlignmentListResponse:
    """List alignments for a master drawing with pagination (limit, offset)."""
    storage = StorageService(db)
    _ensure_master_drawing_in_project(storage, project_id, master_drawing_id)

    alignments, total = storage.list_drawing_alignments(
        master_drawing_id, limit=limit, offset=offset
    )
    items = [DrawingAlignmentResponse.model_validate(a) for a in alignments]
    return DrawingAlignmentListResponse(items=items, total=total, limit=limit, offset=offset)


@router.patch(
    "/{project_id}/drawings/{master_drawing_id}/alignments/{alignment_id}",
    response_model=DrawingAlignmentResponse,
)
def update_drawing_alignment(
    project_id: int,
    master_drawing_id: int,
    alignment_id: int,
    body: AlignmentUpdate,
    db: Session = Depends(get_db),
) -> DrawingAlignmentResponse:
    """
    Update alignment status, transform, or error_message.
    Transform contract: { "type": "homography", "matrix": [9 numbers], "confidence": 0.0-1.0, "page": 1 }
    """
    storage = StorageService(db)
    _ensure_master_drawing_in_project(storage, project_id, master_drawing_id)

    alignment = storage.get_drawing_alignment_by_id(project_id, master_drawing_id, alignment_id)
    if alignment is None:
        raise HTTPException(
            status_code=404,
            detail=f"Alignment {alignment_id} not found on master drawing",
        )

    if body.status is None and body.transform is None and body.error_message is None:
        return DrawingAlignmentResponse.model_validate(alignment)

    status = body.status if body.status is not None else cast(str, alignment.status)
    transform_dict = body.transform.model_dump() if body.transform is not None else None
    error_msg = body.error_message

    updated = storage.update_alignment_status(
        alignment_id,
        status,
        transform=transform_dict,
        error_message=error_msg,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Alignment not found")
    return DrawingAlignmentResponse.model_validate(updated)
