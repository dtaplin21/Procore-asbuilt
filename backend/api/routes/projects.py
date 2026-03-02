from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from backend.api.dependencies import get_db
from backend.services.storage import StorageService
from backend.models.schemas import ProjectResponse, DashboardSummaryResponse, DrawingResponse
from backend.models.models import Drawing, Project
from backend.services.file_storage import save_upload, get_file_path
from datetime import datetime

router = APIRouter(prefix="/api/projects", tags=["projects"])

@router.get("", response_model=List[ProjectResponse])
async def get_projects(
    company_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    storage = StorageService(db)
    return storage.get_projects(company_id=company_id)

@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: int, db: Session = Depends(get_db)):
    storage = StorageService(db)
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}/dashboard/summary", response_model=DashboardSummaryResponse)
async def get_project_dashboard_summary(
    project_id: int,
    user_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Return a high‑level dashboard summary for a given project.

    * ``project_id`` is required and used to look up the project in storage.
    * ``user_id`` is optional and, when provided, is passed through to
      :class:`~services.storage.StorageService.get_project_dashboard_summary`
      so that the service can return an active Procore company context if the
      user has an active connection.

    The storage method will return an empty dict if the project does not
    exist; we translate that into an HTTP 404 so clients can react
    appropriately.
    """

    storage = StorageService(db)
    summary = storage.get_project_dashboard_summary(
        project_id=project_id, procore_user_id=user_id
    )

    if not summary:
        # storage returns an empty dict when no project is found
        raise HTTPException(status_code=404, detail="Project not found")

    return summary



@router.post("/{project_id}/drawings", response_model=DrawingResponse)
async def upload_project_drawing(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a drawing file for a project.
    
    - Validates file type and size
    - Saves file to disk
    - Creates database record with file_url pointing to /file endpoint
    """
    # Verify project exists
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    # Persist file via helper (validates size/type and writes to disk)
    storage_key, content_type, original_name = save_upload(file, project_id, category="drawings")

    # Create drawing record via service layer
    service = StorageService(db)
    drawing = service.create_drawing(
        project_id=project_id,
        source="upload",
        name=original_name,
        storage_key=storage_key,
        content_type=content_type,
        page_count=None,
    )
    
    # Set file_url to point to the /file route (will be implemented in next step)
    drawing.file_url = f"/api/projects/{project_id}/drawings/{drawing.id}/file"
    db.commit()
    db.refresh(drawing)

    return drawing


@router.get("/{project_id}/drawings", response_model=List[DrawingResponse])
def list_project_drawings(
    project_id: int,
    db: Session = Depends(get_db),
):
    """List all drawings for a project.
    
    - Metadata comes from database, no filesystem reads
    - Returns drawings sorted by creation date (newest first)
    """
    # Verify project exists
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    service = StorageService(db)
    drawings = service.list_drawings(project_id)
    
    # Set file_url on each drawing to point to /file endpoint
    for drawing in drawings:
        drawing.file_url = f"/api/projects/{project_id}/drawings/{drawing.id}/file"
    
    db.commit()  # Persist file_url changes
    
    return drawings


@router.get("/{project_id}/drawings/{drawing_id}", response_model=DrawingResponse)
def get_project_drawing(
    project_id: int,
    drawing_id: int,
    db: Session = Depends(get_db),
):
    """Get metadata for a specific drawing.
    
    - Metadata comes from database, no filesystem reads
    - Returns drawing details including file_url
    """
    service = StorageService(db)
    drawing = service.get_drawing(project_id, drawing_id)
    
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")
    
    # Set file_url to point to /file endpoint
    drawing.file_url = f"/api/projects/{project_id}/drawings/{drawing.id}/file"
    db.commit()

    return drawing


@router.get(
    "/{project_id}/drawings/{drawing_id}/download",
    response_class=FileResponse,
)
def download_project_drawing(
    project_id: int,
    drawing_id: int,
    db: Session = Depends(get_db),
):
    # ensure the requested drawing belongs to the project
    drawing = (
        db.query(Drawing)
        .filter(Drawing.id == drawing_id, Drawing.project_id == project_id)
        .first()
    )
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")

    if not drawing.storage_key:
        raise HTTPException(status_code=404, detail="No file available")

    path = get_file_path(drawing.storage_key)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")

    return FileResponse(
        path,
        media_type=drawing.content_type or "application/octet-stream",
        filename=drawing.name,
    )

