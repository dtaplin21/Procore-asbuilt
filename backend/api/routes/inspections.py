from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from database import get_db
from services.storage import StorageService
from models.schemas import Inspection, InspectionCreate

router = APIRouter(prefix="/api/inspections", tags=["inspections"])

@router.get("", response_model=List[Inspection])
async def get_inspections(
    project_id: Optional[str] = Query(None),
    limit: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    storage = StorageService(db)
    try:
        inspections = storage.get_inspections(project_id)
        if limit:
            inspections = inspections[:limit]
        return inspections
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch inspections: {str(e)}")

@router.get("/{inspection_id}", response_model=Inspection)
async def get_inspection(inspection_id: str, db: Session = Depends(get_db)):
    storage = StorageService(db)
    try:
        inspection = storage.get_inspection(inspection_id)
        if not inspection:
            raise HTTPException(status_code=404, detail="Inspection not found")
        return inspection
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch inspection: {str(e)}")

@router.post("", response_model=Inspection, status_code=201)
async def create_inspection(inspection: InspectionCreate, db: Session = Depends(get_db)):
    storage = StorageService(db)
    try:
        inspection_data = inspection.model_dump()
        new_inspection = storage.create_inspection(inspection_data)
        return new_inspection
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create inspection: {str(e)}")

@router.patch("/{inspection_id}", response_model=Inspection)
async def update_inspection(
    inspection_id: str,
    updates: dict,
    db: Session = Depends(get_db)
):
    storage = StorageService(db)
    try:
        inspection = storage.update_inspection(inspection_id, updates)
        if not inspection:
            raise HTTPException(status_code=404, detail="Inspection not found")
        return inspection
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update inspection: {str(e)}")

