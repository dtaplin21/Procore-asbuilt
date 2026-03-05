"""
Drawing diffs API.

Diff analysis results between master and sub drawings.
"""
import logging
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.dependencies import get_db
from errors import DrawingDiffPipelineError
from models.schemas import DrawingDiffListResponse, DrawingDiffResponse, RunDrawingDiffRequest
from ai.pipelines import run_drawing_diff
from services.storage import StorageService

logger = logging.getLogger(__name__)

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
    user_id: Optional[int] = Query(None, description="Optional: for UsageLog telemetry"),
    company_id: Optional[int] = Query(None, description="Optional: for UsageLog telemetry"),
    db: Session = Depends(get_db),
) -> List[DrawingDiffResponse]:
    """
    Run the diff pipeline for an alignment.
    Validates alignment exists, project ownership, and master drawing match.
    Logs diff runs for monitoring. Optionally creates UsageLog when user_id provided.
    """
    storage = StorageService(db)
    _ensure_master_drawing_in_project(storage, project_id, master_drawing_id)

    alignment = storage.get_drawing_alignment_by_id(
        project_id, master_drawing_id, body.alignment_id
    )
    if alignment is None:
        raise HTTPException(status_code=404, detail="alignment not found")

    # 409: diff already exists for this alignment (optional check)
    existing, total = storage.list_drawing_diffs(
        master_drawing_id, alignment_id=body.alignment_id, limit=1, offset=0
    )
    if total > 0:
        raise HTTPException(status_code=409, detail="diff already exists")

    logger.info(
        "drawing_diff_run_started",
        extra={
            "project_id": project_id,
            "master_drawing_id": master_drawing_id,
            "alignment_id": body.alignment_id,
        },
    )
    start = time.perf_counter()

    try:
        diffs = run_drawing_diff(db, alignment)
        duration_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "drawing_diff_run_completed",
            extra={
                "project_id": project_id,
                "master_drawing_id": master_drawing_id,
                "alignment_id": body.alignment_id,
                "diff_count": len(diffs),
                "duration_ms": round(duration_ms, 2),
            },
        )

        if user_id is not None:
            try:
                storage.create_usage_log(
                    user_id=user_id,
                    action="drawing_diff_run",
                    resource_type="drawing_diff",
                    company_id=company_id,
                    processing_time=duration_ms / 1000,
                    metadata={
                        "project_id": project_id,
                        "master_drawing_id": master_drawing_id,
                        "alignment_id": body.alignment_id,
                        "diff_count": len(diffs),
                    },
                )
            except Exception as e:
                logger.warning(
                    "drawing_diff_usage_log_failed",
                    extra={"user_id": user_id, "error": str(e)},
                )

        return [DrawingDiffResponse.model_validate(d) for d in diffs]
    except DrawingDiffPipelineError as e:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.warning(
            "drawing_diff_run_failed",
            extra={
                "project_id": project_id,
                "master_drawing_id": master_drawing_id,
                "alignment_id": body.alignment_id,
                "duration_ms": round(duration_ms, 2),
                "error": str(e),
            },
        )
        raise HTTPException(status_code=500, detail="pipeline failure")


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
        raise HTTPException(status_code=404, detail="alignment not found")

    diff = storage.get_drawing_diff(alignment_id, diff_id)
    if diff is None:
        raise HTTPException(
            status_code=404,
            detail=f"Diff {diff_id} not found",
        )
    return DrawingDiffResponse.model_validate(diff)
