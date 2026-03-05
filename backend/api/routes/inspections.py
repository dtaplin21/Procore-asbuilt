from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Any, Dict, Optional
from database import get_db
from services.storage import StorageService
from models.schemas import InspectionListResponse

router = APIRouter(prefix="/api/inspections", tags=["inspections"])


@router.get("", response_model=InspectionListResponse)
async def get_inspections(
    project_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List inspection records with pagination (limit, offset). Placeholder: returns empty list."""
    storage = StorageService(db)
    items, total = storage.get_inspections(project_id, limit=limit, offset=offset)
    return InspectionListResponse(items=items, total=total, limit=limit, offset=offset)

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

