"""
Routes for backend drawing regions — the inspectable-zone catalog from
the region-visibility spec.

PR1: region-inspection-summary
PR2: create / list / patch / delete

Reconciled with this codebase: project-scoped paths under
``/api/projects/{project_id}/drawings/{master_drawing_id}/…``, integer
PKs, normalized geometry JSON (see models.schemas.DrawingRegionCreate).
"""

from __future__ import annotations

from typing import List, cast

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.dependencies import get_db, get_idempotency_key
from models.schemas import (
    DrawingRegionCreate,
    DrawingRegionResponse,
    DrawingRegionUpdate,
    RegionInspectionSummaryEntryResponse,
    RegionInspectionSummaryResponse,
)
from services.idempotency import begin_idempotent_operation, finish_idempotent_operation
from services.region_inspection_summary import (
    RegionInspectionSummaryEntry,
    build_region_inspection_summary,
)
from services.storage import StorageService

router = APIRouter(prefix="/api/projects", tags=["drawing-regions"])


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


def _summary_entry_response(
    entry: RegionInspectionSummaryEntry,
) -> RegionInspectionSummaryEntryResponse:
    return RegionInspectionSummaryEntryResponse(
        region_id=entry.region_id,
        master_drawing_id=entry.master_drawing_id,
        state=entry.state.value,
        label=entry.label,
        bbox=list(entry.bbox),
        location_tags=list(entry.location_tags),
        inspection_type_tags=list(entry.inspection_type_tags),
        latest_overlay_id=entry.latest_overlay_id,
        latest_inspection_run_id=entry.latest_inspection_run_id,
        inspection_type=entry.inspection_type,
        inspection_status_display=entry.inspection_status_display,
        inspection_date=entry.inspection_date,
        procore_inspection_id=entry.procore_inspection_id,
    )


@router.get(
    "/{project_id}/drawings/{master_drawing_id}/region-inspection-summary",
    response_model=RegionInspectionSummaryResponse,
)
def get_region_inspection_summary(
    project_id: int,
    master_drawing_id: int,
    db: Session = Depends(get_db),
) -> RegionInspectionSummaryResponse:
    """One entry per backend region: hidden or inspected, with tooltip fields.

    Returns 200 with an empty ``items`` list when the drawing has no regions
    yet. Still 404 when the drawing is not in the project.
    """
    storage = StorageService(db)
    _ensure_master_drawing_in_project(storage, project_id, master_drawing_id)

    entries = build_region_inspection_summary(db, master_drawing_id)
    return RegionInspectionSummaryResponse(
        items=[_summary_entry_response(e) for e in entries]
    )


@router.post(
    "/{project_id}/drawings/{master_drawing_id}/regions",
    response_model=DrawingRegionResponse,
    status_code=201,
)
def create_drawing_region(
    project_id: int,
    master_drawing_id: int,
    body: DrawingRegionCreate,
    idempotency_key: str = Depends(get_idempotency_key),
    db: Session = Depends(get_db),
) -> DrawingRegionResponse:
    """Create a user-defined region on a master drawing."""
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

    try:
        region = storage.create_drawing_region(
            master_drawing_id,
            label=body.label,
            page=body.page,
            geometry=body.geometry,
            polygon_points=body.polygon_points,
            inspection_type_tags=body.inspection_type_tags,
            location_tags=body.location_tags,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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


@router.patch(
    "/{project_id}/drawings/{master_drawing_id}/regions/{region_id}",
    response_model=DrawingRegionResponse,
)
def update_drawing_region(
    project_id: int,
    master_drawing_id: int,
    region_id: int,
    body: DrawingRegionUpdate,
    db: Session = Depends(get_db),
) -> DrawingRegionResponse:
    """Partial update for a backend region (geometry and/or tags)."""
    storage = StorageService(db)
    _ensure_master_drawing_in_project(storage, project_id, master_drawing_id)

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        existing = storage.get_drawing_region(master_drawing_id, region_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Drawing region not found")
        return DrawingRegionResponse.model_validate(existing)

    try:
        region = storage.update_drawing_region(
            master_drawing_id,
            region_id,
            label=updates.get("label"),
            page=updates.get("page"),
            geometry=updates.get("geometry"),
            polygon_points=updates["polygon_points"]
            if "polygon_points" in updates
            else ...,
            inspection_type_tags=updates.get("inspection_type_tags"),
            location_tags=updates.get("location_tags"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if region is None:
        raise HTTPException(status_code=404, detail="Drawing region not found")
    return DrawingRegionResponse.model_validate(region)


@router.delete(
    "/{project_id}/drawings/{master_drawing_id}/regions/{region_id}",
    status_code=204,
)
def delete_drawing_region(
    project_id: int,
    master_drawing_id: int,
    region_id: int,
    db: Session = Depends(get_db),
) -> None:
    """Delete a backend region. Linked overlays keep history; region_id is SET NULL."""
    storage = StorageService(db)
    _ensure_master_drawing_in_project(storage, project_id, master_drawing_id)

    deleted = storage.delete_drawing_region(master_drawing_id, region_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Drawing region not found")
