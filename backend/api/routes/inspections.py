from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional
from database import get_db
from services.storage import StorageService

router = APIRouter(prefix="/api/inspections", tags=["inspections"])

@router.get("")
async def get_inspections(
    project_id: Optional[str] = Query(None),
    limit: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    storage = StorageService(db)
    inspections = storage.get_inspections(project_id)
    if limit:
        inspections = inspections[:limit]
    return inspections

@router.get("/{inspection_id}")
async def get_inspection(inspection_id: str, db: Session = Depends(get_db)):
    storage = StorageService(db)
    inspection = storage.get_inspection(inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return inspection

@router.post("", status_code=201)
async def create_inspection(inspection: Dict[str, Any], db: Session = Depends(get_db)):
    storage = StorageService(db)
    return storage.create_inspection(inspection)

@router.patch("/{inspection_id}")
async def update_inspection(
    inspection_id: str,
    updates: dict,
    db: Session = Depends(get_db)
):
    storage = StorageService(db)
    inspection = storage.update_inspection(inspection_id, updates)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return inspection

