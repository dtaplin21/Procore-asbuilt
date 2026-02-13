from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Any, Dict, List
from database import get_db
from services.storage import StorageService

router = APIRouter(prefix="/api/projects", tags=["projects"])

@router.get("")
async def get_projects(db: Session = Depends(get_db)):
    storage = StorageService(db)
    return storage.get_projects()

@router.get("/{project_id}")
async def get_project(project_id: str, db: Session = Depends(get_db)):
    storage = StorageService(db)
    project = storage.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

