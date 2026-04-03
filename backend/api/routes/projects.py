from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional, cast

from api.dependencies import get_db
from services.drawing_comparison import serialize_drawing_for_workspace
from services.drawing_render_jobs import enqueue_drawing_render_job
from services.storage import StorageService
from models.schemas import (
    ProjectResponse,
    ProjectListResponse,
    DashboardSummaryResponse,
    DrawingResponse,
    DrawingSummary,
    DrawingWorkspaceDrawingResponse,
    JobListResponse,
    ProjectDrawingsResponse,
)
from models.models import Drawing, Project
from services.file_storage import save_upload, get_file_path

router = APIRouter(prefix="/api/projects", tags=["projects"])

@router.get("", response_model=ProjectListResponse)
async def get_projects(
    company_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List projects with pagination (limit, offset)."""
    storage = StorageService(db)
    items, total = storage.get_projects(company_id=company_id, limit=limit, offset=offset)
    return ProjectListResponse(
        items=[ProjectResponse.model_validate(p) for p in items],
        total=total,
        limit=limit,
        offset=offset,
    )

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
    current_drawing_id: Optional[int] = Query(
        None,
        alias="currentDrawingId",
        description="Optional master drawing id to scope comparison progress KPIs.",
    ),
    db: Session = Depends(get_db),
):
    """Return a high‑level dashboard summary for a given project.

    * ``project_id`` is required and used to look up the project in storage.
    * ``user_id`` is optional and, when provided, is passed through to
      :class:`~services.storage.StorageService.get_project_dashboard_summary`
      so that the service can return an active Procore company context if the
      user has an active connection.
    * ``currentDrawingId`` optionally selects a master drawing; comparison progress
      is scoped to that master when valid for this project. High-severity diff risk
      is global across active projects.

    The storage method will return an empty dict if the project does not
    exist; we translate that into an HTTP 404 so clients can react
    appropriately.
    """

    storage = StorageService(db)
    summary = storage.get_project_dashboard_summary(
        project_id=project_id,
        procore_user_id=user_id,
        current_drawing_id=current_drawing_id,
    )

    if not summary:
        # storage returns an empty dict when no project is found
        raise HTTPException(status_code=404, detail="Project not found")

    return summary


@router.get("/{project_id}/jobs", response_model=JobListResponse)
def get_project_jobs(
    project_id: int,
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    storage = StorageService(db)
    project = storage.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    jobs = storage.get_project_jobs(project_id=project_id, status=status)
    return {"jobs": jobs}


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
    setattr(drawing, "file_url", f"/api/projects/{project_id}/drawings/{cast(int, drawing.id)}/file")
    db.commit()
    db.refresh(drawing)

    # Enqueue async render job for PDF/image rendition generation
    enqueue_drawing_render_job(db, project_id, cast(int, drawing.id))

    return drawing


@router.get("/{project_id}/drawings", response_model=ProjectDrawingsResponse)
def list_project_drawings(
    project_id: int,
    db: Session = Depends(get_db),
):
    """List all drawings for a project.

    - Metadata comes from database, no filesystem reads
    - Returns drawings with camelCase fields for workspace/sub-drawing selection
    - Response shape: { drawings: [...] }
    """
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    service = StorageService(db)
    drawings = service.list_drawings(project_id)

    result = []
    for d in drawings:
        item = DrawingSummary.model_validate(d)
        if not item.file_url:
            item = item.model_copy(
                update={
                    "file_url": f"/api/projects/{project_id}/drawings/{d.id}/file"
                }
            )
        result.append(item)

    return ProjectDrawingsResponse(drawings=result)


@router.get(
    "/{project_id}/drawings/{drawing_id}",
    response_model=DrawingWorkspaceDrawingResponse,
)
def get_project_drawing(
    project_id: int,
    drawing_id: int,
    page: int = Query(1, ge=1, description="Active page for rendered image URL"),
    db: Session = Depends(get_db),
):
    """Get metadata for a specific drawing (rendition-aware workspace payload).

    - Prefers rendered page image URL when rendition is ready; falls back to source file
    - Returns drawing details including fileUrl, sourceFileUrl, widthPx, heightPx
    """
    service = StorageService(db)
    drawing = service.get_drawing(project_id, drawing_id)

    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")

    serialized = serialize_drawing_for_workspace(db, drawing, active_page=page)
    return DrawingWorkspaceDrawingResponse(
        id=serialized["id"],
        name=serialized["name"],
        file_url=serialized["fileUrl"],
        source_file_url=serialized["sourceFileUrl"],
        page_count=serialized["pageCount"],
        active_page=serialized["activePage"],
        width_px=serialized.get("widthPx"),
        height_px=serialized.get("heightPx"),
        processing_status=serialized.get("processingStatus", "pending"),
        processing_error=serialized.get("processingError"),
        project_id=serialized.get("projectId"),
        source=serialized.get("source"),
    )


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

    storage_key = cast(Optional[str], drawing.storage_key)
    if not storage_key:
        raise HTTPException(status_code=404, detail="No file available")

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


@router.get("/{project_id}/drawings/{drawing_id}/file", response_class=FileResponse)
def download_project_drawing_file(
    project_id: int,
    drawing_id: int,
    db: Session = Depends(get_db),
):
    """Secure file download for a drawing. Returns file bytes with correct content-type.

    Flow:
    - Load drawing via StorageService.get_drawing(project_id, drawing_id)
    - If not found -> 404
    - Resolve on-disk path via get_file_path(drawing.storage_key)
    - Return FileResponse(path, media_type=..., filename=drawing.name)
    """
    service = StorageService(db)
    drawing = service.get_drawing(project_id, drawing_id)
    if not drawing:
        raise HTTPException(status_code=404, detail="Drawing not found")

    storage_key = cast(Optional[str], drawing.storage_key)
    if not storage_key:
        raise HTTPException(status_code=404, detail="No file available")

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
