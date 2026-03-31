from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.dependencies import get_db
from models.schemas import DrawingProgressSummary
from services.drawing_progress import DrawingProgressService

router = APIRouter(prefix="/api/projects", tags=["drawing-progress"])


@router.get(
    "/{project_id}/drawings/{master_drawing_id}/progress",
    response_model=DrawingProgressSummary,
)
def get_master_drawing_progress(
    project_id: int,
    master_drawing_id: int,
    db: Session = Depends(get_db),
):
    service = DrawingProgressService(db)
    return service.get_master_drawing_progress(
        project_id=project_id,
        master_drawing_id=master_drawing_id,
    )
