"""
Drawing regions and alignments API.

Phase 2: User-defined regions on master drawings and sub-drawing alignment linkage.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.dependencies import get_db
from models.schemas import (
    DrawingRegionCreate,
    DrawingRegionResponse,
    DrawingAlignmentCreate,
    DrawingAlignmentResponse,
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
    db: Session = Depends(get_db),
) -> DrawingRegionResponse:
    """
    Create a user-defined region on a master drawing.
    Validates that master_drawing belongs to project.
    """
    storage = StorageService(db)
    _ensure_master_drawing_in_project(storage, project_id, master_drawing_id)

    region = storage.create_drawing_region(
        master_drawing_id,
        label=body.label,
        page=body.page,
        geometry=body.geometry,
    )
    return DrawingRegionResponse.model_validate(region)


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
    db: Session = Depends(get_db),
) -> DrawingAlignmentResponse:
    """
    Create a sub-drawing alignment to a master (and optionally a region).
    Validates master_drawing and sub_drawing belong to project.
    """
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
    return DrawingAlignmentResponse.model_validate(alignment)


@router.get(
    "/{project_id}/drawings/{master_drawing_id}/alignments",
    response_model=List[DrawingAlignmentResponse],
)
def list_drawing_alignments(
    project_id: int,
    master_drawing_id: int,
    db: Session = Depends(get_db),
) -> List[DrawingAlignmentResponse]:
    """List all alignments for a master drawing."""
    storage = StorageService(db)
    _ensure_master_drawing_in_project(storage, project_id, master_drawing_id)

    alignments = storage.list_drawing_alignments(master_drawing_id)
    return [DrawingAlignmentResponse.model_validate(a) for a in alignments]
