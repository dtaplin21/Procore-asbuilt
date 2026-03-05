"""
Drawing diffs API.

Diff analysis results between master and sub drawings.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.dependencies import get_db
from models.schemas import DrawingDiffListResponse, DrawingDiffResponse, RunDrawingDiffRequest
from ai.pipelines import run_drawing_diff
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
    response_model=DrawingDiffListResponse,
)
def list_drawing_diffs(
    project_id: int,
    master_drawing_id: int,
    alignment_id: Optional[int] = Query(None, description="Filter by alignment"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    db: Session = Depends(get_db),
) -> DrawingDiffListResponse:
    """List diffs for a master drawing. Sorted by created_at desc. Paginated."""
    storage = StorageService(db)
    _ensure_master_drawing_in_project(storage, project_id, master_drawing_id)

    diffs, total = storage.list_drawing_diffs(
        master_drawing_id,
        alignment_id=alignment_id,
        limit=limit,
        offset=offset,
    )
    return DrawingDiffListResponse(
        items=[DrawingDiffResponse.model_validate(d) for d in diffs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{project_id}/drawings/{master_drawing_id}/diffs",
    response_model=List[DrawingDiffResponse],
)
def run_diffs_for_alignment(
    project_id: int,
    master_drawing_id: int,
    body: RunDrawingDiffRequest,
    db: Session = Depends(get_db),
) -> List[DrawingDiffResponse]:
    """
    Run the diff pipeline for an alignment.
    Validates alignment exists, project ownership, and master drawing match.
    """
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

    diffs = run_drawing_diff(db, alignment)
    return [DrawingDiffResponse.model_validate(d) for d in diffs]


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
