from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models.schemas import DrawingComparisonWorkspaceResponse
from services.drawing_comparison import compare_sub_drawing_to_master

router = APIRouter(prefix="/api/projects", tags=["drawing-comparison"])


@router.post(
    "/{project_id}/drawings/compare/{master_drawing_id}/{sub_drawing_id}",
    response_model=DrawingComparisonWorkspaceResponse,
)
def compare_drawings(
    project_id: int,
    master_drawing_id: int,
    sub_drawing_id: int,
    force_recompute: bool = Query(False),
    db: Session = Depends(get_db),
):
    try:
        result = compare_sub_drawing_to_master(
            db,
            project_id=project_id,
            master_drawing_id=master_drawing_id,
            sub_drawing_id=sub_drawing_id,
            force_recompute=force_recompute,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Drawing comparison failed: {exc}")
