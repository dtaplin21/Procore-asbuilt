from typing import List, Optional, cast

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from api.dependencies import get_db
from models.models import Drawing
from models.schemas import DrawingOverlayResponse, DrawingResponse
from services.storage import StorageService
from services.file_storage import save_upload, get_file_path
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
    storage_key, content_type, original_name = save_upload(file, project_id, category="drawings")

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

    storage_key = cast(Optional[str], drawing.storage_key)
    if not storage_key:
        raise HTTPException(status_code=404, detail="File not available")

    path = get_file_path(storage_key)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")

    content_type = cast(Optional[str], drawing.content_type) or "application/octet-stream"
    name = cast(str, drawing.name)
    return FileResponse(
        path,
        media_type=content_type,
        filename=name,
    )


@router.get(
    "/api/projects/{project_id}/drawings/{drawing_id}/overlays",
    response_model=List[DrawingOverlayResponse],
)
def list_drawing_overlays(
    project_id: int,
    drawing_id: int,
    inspection_run_id: Optional[int] = Query(None, description="Filter by inspection run"),
    diff_id: Optional[int] = Query(None, description="Filter by diff"),
    db: Session = Depends(get_db),
) -> List[DrawingOverlayResponse]:
    """
    GET /api/projects/{project_id}/drawings/{drawing_id}/overlays

    List overlays for a drawing (master drawing). Sorted by created_at desc.
    Optional filters: inspection_run_id, diff_id.
    """
    service = StorageService(db)
    drawing = service.get_drawing(project_id, drawing_id)
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")

    overlays = service.list_drawing_overlays(
        master_drawing_id=drawing_id,
        inspection_run_id=inspection_run_id,
        diff_id=diff_id,
    )
    return [DrawingOverlayResponse.model_validate(o) for o in overlays]