"""
Drawing diffs API.

Diff analysis results between master and sub drawings.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.dependencies import get_db
from models.schemas import DrawingDiffCreate, DrawingDiffResponse
from services.storage import StorageService

router = APIRouter(prefix="/api/projects", tags=["drawing-diffs"])


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


@router.get(
    "/{project_id}/drawings/{master_drawing_id}/diffs",
    response_model=List[DrawingDiffResponse],
)
def list_drawing_diffs(
    project_id: int,
    master_drawing_id: int,
    alignment_id: Optional[int] = Query(None, description="Filter by alignment"),
    db: Session = Depends(get_db),
) -> List[DrawingDiffResponse]:
    """List diffs for a master drawing, optionally filtered by alignment."""
    storage = StorageService(db)
    _ensure_master_drawing_in_project(storage, project_id, master_drawing_id)

    diffs = storage.list_drawing_diffs(master_drawing_id, alignment_id=alignment_id)
    return [DrawingDiffResponse.model_validate(d) for d in diffs]


@router.post(
    "/{project_id}/drawings/{master_drawing_id}/diffs",
    response_model=DrawingDiffResponse,
)
def create_drawing_diff(
    project_id: int,
    master_drawing_id: int,
    body: DrawingDiffCreate,
    db: Session = Depends(get_db),
) -> DrawingDiffResponse:
    """Create a drawing diff. Validates alignment belongs to project and master drawing."""
    storage = StorageService(db)
    _ensure_master_drawing_in_project(storage, project_id, master_drawing_id)

    alignment = storage.get_drawing_alignment_by_id(
        project_id, master_drawing_id, body.alignment_id
    )
    if alignment is None:
        raise HTTPException(
            status_code=404,
            detail=f"Alignment {body.alignment_id} not found on master drawing",
        )

    diff_regions = [r.model_dump() for r in body.diff_regions]
    diff = storage.create_drawing_diff(
        body.alignment_id,
        summary=body.summary,
        severity=body.severity,
        diff_regions=diff_regions,
        finding_id=body.finding_id,
    )
    return DrawingDiffResponse.model_validate(diff)


@router.get(
    "/{project_id}/drawings/{master_drawing_id}/alignments/{alignment_id}/diffs/{diff_id}",
    response_model=DrawingDiffResponse,
)
def get_drawing_diff(
    project_id: int,
    master_drawing_id: int,
    alignment_id: int,
    diff_id: int,
    db: Session = Depends(get_db),
) -> DrawingDiffResponse:
    """Get a single diff by id. Validates alignment belongs to project and master drawing."""
    storage = StorageService(db)
    _ensure_master_drawing_in_project(storage, project_id, master_drawing_id)

    alignment = storage.get_drawing_alignment_by_id(
        project_id, master_drawing_id, alignment_id
    )
    if alignment is None:
        raise HTTPException(
            status_code=404,
            detail=f"Alignment {alignment_id} not found on master drawing",
        )

    diff = storage.get_drawing_diff(alignment_id, diff_id)
    if diff is None:
        raise HTTPException(
            status_code=404,
            detail=f"Diff {diff_id} not found",
        )
    return DrawingDiffResponse.model_validate(diff)
