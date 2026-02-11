from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from database import get_db
from services.storage import StorageService
from models.schemas import Project, ProjectCreate

router = APIRouter(prefix="/api/projects", tags=["projects"])

@router.get("", response_model=List[Project])
async def get_projects(db: Session = Depends(get_db)):
    storage = StorageService(db)
    projects = storage.get_projects()
    return projects

@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: str, db: Session = Depends(get_db)):
    storage = StorageService(db)
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

