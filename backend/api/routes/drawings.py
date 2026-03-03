from typing import List

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session

from backend.api.dependencies import get_db
from backend.models.models import Drawing
from backend.models.schemas import DrawingResponse
from backend.services.storage import StorageService
from backend.services.file_storage import save_upload, get_file_path
from fastapi.responses import FileResponse

router = APIRouter(tags=["drawings"])



@router.post("/api/projects/{project_id}/drawings", response_model=DrawingResponse)
async def upload_drawing(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> DrawingResponse:
    """
    POST /api/projects/{project_id}/drawings
    Upload a drawing file and persist metadata to database.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    # Save file to disk with validation
    storage_key, content_type, original_name = await save_upload(file, project_id, category="drawings")

    # Create database record
    service = StorageService(db)
    drawing = service.create_drawing(
        project_id=project_id,
        source="upload",
        name=original_name,
        storage_key=storage_key,
        content_type=content_type,
        page_count=None,
    )

    return DrawingResponse.from_orm(drawing)


@router.get("/api/projects/{project_id}/drawings", response_model=List[DrawingResponse])
def list_drawings(project_id: int, db: Session = Depends(get_db)) -> List[DrawingResponse]:
    """
    GET /api/projects/{project_id}/drawings
    List all drawings for a project.
    """
    service = StorageService(db)
    drawings = service.list_drawings(project_id)
    return [DrawingResponse.from_orm(d) for d in drawings]


@router.get("/api/projects/{project_id}/drawings/{drawing_id}", response_model=DrawingResponse)
def get_drawing(
    project_id: int,
    drawing_id: int,
    db: Session = Depends(get_db),
) -> DrawingResponse:
    """
    GET /api/projects/{project_id}/drawings/{drawing_id}
    Get a specific drawing by ID.
    """
    service = StorageService(db)
    drawing = service.get_drawing(project_id, drawing_id)
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")
    return DrawingResponse.from_orm(drawing)


@router.get("/api/projects/{project_id}/drawings/{drawing_id}/file", response_class=FileResponse)
def download_drawing_file(
    project_id: int,
    drawing_id: int,
    db: Session = Depends(get_db),
) -> FileResponse:
    """Download the file bytes for a drawing, verifying project scope."""
    service = StorageService(db)
    drawing = service.get_drawing(project_id, drawing_id)
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")

    if not drawing.storage_key:
        raise HTTPException(status_code=404, detail="File not available")

    path = get_file_path(drawing.storage_key)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")

    return FileResponse(
        path,
        media_type=drawing.content_type or "application/octet-stream",
        filename=drawing.name,
    )