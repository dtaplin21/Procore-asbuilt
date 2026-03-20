from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models.schemas import (
    DrawingAlignmentHistoryListResponse,
    DrawingCompareRequest,
    DrawingComparisonWorkspaceResponse,
    DrawingDiffHistoryListResponse,
)
from services.drawing_comparison import DrawingComparisonService

router = APIRouter(prefix="/api/projects", tags=["drawing-comparison"])


@router.post(
    "/{project_id}/drawings/{master_drawing_id}/compare",
    response_model=DrawingComparisonWorkspaceResponse,
)
def compare_drawings(
    project_id: int,
    master_drawing_id: int,
    payload: DrawingCompareRequest,
    force_recompute: bool = Query(False),
    db: Session = Depends(get_db),
):
    service = DrawingComparisonService(db)
    try:
        result = service.compare(
            project_id=project_id,
            master_drawing_id=master_drawing_id,
            sub_drawing_id=payload.sub_drawing_id,
            force_recompute=force_recompute,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Drawing comparison failed: {str(e)}"
        )


@router.get(
    "/{project_id}/drawings/{master_drawing_id}/alignments",
    response_model=DrawingAlignmentHistoryListResponse,
)
def list_drawing_alignments(
    project_id: int,
    master_drawing_id: int,
    db: Session = Depends(get_db),
):
    service = DrawingComparisonService(db)

    try:
        return service.list_alignments(
            project_id=project_id,
            master_drawing_id=master_drawing_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load alignments: {str(e)}")


@router.get(
    "/{project_id}/drawings/{master_drawing_id}/diffs",
    response_model=DrawingDiffHistoryListResponse,
)
def list_drawing_diffs(
    project_id: int,
    master_drawing_id: int,
    alignment_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    service = DrawingComparisonService(db)

    try:
        return service.list_diffs(
            project_id=project_id,
            master_drawing_id=master_drawing_id,
            alignment_id=alignment_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load diffs: {str(e)}")
