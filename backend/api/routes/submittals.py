from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from database import get_db
from services.storage import StorageService
from models.schemas import Submittal, SubmittalCreate

router = APIRouter(prefix="/api/submittals", tags=["submittals"])

@router.get("", response_model=List[Submittal])
async def get_submittals(
    project_id: Optional[str] = Query(None),
    limit: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    storage = StorageService(db)
    try:
        submittals = storage.get_submittals(project_id)
        if limit:
            submittals = submittals[:limit]
        return submittals
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch submittals: {str(e)}")

@router.get("/{submittal_id}", response_model=Submittal)
async def get_submittal(submittal_id: str, db: Session = Depends(get_db)):
    storage = StorageService(db)
    try:
        submittal = storage.get_submittal(submittal_id)
        if not submittal:
            raise HTTPException(status_code=404, detail="Submittal not found")
        return submittal
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch submittal: {str(e)}")

@router.post("", response_model=Submittal, status_code=201)
async def create_submittal(submittal: SubmittalCreate, db: Session = Depends(get_db)):
    storage = StorageService(db)
    try:
        submittal_data = submittal.model_dump()
        new_submittal = storage.create_submittal(submittal_data)
        return new_submittal
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create submittal: {str(e)}")

@router.patch("/{submittal_id}", response_model=Submittal)
async def update_submittal(
    submittal_id: str,
    updates: dict,
    db: Session = Depends(get_db)
):
    storage = StorageService(db)
    try:
        submittal = storage.update_submittal(submittal_id, updates)
        if not submittal:
            raise HTTPException(status_code=404, detail="Submittal not found")
        return submittal
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update submittal: {str(e)}")

