from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional, cast
from api.dependencies import get_db
from services.storage import StorageService
from models.schemas import (
    ProjectResponse,
    ProjectListResponse,
    DashboardSummaryResponse,
    DrawingResponse,
    ProcoreWritebackRequest,
    ProcoreWritebackResponse,
)
from models.models import Drawing, Project
from services.file_storage import save_upload, get_file_path
from services.procore_writeback_contract import build_writeback_contract
from services.procore_writeback import translate_contract_to_procore_payload
from services.procore_client import ProcoreAPIClient
from services.procore_connection_store import get_active_connection
from errors import ProcoreNotConnected
from datetime import datetime

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


@router.post(
    "/{project_id}/procore/writeback",
    response_model=ProcoreWritebackResponse,
)
async def procore_writeback(
    project_id: int,
    body: ProcoreWritebackRequest,
    user_id: str = Query(..., description="Procore user ID for auth"),
    db: Session = Depends(get_db),
) -> ProcoreWritebackResponse:
    """
    Write inspection run to Procore.

    - **dry_run**: Returns the payload that would be sent (no API call).
    - **commit**: Calls Procore create_inspection and returns the created inspection.

    Uses Project.procore_project_id for the Procore API.
    """
    if body.mode not in ("dry_run", "commit"):
        raise HTTPException(
            status_code=400,
            detail="mode must be 'dry_run' or 'commit'",
        )

    # 1. Load the internal contract
    try:
        contract = build_writeback_contract(db, project_id, body.inspection_run_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. Translate to Procore format
    procore_payload = translate_contract_to_procore_payload(contract)

    # 3. Dry-run: return payload (no API call)
    if body.mode == "dry_run":
        return ProcoreWritebackResponse(mode="dry_run", payload=procore_payload)

    # 4. Commit: require Procore connection and push to Procore
    if get_active_connection(db, user_id) is None:
        raise ProcoreNotConnected(details={"user_id": user_id})

    procore_project_id = contract.get("project", {}).get("procore_project_id", "")
    if not procore_project_id:
        raise HTTPException(
            status_code=400,
            detail="Project has no procore_project_id; sync project from Procore first",
        )

    async with ProcoreAPIClient(db, user_id) as client:
        created = await client.create_inspection(
            project_id=str(procore_project_id),
            inspection_data=procore_payload,
        )
    return ProcoreWritebackResponse(
        mode="commit",
        procore_inspection=created,
    )


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
        setattr(drawing, "file_url", f"/api/projects/{project_id}/drawings/{cast(int, drawing.id)}/file")
    
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
    setattr(drawing, "file_url", f"/api/projects/{project_id}/drawings/{cast(int, drawing.id)}/file")
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

