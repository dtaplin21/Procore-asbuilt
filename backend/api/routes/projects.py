from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
from database import get_db
from services.storage import StorageService
from models.schemas import ProjectResponse
from models.schemas import DashboardSummaryResponse
from models.schemas import DrawingResponse
from models.models import Drawing, Project
import os
from uuid import uuid4
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
    # Verify project exists
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    # Prepare upload directory
    upload_dir = os.path.join(os.path.dirname(__file__), "..", "..", "uploads")
    project_dir = os.path.join(upload_dir, str(project_id))
    os.makedirs(project_dir, exist_ok=True)

    # Save file with uuid prefix to avoid collisions
    filename = f"{uuid4().hex}_{os.path.basename(file.filename)}"
    file_path = os.path.join(project_dir, filename)

    try:
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Build storage_key and file_url (file_url served by a future download endpoint)
    storage_key = f"uploads/{project_id}/{filename}"
    file_url = f"/api/projects/{project_id}/drawings/{filename}"  # simple placeholder

    # Persist drawing record
    drawing = Drawing(
        project_id=project_id,
        source="upload",
        name=file.filename,
        storage_key=storage_key,
        file_url=file_url,
        content_type=file.content_type,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(drawing)
    db.commit()
    db.refresh(drawing)

    return drawing

